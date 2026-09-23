"""استخراج زندهٔ فیلت‌ها از نتایج جستجو + فیلتر با Jev (بدون LLM).

جریان:
  facets_for(q)      -> حداکثر 3 صفحه نتیجه می‌گیرد، ویژگی‌ها را با regex از
                        عنوان فارسی محصولات در می‌آورد و گروه‌بندی برمی‌گرداند.
  apply_filter(q, g, v) -> group‌های عددی/اسمی (حجم، SPF، برند) با تطبیق مستقیم؛
                        group‌های معنایی (نوع پوست، بافت) با یک درخواست دسته‌ای Jev
                        (noul) روی همان محصولات — نتیجه کش می‌شود.
"""
import json
import re
import time
import threading
import urllib.parse

import server

UA = server.UA
CACHE_TTL = 900  # 15 دقیقه
_lock = threading.Lock()
_products_cache: dict[str, tuple[float, list[dict]]] = {}   # q -> (ts, cards)
_sorts_cache: dict[str, tuple[float, dict]] = {}            # q -> (ts, {normalised_label: id})
_jev_cache: dict[str, tuple[float, dict]] = {}               # q|g|v -> (ts, {pid: score})

# --- نرمال‌سازی متن فارسی عنوان (نیم‌فاصله/حروف عربی) ---
def norm(t: str) -> str:
    t = t or ""
    t = t.replace("\u200c", " ").replace("\u200b", "")
    for a, b in (("ي", "ی"), ("ك", "ک"), ("أ", "ا"), ("إ", "ا"), ("ة", "ه"), ("آ", "ا")):
        t = t.replace(a, b)
    t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2))
    return re.sub(r"\s+", " ", t).lower()


FA = "۰۱۲۳۴۵۶۷۸۹"
def to_en_digits(s: str) -> str:
    return s.translate(str.maketrans(FA, "0123456789"))


# --- گروه‌های ویژگی: regex از عنوان => برچسب ---
# (پترن‌ها روی متن نرمال‌شده تطبیق می‌شوند: حروف فارسی، ZWNJ=فاصله، کوچک)
# هر مقدار = (الگوی صریح در عنوان، الگوی سرنخ/مبهم)
# صریح => نگه‌داشتن بدون Jev؛ سرنخ بدون صراحت => کاندیدای Jev؛ بی‌سرنخ => حذف.
SKIN = {
    "پوست چرب": (r"پوست( ?های)? ?چرب|فاقد چربی|oil.?free|مات ?کننده|ضد ?براق",
                 r"چرب|براق|مات|matte|oil|آکنه|acne|کومدون|comedo|جوش"),
    "پوست خشک": (r"پوست( ?های)?( ?نرمال ?تا)? ?خشک",
                 r"خشک|آبرسان|ه?یدرات|hydrat|مرطوب|رطوبت|moistur"),
    "پوست مختلط": (r"پوست( ?های)? ?مختلط", r"مختلط|combo|mix"),
    "پوست حساس": (r"پوست( ?های)? ?حساس", r"حساس|sensitiv|التهاب|allerg|هایپو|فاقد بو"),
    "همه پوست‌ها": (r"همه ?پوست|انواع ?پوست|all ?skin", r"پوست"),
}
TEXTURE = {
    "کرم": (r"کرم", r"کرم|لوسیون|lotion|بالم"),
    "فلوئید": (r"فلوئ?ید|fluid", r"فلو"),
    "اسپری": (r"اسپری|spray", r"میست|mist"),
    "استیک": (r"استیک|stick|قلم[یه]? ?ضد", r"قلم"),
    "سرم": (r"سرم|serum", r"قطره|drop"),
    "بی‌بی/تانگ": (r"بی.?بی|bb cream|تنت?د|تان?ژ|رنگی", r"رنگ|tint"),
    "پرایمر": (r"پرایمر|primer", r"زیرساز"),
}
SEM_PATTERNS = {"نوع پوست": SKIN, "بافت": TEXTURE}

# --- گارد جنسیت: اگر کوئری جنسیت دارد، محصولات جنس مخالف حذف می‌شوند ---
# (موتور جستجوی دیجی‌کالا از صفحهٔ ۳ به بعد مایو زنانه را داخل «مایو مردانه» می‌ریزد)
GENDER_WORDS = {
    "male": r"مردانه|مردانه|پسرانه|آقا|男",
    "female": r"زنانه|بانوان|دخترانه|خانم",
}


