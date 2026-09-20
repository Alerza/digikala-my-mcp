"""
Digikala MCP server — phase 1 (stdio)
مفاهیم: FastMCP، ابزار (tool)، docstring = schema برای LLM، خطای صادقانه، readOnlyHint
اجرا:  .venv/bin/python server.py   (stdio — کلاینت خودش لانچش می‌کند)
"""
import httpx
from mcp.server.fastmcp import FastMCP

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
def search_digikala(query: str, page: int = 1, page_size: int = 10) -> str:
    """جستجوی محصول در دیجی‌کالا. query را فارسی بده (مثلاً «گوشی سامسونگ»).
    خروجی: لیست کارت‌های فشرده با قیمت تومان، امتیاز و لینک."""
    data = _get(f"{API}/search/", {"q": query, "page": page, "page_size": min(page_size, 30)})
    items = data.get("data", {}).get("products", [])
    if not items:
        return json_dumps({"query": query, "items": [], "note": "نتیجه‌ای نبود — کوئری را کوتاه‌تر کن"})
    cards = [_card(p) for p in items]
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
    prod = data.get("product") or {}
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
    prod = data.get("product") or {}
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
    prod = data.get("product") or {}
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

def json_dumps(x) -> str:
    import json
    return json.dumps(x, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # transport=stdio پیش‌فرض: JSON-RPC از stdin به stdout
    mcp.run()
