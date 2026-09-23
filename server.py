"""
Digikala MCP server — phase 1 (stdio)
مفاهیم: FastMCP، ابزار (tool)، docstring = schema برای LLM، خطای صادقانه، readOnlyHint
اجرا:  .venv/bin/python server.py   (stdio — کلاینت خودش لانچش می‌کند)
"""
import json
import os
import concurrent.futures as _futures
import httpx
from mcp.server.fastmcp import FastMCP


# ---------- TypeSafe Jev (typed judgments; خروجی توکن رایگان، ورودی ~$0.042/M) ----------
JEV_URL = "https://api.typesafe.ai/v1/systemone"
_KEY_FILES = (os.path.expanduser("~/.hermes/.env"), os.path.join(os.path.dirname(__file__), ".env"))


def _jev_key() -> str | None:
    """کلید از env پروسه وگرنه از فایل‌های .env — هیچ‌جا هارد/کامیت نمی‌شود."""
    k = os.environ.get("TYPESAFE_API_KEY")
    if k:
        return k.strip()
    for path in _KEY_FILES:
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("TYPESAFE_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            continue
    return None


def _jev(state, questions: dict) -> dict:
    """یک POST به System One; برمی‌گرداند dict پاسخ‌ها. خطا -> استثنا با پیام صادقانه."""
    key = _jev_key()
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY یافت نشد (env یا ~/.hermes/.env)")
    r = httpx.post(JEV_URL, json={"state": state, "model": "jev-latest", "questions": questions},
                   headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"jev HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("answers", {})


def _bayes(rating_pct, votes) -> float:
    """بتا ۵٪ پایین‌bound با پیشین Beta(11,11) — بدون scipy، فرم بسته."""
    if not rating_pct or not votes:
        return 0.5
    up = votes * rating_pct / 100.0
    return (11 + up) / (22 + votes)

mcp = FastMCP(
    "digikala-my",          # نام سرور — در initialize برمی‌گردد
    instructions="دیجی‌کالا: جستجو، جزئیات و قیمت به تومان. فقط‌خواندنی.",
)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
API = "https://api.digikala.com/v1"
API2 = "https://api.digikala.com/v2"

# مرتب‌سازی‌های معتبر دیجی‌کالا (کمکی برای مستندسازی در docstring)
SORTS = {
    "default": 1, "rotation": 1, "cheap": 4, "expensive": 21,
    "bestselling": 7, "rating": 22, "discount": 20,
}


def _get(url: str, params: dict | None = None) -> dict:
    """یک GET با backoff دستی — الگوی خطای صادقانه مثل digikala-mcp"""
    last = "unknown"
    for attempt in range(3):
        try:
            r = httpx.get(url, params=params, headers={"User-Agent": UA},
                          timeout=20, follow_redirects=True)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:200]
    raise RuntimeError(f"digikala API unreachable after 3 tries: {last}")


def _card(p: dict) -> dict:
    """کارت فشرده محصول — مفهوم: خروجی کم‌حجم برای context اَنجنت"""
    dv = p.get("default_variant") or {}
    price = dv.get("price") or {}
    rating = p.get("rating") or {}
    seller = (dv.get("seller") or {})
    return {
        "id": p.get("id"),
        "title": p.get("title_fa"),
        "price_toman": round(price.get("selling_price", 0) / 10),
        "rrp_toman": round(price.get("rrp_price", 0) / 10) or None,
        "discount_pct": price.get("discount_percent") or 0,
        "rating_pct": rating.get("rate"),        # دیجی‌کالا امتیاز را 0-100 می‌دهد
        "votes": rating.get("count"),
        "stock": price.get("marketable_stock"),
        "in_stock": (p.get("status") == "marketable"),
        "seller": seller.get("title_fa") or None,
        "url": f"https://www.digikala.com/product/dkp-{p.get('id')}/",
    }


@mcp.tool()
def search_digikala(
    query: str, page: int = 1, page_size: int = 10,
    min_price_toman: int | None = None, max_price_toman: int | None = None,
) -> str:
    """جستجوی محصول در دیجی‌کالا. query را فارسی بده (مثلاً «گوشی سامسونگ»).
    فیلتر بازهٔ قیمت (تومان) اختیاری. خروجی: کارت‌های فشرده با قیمت تومان، امتیاز و لینک."""
    params: dict = {"q": query, "page": page}
    if min_price_toman:
        params["price[min]"] = min_price_toman * 10
    if max_price_toman:
        params["price[max]"] = max_price_toman * 10
    data = _get(f"{API}/search/", params)
    items = data.get("data", {}).get("products", [])
    if not items:
        return json_dumps({"query": query, "items": [], "note": "نتیجه‌ای نبود — کوئری را کوتاه‌تر کن"})
    cards = [_card(p) for p in items]
    if page_size and page_size < len(cards):
        cards = cards[:page_size]
    pager = data.get("data", {}).get("pager", {})
    return json_dumps({
        "query": query, "page": page,
        "total_estimate": pager.get("total"),
        "items": cards,
    })


@mcp.tool()
def product_details(product_id: int) -> str:
    """جزئیات کامل یک محصول با dkp id (عدد بعد از dkp- در لینک دیجی‌کالا).
    قیمت، گارانتی، فروشنده، امتیاز و موجودی."""
    data = _get(f"{API2}/product/{product_id}/")
    prod = ((data.get("data") or {}).get("product")) or data.get("product") or {}
    if not prod.get("id"):
        return json_dumps({"error": f"id {product_id} در دیجی‌کالا نیست — عدد dkp معتبر بده", "id": product_id})
    return json_dumps(_card(prod))


def _brand_id(prod: dict) -> dict:
    """برند محصول از data_layer یا brand مستقیم."""
    dl = (prod.get("data_layer") or {})
    return {
        "brand": dl.get("brand") or (prod.get("brand") or {}).get("title_fa"),
        "category_path": (prod.get("breadcrumb") or [{}]),
    }


def _spec_items(prod: dict) -> list[dict]:
    """مشخصات فنی گروه‌بندی‌شده (حداکثر ۶۰ ویژگی برای context کم)."""
    out = []
    for grp in (prod.get("specifications") or [])[:4]:
        for a in (grp.get("attributes") or [])[:15]:
            out.append({"title": a.get("title"), "values": a.get("values")})
        if len(out) >= 60:
            break
    return out[:60]


@mcp.tool()
def product_specs(product_id: int) -> str:
    """مشخصات فنی کامل یک محصول با dkp id — گروه‌بندی‌شده (ماندگاری، جنس، ابعاد و...)."""
    data = _get(f"{API2}/product/{product_id}/")
    prod = ((data.get("data") or {}).get("product")) or data.get("product") or {}
    if not prod.get("id"):
        return json_dumps({"error": f"id {product_id} معتبر نیست", "id": product_id})
    return json_dumps({
        "id": product_id,
        "title": prod.get("title_fa"),
        "brand": _brand_id(prod)["brand"],
        "category": [(b.get("title") or "") for b in (prod.get("breadcrumb") or [])],
        "specs": _spec_items(prod),
    })


@mcp.tool()
def browse_category(
    category_slug: str, page: int = 1,
    min_price_toman: int | None = None, max_price_toman: int | None = None,
    sort: str = "default",
) -> str:
    """پیمایش دستهٔ رسمی دیجی‌کالا با slug (مثلاً «sunscreen-cream»، «sunscreen-cream» نوع آفافت).
    فیلتر قیمت (تومان)، مرتب‌سازی (cheap/expensive/bestselling/rating/discount) و صفحه‌بندی.
    slug را از search_filters یا از breadcrumb محصولات بگیر."""
    params: dict = {"page": page}
    if sort != "default":
        params["sort"] = SORTS.get(sort, sort)
    if min_price_toman:
        params["price[min]"] = min_price_toman * 10
    if max_price_toman:
        params["price[max]"] = max_price_toman * 10
    data = _get(f"{API}/categories/{category_slug}/search/", params)
    d = data.get("data") or {}
    items = [_card(p) for p in (d.get("products") or [])]
    pager = d.get("pager") or {}
    # برندهای موجود در این دسته (برای شناخت برند از آپشن‌های فیلتر)
    brand_opts = (d.get("filters") or {}).get("brands", {})
    if isinstance(brand_opts, dict):
        brand_opts = brand_opts.get("options") or []
    return json_dumps({
        "category": category_slug, "page": page, "sort": sort,
        "total_items": pager.get("total_items") or pager.get("total"),
        "total_pages": pager.get("total_pages"),
        "products_on_page": len(items),
        "brands_sample": [{"id": b.get("id"), "title": b.get("title_fa"), "code": b.get("code")}
                          for b in brand_opts[:20]],
        "items": items,
    })


@mcp.tool()
def search_filters(query: str) -> str:
    """برندها و فیلترها برای یک کوئری — فهرست id و code برندها، دسته‌ها، بازهٔ قیمت.
    برای پیدا کردن category slug و برندهای مرتبط با یک موضوع."""
    data = _get(f"{API}/search/", {"q": query})
    d = data.get("data") or {}
    filters = d.get("filters") or {}
    brands = (filters.get("brands") or {}).get("options") or []
    cats = (filters.get("categories") or {}).get("options") or []
    pager = d.get("pager") or {}
    return json_dumps({
        "query": query,
        "total_items": pager.get("total_items") or pager.get("total"),
        "brands": [{"id": b.get("id"), "title": b.get("title_fa"), "code": b.get("code")} for b in brands[:30]],
        "categories": [{"id": c.get("id"), "title": c.get("title_fa"), "code": c.get("code")} for c in cats[:20]],
    })


@mcp.tool()
def product_reviews(product_id: int, page: int = 1, rate: int | None = None,
                    buyers_only: bool = True) -> str:
    """نظرات خریداران یک محصول با dkp id — متن، امتیاز، تاریخ، معایب/مزایا.
    rate برای فیلتر امتیاز (۱-۵)، buyers_only فقط خریداران واقعی."""
    params: dict = {"page": page}
    if rate:
        params["rate"] = rate
    if buyers_only:
        params["is_buyer"] = 1
    data = _get(f"{API}/product/{product_id}/comments/", params)
    d = data.get("data") or {}
    comments = []
    for c in (d.get("comments") or [])[:20]:
        comments.append({
            "rate": c.get("rate"),
            "title": c.get("title"),
            "body": (c.get("body") or "")[:400],
            "created": c.get("created_at"),
            "is_buyer": c.get("is_buyer"),
            "advantages": c.get("advantages"),
            "disadvantages": c.get("disadvantages"),
            "likes": (c.get("reactions") or {}).get("likes"),
        })
    pager = d.get("pager") or {}
    return json_dumps({
        "product_id": product_id, "page": page, "filter_rate": rate,
        "buyer_only": buyers_only,
        "total_comments": pager.get("total_items"),
        "total_pages": pager.get("total_pages"),
        "ratings_summary": d.get("ratings"),
        "comments_on_page": len(comments),
        "comments": comments,
    })


@mcp.tool()
def product_questions(product_id: int, page: int = 1) -> str:
    """سؤالات خریدارها دربارهٔ یک محصول با dkp id — متن سؤال + تعداد جواب‌ها."""
    data = _get(f"{API}/product/{product_id}/questions/", {"page": page})
    d = data.get("data") or {}
    qs = []
    for q in (d.get("questions") or [])[:20]:
        qs.append({
            "body": (q.get("body") or "")[:300],
            "answers": [a.get("body", "")[:200] for a in (q.get("answers") or [])[:3]],
            "answer_count": len(q.get("answers") or []),
            "created": q.get("created_at"),
        })
    pager = d.get("pager") or {}
    return json_dumps({
        "product_id": product_id, "page": page,
        "total_questions": pager.get("total_items"),
        "questions_on_page": len(qs),
        "questions": qs,
    })


@mcp.tool()
def product_overview(product_id: int) -> str:
    """نمای کلی نظرات محصول — خلاصهٔ AI دیجی‌کالا (comments_overview)، امتیازهای زیرمجموعه، و نمونهٔ نظرها.
    برای قضاوت سریع «کیفیت در مقابل قیمت» بدون خواندن همه‌ی نظرات."""
    data = _get(f"{API2}/product/{product_id}/")
    prod = ((data.get("data") or {}).get("product")) or data.get("product") or {}
    if not prod.get("id"):
        return json_dumps({"error": f"id {product_id} معتبر نیست", "id": product_id})
    rating = prod.get("rating") or {}
    ov = (prod.get("comments_overview") or {}).get("overview")
    return json_dumps({
        "id": product_id,
        "title": prod.get("title_fa"),
        "brand": _brand_id(prod)["brand"],
        "rating_rate": rating.get("rate"),
        "rating_count": rating.get("count"),
        "comments_count": prod.get("comments_count"),
        "questions_count": prod.get("questions_count"),
        "ai_overview": (ov or "")[:800],
        "last_comments_preview": [
            {"rate": c.get("rate"), "body": (c.get("body") or "")[:200], "is_buyer": c.get("is_buyer")}
            for c in (prod.get("last_comments") or [])[:5]
        ],
        "has_price_chart": prod.get("has_price_chart"),
    })


def _spec_flat(prod: dict) -> dict:
    """مشخصات به دیکشنری تخت (title → values join شده) برای مقایسه."""
    flat = {}
    for grp in (prod.get("specifications") or []):
        for a in (grp.get("attributes") or []):
            key = a.get("title")
            if not key:
                continue
            vals = a.get("values") or []
            # values ممکنه لیست رشته یا لیست dict باشد
            joined = ", ".join(
                (v.get("value") if isinstance(v, dict) else str(v)).strip()
                for v in vals if v
            )
            flat[key] = joined
    return flat


@mcp.tool()
def get_products_batch(product_ids: list[int]) -> str:
    """کارت فشردهٔ حداکثر ۱۰ محصول با لیست dkp id — برای پیش‌فرض مقایسه.
    خطای هر id جداگانه گزارش می‌شود؛ بقیه به‌کار ادامه می‌دهند."""
    product_ids = list(dict.fromkeys(product_ids))[:10]
    out = []
    for pid in product_ids:
        try:
            d = _get(f"{API2}/product/{pid}/")
            prod = ((d.get("data") or {}).get("product")) or d.get("product") or {}
            out.append(_card(prod) if prod.get("id") else {"id": pid, "error": "پیدا نشد"})
        except Exception as e:
            out.append({"id": pid, "error": str(e)[:120]})
    return json_dumps({"count": len(out), "items": out})


@mcp.tool()
def compare_products(product_ids: list[int]) -> str:
    """مقایسهٔ ۲ تا ۵ محصول با dkp id — فقط مشخصاتی که واقعاً بینشان فرق دارد.
    قیمت/امتیاز/برند همیشه گزارش می‌شود؛ مشخصات فنی فقط تمایزها."""
    product_ids = list(dict.fromkeys(product_ids))[:5]
    if len(product_ids) < 2:
        return json_dumps({"error": "حداقل ۲ id لازم است"})
    items, flats = [], []
    for pid in product_ids:
        try:
            prod = (((_get(f"{API2}/product/{pid}/").get("data") or {}).get("product"))) or {}
        except Exception as e:
            return json_dumps({"error": f"id {pid}: {str(e)[:120]}"})
        if not prod.get("id"):
            return json_dumps({"error": f"id {pid} در دیجی‌کالا نیست"})
        c = _card(prod)
        items.append(c)
        flats.append((pid, _spec_flat(prod)))
    attrs: dict = {}
    for key in {k for _, f in flats for k in f}:
        vals = {pid: f.get(key, "") for pid, f in flats}
        if len(set(vals.values())) > 1:
            attrs[key] = {str(pid): v for pid, v in vals.items()}
    return json_dumps({
        "products": items,
        "differing_specs": attrs,
    })


@mcp.tool()
def incredible_offers(page: int = 1) -> str:
    """پیشنهادهای شگفت‌انگیز امروز دیجی‌کالا — محصولاتی با بزرگ‌ترین تخفیف فعال.
    خروجی: لیست کارت فشرده + خوب‌باد از sub-لیست‌های (incredible / running_out / digiplus)."""
    data = _get(f"{API}/incredible-offers/", {"page": page})
    d = data.get("data") or {}
    main = d.get("incredible_products_list") or {}
    items = [_card(p) for p in (main.get("products") or [])]
    running_out = [_card(p) for p in (d.get("running_out_incredible_products") or {}).get("products", [])][:5]
    return json_dumps({
        "page": page,
        "total_estimate": (main.get("pager") or {}).get("total"),
        "items": items,
        "running_out_soon": running_out,
    })


@mcp.tool()
def best_selling(category_slug: str | None = None, page: int = 1) -> str:
    """پرفروش‌ترین‌های کل سایت دیجی‌کالا (یا یک دسته با slug) — با رتبهٔ جهانی.
    برای اطلاع «چه چیزی الان در ایران مخوب است».
    نکته: پارامتر category فقط slug متنی می‌پذیرد (id عددی 404 می‌دهد)."""
    if category_slug:
        data = _get(f"{API}/categories/{category_slug}/search/", {"page": page, "sort": 7})
    else:
        data = _get(f"{API}/best-selling/", {"page": page})
    d = data.get("data") or {}
    items = [_card(p) for p in (d.get("products") or [])]
    pager = d.get("pager") or {}
    return json_dumps({
        "category": category_slug, "page": page,
        "total_estimate": pager.get("total_items") or pager.get("total"),
        "items": items,
    })

@mcp.tool()
def smart_pick(query: str, need: str, max_items: int = 3,
               min_price_toman: int | None = None, max_price_toman: int | None = None,
               page_size: int = 20) -> str:
    """انتخاب هوشمند محصول: جستجو + قضاوت مدل Jev (تطابق با need) داخل سرور،
    و فقط چند کارت برتر برگردانده می‌شود — مصرف توکن context کلاینت کم می‌شود.
    query: کلمه کلیدی فارسی. need: توضیح طبیعی نیاز («ضدآفتاب رنگی مناسب پوست چرب، زیر ۵۰۰ هزار»).
    امتیاز نهایی = احتمال تطابق Jev × رتبه‌بندی بیزی امتیاز/نظرات. بدون کلید API،
    به رتبه‌بندی بیزیِ خالی برمی‌گردد (note:jev-off)."""
    params: dict = {"q": query, "page": 1}
    if min_price_toman:
        params["price[min]"] = min_price_toman * 10
    if max_price_toman:
        params["price[max]"] = max_price_toman * 10
    data = _get(f"{API}/search/", params)
    d = data.get("data") or {}
    prods = (d.get("products") or [])[:page_size]
    if not prods:
        return json_dumps({"query": query, "items": [], "note": "نتیجه‌ای نبود — کوئری را کوتاه‌تر کن"})
    cards = {str(p["id"]): _card(p) for p in prods if p.get("id")}
    state_lite = {pid: {"title": c["title"], "brand_price_rating":
                        f"{c['price_toman']} تومان، امتیاز {c.get('rating_pct')} از {c.get('votes')} نظر"}
                  for pid, c in cards.items()}
    jev_note = "jev-off"
    try:
        questions = {
            pid: {"type": "noul",
                  "instructions": {
                      "need": "`need`",
                      "product": f"`products.{pid}`",
                      "question": "با توجه به نام و برند محصول در product، آیا این محصول "
                                  "نیاز اعلام‌شده در need را برآورده می‌کند؟ بله=محصول "
                                  "مناسب یا جایگزین نزدیک؛ نه=دسته/ویژگی اشتباه."},
                  "criteria": {"true": "تطابق مستقیم یا بسیار نزدیک با need",
                               "false": "دسته، ویژگی یا کاربرد نامرتبط"}}
            for pid in cards
        }
        answers = _jev({"need": need, "products": state_lite}, questions)
        scores = {pid: float((answers.get(pid) or {}).get("noul", 0.0)) for pid in cards}
        jev_note = "jev-on"
    except Exception as e:
        scores = {pid: 0.5 for pid in cards}
        jev_note = f"jev-fallback ({str(e)[:80]})"
    ranked = sorted(
        ({"jev_match": round(scores[pid], 3),
          "bayes": round(_bayes(c.get("rating_pct"), c.get("votes")), 3),
          "final": round((scores[pid] * _bayes(c.get("rating_pct"), c.get("votes"))) * (1 if c.get("in_stock") else 0.3), 3),
          **c}
         for pid, c in cards.items() if scores[pid] > 0),
        key=lambda x: x["final"], reverse=True)
    return json_dumps({
        "query": query, "need": need, "mode": jev_note,
        "candidates_scanned": len(cards),
        "items": ranked[:max(1, min(max_items, 10))],
        "runner_up_ids": [c["id"] for c in ranked[max(1, min(max_items, 10)):max(6, max_items * 2)]],
    })


@mcp.tool()
def cheap_details(product_ids: list[int]) -> str:
    """همان get_products_batch اما خروجی تک‌خطی/فشرده‌تر (بدون indent) — توکن کمتر.
    برای وقتی که فقط قیمت/موجودی/لینک چند id لازم است."""
    r = json.loads(get_products_batch(product_ids))
    compact = []
    for it in r.get("items", []):
        compact.append({k: v for k, v in it.items()
                        if k in ("id", "title", "price_toman", "discount_pct", "rating_pct", "votes", "in_stock", "error")})
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"), default=str)


def json_dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # transport=stdio پیش‌فرض: JSON-RPC از stdin به stdout
    mcp.run()