def _query_gender(q: str) -> str | None:
    t = norm(q)
    has_m = re.search(GENDER_WORDS["male"], t)
    has_f = re.search(GENDER_WORDS["female"], t)
    if has_m and not has_f:
        return "male"
    if has_f and not has_m:
        return "female"
    return None


def gender_ok(card: dict, want: str | None) -> bool:
    """False فقط وقتی تضاد صریح است: عنوان/دستهٔ محصول جنس مخالفِ کوئری."""
    if not want:
        return True
    t = norm((card.get("title") or ""))
    dl = card.get("_dl") or {}
    cat = norm(str(dl.get("item_category5") or dl.get("category") or ""))
    other = GENDER_WORDS["female" if want == "male" else "male"]
    own = GENDER_WORDS[want]
    blob = t + "|" + cat
    # تضاد: جنس مخالف هست و جنس خود کوئری در همان متن نیست
    if re.search(other, blob) and not re.search(own, blob):
        return False
    return True
JEV_MAX = 90  # سقف فراخوان‌های Jev برای هر فیلتر (هزینه/تأخیر قابل‌کنترل)
POOL_PAGES = 10  # استخر کاندیدا: ۱۰ صفحه × ۲۰ = تا ۲۰۰ محصول
SPF_MIN = 30
LABEL_GROUP_MODE = {  # how each group filters
    "نوع پوست": "jev", "بافت": "jev",
    "حجم": "direct", "ضد آفتاب SPF": "direct", "برند": "direct", "تخفیف": "direct",
}

VOL_RE = re.compile(r"(?<![\w.٫])([0-9]+(?:[.٫][0-9]+)?)\s*(میلی ?لیتر|ml|gr|گرم|g)(?![\w])", re.I)
PACK_NUM = re.compile(r"(?<![\d۰-۹])([0-9۰-۹]{1,3}) ?(?:جفت[یه]?|عددی|تایی|عدد|تا)\b")
PACK_FA = re.compile(r"(?:^|\s|ه)(دو|سه|چهار|پنج|شش|شیش|هفت|هشت|نه|ده) ?(?:جفت[یه]?|عددی|تایی|تا)\b")
FA_NUMS = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "شیش": 6,
           "هفت": 7, "هشت": 8, "نه": 9, "ده": 10}
SPF_RE = re.compile(r"(?:spf|اسپف)[\s\u200c-]*(\d{2})", re.I)


def search_source(q):
    """Internal category scope isolates caches and removes the original query."""
    if q.startswith("@category:"):
        slug = q.removeprefix("@category:")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", slug):
            raise ValueError("Invalid category slug")
        return f"{server.API}/categories/{slug}/search/", {}
    return f"{server.API}/search/", {"q": q}


def _search_products(q: str, pages: int = POOL_PAGES) -> tuple[list[dict], dict]:
    import concurrent.futures as cf

    def one(pg: int):
        url, params = search_source(q)
        result = server._get(url, {**params, "page": pg})
        data = result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise RuntimeError(f"Invalid search response on page {pg}")
        return result

    first = one(1)
    pager = first["data"].get("pager") or {}
    total_pages = pager.get("total_pages")
    if isinstance(total_pages, int):
        pages = min(pages, max(1, total_pages))
    out, sorts = [], {}
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        results = [first] + list(ex.map(one, range(2, pages + 1)))
    for pg, data in enumerate(results, 1):
        if not data:
            continue
        d = data.get("data") or {}
        if pg == 1:
            sorts = {norm(o.get("title_fa") or ""): o["id"]
                     for o in (d.get("sort_options") or []) if o.get("id") is not None}
        out.extend(d.get("products") or [])
    return out, sorts


def _card_full(p: dict) -> dict:
    c = server._card(p)
    main = (p.get("images") or {}).get("main") or {}
    urls = main.get("webp_url") or main.get("url") or []
    c["image"] = urls[0] if urls else None
    c["brand"] = (p.get("data_layer") or {}).get("brand")
    c["_dl"] = p.get("data_layer") or {}
    return c


def _pack_count(t: str) -> int:
    m = PACK_NUM.search(t)
    if m:
        packs = max(1, int(to_en_digits(m.group(1))))
    else:
        mf = PACK_FA.search(t)
        packs = FA_NUMS.get(mf.group(1), 1) if mf else 1
    if packs > 12:  # «۲ عددی/دو تایی» تا دوجین منطقی‌ست؛ بزرگ‌ترش احتمالاً سوءتطبیق است
        packs = 1
    return packs


def _volumes(text):
    """Positive decimal quantities with canonical, distinct mass/volume units."""
    return [(float(n.replace("٫", ".")), "ml" if u == "ml" or "لیتر" in u else "g")
            for n, u in VOL_RE.findall(norm(text)) if float(n.replace("٫", ".")) > 0]


def unit_price(card: dict) -> tuple[float | None, str | None]:
    """مبنای منصفانهٔ قیمت از عنوان:
    - حجم (ml/g) موجود => قیمت هر ۱۰۰ واحد (حجم × تعداد بسته)
    - حجم نیست ولی بستهٔ چندنفره => قیمت هر عدد/جفت  ← مسواک «۲ عددی» ÷۲
    - هیچ‌کدام => None (قیمت کل)."""
    t = card.get("_t") or norm(card.get("title") or "")
    packs = _pack_count(t)
    vols = _volumes(t)
    if vols:
        # دیجی‌کالا در عنوان‌ها معمولاً «حجمِ هر واحد» را می‌نویسد و بسته را جدا:
        # «۴۰ میلی لیتر بسته ۲ عددی» = ۲×۴۰، نه ۴۰. پس کمینهٔ حجم × تعداد بسته.
        # (جمعِ چند حجمِ نامساوی فقط برای ست‌های «۵۰ml + ۲۰ml هدیه» درست است)
        if len({u for _, u in vols}) != 1:
            return None, None  # Do not add grams to millilitres.
        nums = sorted(n for n, _ in vols)
        uniq = sorted(set(nums))
        if len(uniq) == 1:
            total = uniq[0] * packs            # «۵۰ml بسته ۲ عددی» => ۱۰۰
        else:
            total = sum(nums) * (packs or 1)   # «۵۰ml + ۲۰ml هدیه» => ۷۰ (× بسته)
        kind = vols[0][1]
        qty = total
        return round(card["price_toman"] / qty * 100), (
            f"{'×' + str(packs) if packs > 1 else ''}{kind}")
    if packs > 1:
        return round(card["price_toman"] / packs), f"×{packs}عددی"
    return None, None


def get_products(q: str) -> list[dict]:
    key = norm(q)
    with _lock:
        hit = _products_cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    raw, sorts = _search_products(q)
    seen, uniq = set(), []
    for p in raw:
        if p.get("id") and p["id"] not in seen:
            seen.add(p["id"])
            uniq.append(p)
    cards = [_card_full(p) for p in uniq]
    g = _query_gender(q)
    if g:
        cards = [c for c in cards if gender_ok(c, g)]
    for c in cards:
        c["_t"] = norm(c["title"] or "")
        up, label = unit_price(c)
        c["unit_price_toman"] = up   # تومان به‌ازای ۱۰۰ml/g (None اگر حجم نداشت)
        c["unit_label"] = label
    with _lock:
        _products_cache[key] = (time.time(), cards)
        _sorts_cache[key] = (time.time(), sorts)
    return cards


def get_sorts(q: str) -> dict:
    """sort_option‌های واقعی همین کوئری (نرمال‌شده): عناوین دیجی‌کالا per-category متفاوت‌اند!"""
    get_products(q)  # ensure warm
    key = norm(q)
    with _lock:
        hit = _sorts_cache.get(key)
    return hit[1] if hit else {}


# کلید UI -> عنوان‌های احتمالی در sort_options دیجی‌کالا
_SORT_LABELS = {
    "cheap": ["ارزان ترین"],
    "expensive": ["گران ترین"],
    "bestselling": ["پرفروش ترین", "پرفروش ترین‌"],
    "newest": ["جدید ترین"],
    "popular": ["پربازدید ترین"],
}


def resolve_sort(q: str, key: str) -> int | None:
    """id مرتب‌سازی را از sort_optionsِ زندهٔ همین کوئری پیدا می‌کند."""
    sorts = get_sorts(q)
    for label in _SORT_LABELS.get(key, []):
        if label in sorts:
            return sorts[label]
    return None


def facets_for(q: str) -> list[dict]:
    cards = get_products(q)
    if len(cards) < 4:
        return []
    groups: dict[str, dict[str, int]] = {}

    def bump(g, label):
        groups.setdefault(g, {})
        groups[g][label] = groups[g].get(label, 0) + 1

    for c in cards:
        t = c["_t"]
        for label, (explicit, _hint) in SKIN.items():
            if re.search(explicit, t):
                bump("نوع پوست", label)
        for label, (explicit, _hint) in TEXTURE.items():
            if re.search(explicit, t):
                bump("بافت", label)
        for n, unit in set(_volumes(t)):
            bump("حجم", f"{n:g} {unit}")
        m = SPF_RE.search(t)
        if m:
            bump("ضد آفتاب SPF", f"SPF{m.group(1)}")
        if c.get("brand"):
            bump("برند", c["brand"])

    out = []
    # گروه تخفیف — از درصد تخفیف واقعی کارت‌ها (بدون Jev)
    for thr in (30, 20, 10):
        n = sum(1 for c in cards if (c.get("discount_pct") or 0) >= thr)
        if n >= 3:
            groups.setdefault("تخفیف", {})
            groups["تخفیف"][f"{thr}٪ و بیشتر"] = n
    for g, labels in groups.items():
        opts = sorted(
            ({"label": l, "count": n} for l, n in labels.items() if n >= (2 if g != "برند" else 3)),
            key=lambda x: -x["count"])[:10]
        if len(opts) >= 2:
            out.append({"group": g, "mode": LABEL_GROUP_MODE.get(g, "direct"), "options": opts})
    order = ["نوع پوست", "بافت", "ضد آفتاب SPF", "حجم", "تخفیف", "برند"]
    out.sort(key=lambda g: order.index(g["group"]) if g["group"] in order else 99)
    return out


def _direct_match(c: dict, group: str, value: str) -> bool:
    t = c["_t"]
    if group == "برند":
        return norm(c.get("brand") or "") == norm(value)
    if group == "تخفیف":
        thr = int(re.search(r"\d+", value).group())
        return (c.get("discount_pct") or 0) >= thr
    if group == "حجم":
        wanted = _volumes(value)
        return bool(wanted) and wanted[0] in _volumes(t)
    if group == "ضد آفتاب SPF":
        n = int(re.search(r"\d+", value).group())
        return any(int(s) >= n for s in SPF_RE.findall(t))
    return False


def _jev_score_semantic(q: str, group: str, value: str, cards: list[dict]) -> dict:
    """یک درخواست دسته‌ای Jev: برای هر محصول noul تطابق با ویژگی. کش می‌شود."""
    key = f"{norm(q)}|{group}|{norm(value)}"
    now = time.time()
    with _lock:
        hit = _jev_cache.get(key)
    cached = dict(hit[1]) if hit and now - hit[0] < CACHE_TTL * 4 else {}
    cached.pop("_error", None)
    cards = [c for c in cards if str(c["id"]) not in cached]
    if not cards:
        return cached
    need = (f"ویژگی اعلام‌شده: «{value}» در دستهٔ «{group}». "
            "محصول باید صریحاً در نام/برند/توضیح خود به این ویژگی اشاره کند "
            "(مثلاً «مناسب پوست چرب»). اشارهٔ مبهم یا نامربوط = نه.")
    questions = {
        str(c["id"]): {
            "type": "noul",
            "instructions": {
                "need": "`need`",
                "product": f"`products.{c['id']}`",
                "question": "با توجه به نام و برند محصول در product، آیا این محصول "
                            "ویژگی اعلام‌شده در need را صریحاً دارد؟ بله=دارد؛ "
                            "نه=ندارد یا نامشخص.",
            },
            "criteria": {"true": "ویژگی صریحاً ذکر شده", "false": "ذکر نشده یا مبهم"},
        } for c in cards
    }
    state_lite = {str(c["id"]): {"title": c["title"], "brand": c.get("brand")} for c in cards}
    scores: dict[str, float] = {}
    try:
        answers = server._jev({"need": need, "products": state_lite}, questions)
        scores = {pid: float((answers.get(pid) or {}).get("noul", 0.0)) for pid in questions}
    except Exception as e:
        scores = {pid: -1.0 for pid in questions}  # خطا => علامت بزن
        scores["_error"] = str(e)[:120]
    with _lock:
        if "_error" not in scores:
            merged = {**cached, **scores}
            _jev_cache[key] = (now, merged)
            return merged
        return {**cached, **scores}


def tiered_rank(q: str, conds: list[tuple[str, str]], n_tiers: int = 3, bypass_jev: bool = False) -> dict:
    """رتبه‌بندی v2 (بیزی شرطی‌شده بر لایهٔ قیمتی + اعتبار برند) روی کاندیداهای
    فیلترشده: اول (چند) فیلتر اعمال می‌شود، بعد داخل هر لایهٔ قیمتی رتبه می‌دهیم."""
    stats = apply_filters(q, conds, bypass_jev=bypass_jev) if conds else \
        {"items": [{k: v for k, v in c.items() if k not in ("_t", "_dl")} for c in get_products(q)],
         "mode": "all", "candidates": len(get_products(q))}
    if stats.get("error"):
        return stats
    cards = [dict(c) for c in stats["items"]
             if c.get("in_stock") and isinstance(c.get("price_toman"), (int, float))
             and c["price_toman"] > 0]
    scored = [c for c in cards if c.get("rating_pct") and c.get("votes")]
    if len(scored) < 3:
        return {"tiers": [], "facets": facets_for(q), "note": "دادهٔ امتیاز کافی برای رتبه‌بندی نیست",
                "mode": stats.get("mode"), "conditions": [{"group": g, "value": v} for g, v in conds],
                "items": cards}
    # --- پرایور هر لایه از آمار خودِ همان لایه (اسکیل rank_v2) ---
    import statistics
    # مبنای لایه‌بندی: قیمت هر ۱۰۰ml/g (دسته‌های حجمی) یا هر عدد (دسته‌های count).
    # تخمین: اگر عمدهٔ استخر حجم داشت، بی‌حجم‌ها ÷۵۰ml فرض می‌شوند؛ وگرنه قیمت کل.
    has_unit = [c for c in scored if c.get("unit_label")]
    vol_mode = has_unit and sum(1 for c in has_unit
                                if "ml" in (c.get("unit_label") or "")
                                or "g" in (c.get("unit_label") or "")) >= len(has_unit) * 0.6
    for c in cards:
        if c.get("unit_price_toman") and c.get("unit_label"):
            c["_cmp"] = c["unit_price_toman"]
            c["unit_est"] = False
        elif vol_mode:
            c["_cmp"] = round(c["price_toman"] * 2)  # فرض ۵۰ml
            c["unit_est"] = True
            c["unit_label"] = "ml"
        else:
            c["_cmp"] = c["price_toman"]
            c["unit_est"] = False
            c["unit_label"] = "عددی"
        c["unit_price_toman"] = c["_cmp"]
    prices = sorted(c["_cmp"] for c in scored)
    cuts = [prices[int(round(k * len(prices) / n_tiers))] for k in range(1, n_tiers)]
    global_mean = statistics.fmean(c["rating_pct"] for c in scored)
    global_m = max(30.0, statistics.median(c["votes"] for c in scored))

    def tidx(p):
        i = 0
        for cu in cuts:
            if p >= cu:
                i += 1
        return i

    buckets: dict[int, list] = {}
    for c in scored:
        buckets.setdefault(tidx(c["_cmp"]), []).append(c)
    priors = {}
    for ti in range(n_tiers):
        b = buckets.get(ti) or []
        if b:
            tv = sum(c["votes"] for c in b)
            priors[ti] = {"mean": sum(c["rating_pct"] * c["votes"] for c in b) / tv,
                          "m": max(30.0, statistics.median(c["votes"] for c in b))}
        else:
            priors[ti] = {"mean": global_mean, "m": global_m}
    by_brand: dict[str, list] = {}
    for c in scored:
        if c.get("brand"):
            by_brand.setdefault(norm(c["brand"]), []).append(c)
    bscore, bconf = {}, {}
    BRAND_M = 200.0  # نظرات لازم تا برند «معتبر» تمام‌وزن حساب شود (شرط بیزی برند)
    for br, grp in by_brand.items():
        n = sum(c["votes"] for c in grp)
        wm = sum(c["rating_pct"] * c["votes"] for c in grp) / n
        bscore[br] = (n * wm + global_m * global_mean) / (n + global_m)
        bconf[br] = n / (n + BRAND_M)

    TIER_NAMES = {1: "اقتصادی", 2: "متوسط", 3: "پرچم‌دار"}
    tiers = []
    for ti in range(n_tiers):
        b = buckets.get(ti) or []
        rows = []
        pr = priors[ti]
        for c in b:
            bayes = (c["votes"] * c["rating_pct"] + pr["m"] * pr["mean"]) / (c["votes"] + pr["m"])
            br = norm(c.get("brand") or "")
            brand = bscore.get(br, global_mean)
            conf = bconf.get(br, 0.0)  # برند کم‌نظر => دلتا عملاً صفر
            final = max(0.0, min(100.0, bayes + 0.60 * (brand - pr["mean"]) * conf))
            r = {k: v for k, v in c.items() if k not in ("_t", "_dl", "_cmp")}
            r.update({"bayes": round(bayes, 1), "score": round(final, 1),
                      "tier": ti + 1})
            rows.append(r)
        rows.sort(key=lambda r: (-r["score"], -r["bayes"]))
        if rows:
            tiers.append({
                "tier": ti + 1,
                "name": TIER_NAMES.get(ti + 1, f"لایه {ti+1}"),
                "range_toman": [min(r["price_toman"] for r in rows),
                                max(r["price_toman"] for r in rows)],
                "unit_range": [min(r["unit_price_toman"] for r in rows),
                               max(r["unit_price_toman"] for r in rows)],
                "prior_mean": round(pr["mean"], 1),
                "items": rows,
            })
    return {"tiers": tiers, "facets": facets_for(q), "mode": stats.get("mode"),
            "conditions": [{"group": g, "value": v} for g, v in conds],
            "candidates": stats.get("candidates"), "count": len(scored)}


def apply_filters(q: str, conds: list[tuple[str, str]], bypass_jev: bool = False) -> dict:
    """OR داخل هر گروه، AND بین گروه‌ها (مثل خود دیجی‌کالا).
    Jev فقط روی کاندیداهای عبورکننده از گیت‌های regex، سقف JEV_MAX در مجموع."""
    cards = get_products(q)
    if not cards:
        return {"items": [], "facets": [], "error": "اول جستجو کنید"}
    direct = [(g, v) for g, v in conds
              if g in ("برند", "حجم", "ضد آفتاب SPF", "تخفیف")]
    sem = [(g, v) for g, v in conds if (g, v) not in direct]
    by_group: dict[str, list[str]] = {}
    for g, v in direct:
        by_group.setdefault(g, []).append(v)

    pool = [c for c in cards
            if all(any(_direct_match(c, g, v) for v in vs)
                   for g, vs in by_group.items())]
    sem_by_group: dict[str, list[str]] = {}
    for g, v in sem:
        sem_by_group.setdefault(g, []).append(v)

    sure_ids, maybe = set(), []
    for c in pool:
        ok, cand = True, False
        for g, vs in sem_by_group.items():
            hit_any, need_jev = False, False
            for v in vs:
                explicit, hint = SEM_PATTERNS.get(g, {}).get(v, ("(نابلد)", ""))
                if re.search(explicit, c["_t"]):
                    hit_any = True
                    break
                if hint and re.search(hint, c["_t"]):
                    need_jev = True
            if not hit_any and need_jev:
                cand = True
            elif not hit_any:
                ok = False
                break
        if not ok:
            continue
        if cand:
            maybe.append(c)
        else:
            sure_ids.add(str(c["id"]))
    maybe = [] if bypass_jev else maybe[:JEV_MAX]
    scores: dict = {}
    jev_error = None
    if maybe:
        scores = _jev_score_multi(q, sem, maybe)
        if "_error" in scores:
            jev_error = str(scores.get("_error"))[:60]
    kept = []
    for c in pool:
        cid = str(c["id"])
        if cid in sure_ids:
            kind, jv = "explicit", 1.0
        else:
            if jev_error:
                continue
            s = scores.get(cid, 0.0)
            if s < 0.5:
                continue
            kind, jv = "jev", round(s, 2)
        cc = {k: v for k, v in c.items() if k not in ("_t", "_dl")}
        cc.update({"match_kind": kind})
        if sem:
            cc["jev_match"] = jv
        kept.append(cc)
    if jev_error and not kept:
        return {"items": [], "facets": facets_for(q),
                "error": f"Jev در دسترس نبود ({jev_error})"}
    kept.sort(key=lambda x: -x.get("jev_match", 1.0))
    mode = "direct" if not sem else ("jev-bypass" if bypass_jev else ("jev-gated" if maybe else "explicit"))
    return {"items": kept, "facets": facets_for(q), "mode": mode,
            "stats": {"explicit_kept": len(sure_ids), "jev_called": len(maybe),
                      "pool": len(pool)},
            "conditions": [{"group": g, "value": v} for g, v in conds],
            "candidates": len(cards)}


def _grouped(conds: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    out: dict[str, list[str]] = {}
    for g, v in conds:
        out.setdefault(g, []).append(v)
    return sorted(out.items())


def _jev_score_multi(q: str, conds: list[tuple[str, str]], cards: list[dict]) -> dict:
    """یک noul با needِ مرکب: محصول باید همهٔ ویژگی‌ها را صریحاً داشته باشد.
    کش با کلید ترتیب‌یافتهٔ شرط‌ها."""
    key = f"multi-v2|{norm(q)}|" + "&".join(sorted(f"{g}:{norm(v)}" for g, v in conds))
    now = time.time()
    with _lock:
        hit = _jev_cache.get(key)
    cached = dict(hit[1]) if hit and now - hit[0] < CACHE_TTL * 4 else {}
    cached.pop("_error", None)
    cards = [c for c in cards if str(c["id"]) not in cached]
    if not cards:
        return cached
    conditions = " + ".join(f"[{' یا '.join(f'«{v}»' for v in vs)}] (در دستهٔ «{g}»)"
                      for g, vs in _grouped(conds))
    need = (f"لیست زیر گروه‌ویژگی‌ها است؛ محصول باید از هر گروه حداقل یکی را "
            "صریحاً در نام/برند/توضیح خود داشته باشد (مثلاً «مناسب پوست چرب»). "
            "کم‌داشتن هر گروه یا اشارهٔ مبهم = نه. اگر دو گزینهٔ یک گروه «یا» داشت، هرکدام کافی است.\n"
            f"شرط‌های انتخابی: {conditions}")
    questions = {
        str(c["id"]): {
            "type": "noul",
            "instructions": {
                "need": "`need`",
                "product": f"`products.{c['id']}`",
                "question": "با توجه به نام و برند محصول در product، آیا این محصول "
                            "همهٔ ویژگی‌های اعلام‌شده در need را صریحاً دارد؟ بله=همه؛ "
                            "نه=حداقل یکی ندارد یا نامشخص.",
            },
            "criteria": {"true": "همهٔ ویژگی‌ها صریحاً ذکر شده",
                         "false": "حداقل یکی ذکر نشده یا مبهم"},
        } for c in cards
    }
    state_lite = {str(c["id"]): {"title": c["title"], "brand": c.get("brand")} for c in cards}
    scores: dict = {}
    try:
        answers = server._jev({"need": need, "products": state_lite}, questions)
        scores = {pid: float((answers.get(pid) or {}).get("noul", 0.0)) for pid in questions}
    except Exception as e:
        scores = {pid: -1.0 for pid in questions}
        scores["_error"] = str(e)[:120]
    with _lock:
        if "_error" not in scores:
            merged = {**cached, **scores}
            _jev_cache[key] = (now, merged)
            return merged
        return {**cached, **scores}


def apply_filter(q: str, group: str, value: str, bypass_jev: bool = False) -> dict:
    return apply_filters(q, [(group, value)], bypass_jev=bypass_jev)
