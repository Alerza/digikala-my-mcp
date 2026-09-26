"""Dependency-free, read-only Khanoumi MCP server (stdio transport)."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


BASE = "https://www.khanoumi.com"
API = BASE + "/api/ntl/v1/products"
HEADERS = {"User-Agent": "KhanoumiMCP/1.0 (+read-only product lookup)", "Accept": "application/json,text/html"}
SEEN = {}


class UpstreamError(Exception):
    pass


def fetch(url: str):
    if urlparse(url).hostname != "www.khanoumi.com" or not url.startswith(BASE + "/"):
        raise ValueError("Only public khanoumi.com URLs are allowed")
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=15) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise UpstreamError(f"Khanoumi request failed: {exc}") from exc


def listing(*, query: str = "", cat_id: int | None = None, page: int = 1, limit: int = 10):
    if not 1 <= page <= 100 or not 1 <= limit <= 24:
        raise ValueError("page must be 1..100 and limit 1..24")
    params = {"page_number": page, "page_size": limit}
    if query:
        params["query"] = query.strip()[:100]
    if cat_id is not None:
        if cat_id < 1:
            raise ValueError("cat_id must be positive")
        params["cat_id"] = cat_id
    payload = json.loads(fetch(API + "?" + urlencode(params)))
    if payload.get("isSuccess") is not True:
        raise UpstreamError("Khanoumi returned an unsuccessful response")
    products = payload.get("data", {}).get("products", {})
    rows = [normalize(item) for item in products.get("items", [])[:limit]]
    for row in rows:
        SEEN[row["id"]] = row
    return {"total": products.get("totalCount"), "page": page, "products": rows}


def normalize(item: dict):
    slug = item.get("slug")
    return {"id": str(item.get("id", "")), "name": item.get("nameFa"),
            "english_name": item.get("nameEn"), "brand": (item.get("brand") or {}).get("nameFa"),
            "base_price": item.get("basePrice"), "effective_price": item.get("effectivePrice"),
            "discount_amount": item.get("discountPrice"), "discount_percent": item.get("discountPercent"),
            "price_unit": "تومان", "in_stock": item.get("hasStock"),
            "image": item.get("imageUrl"), "url": BASE + "/products/" + slug if slug else None}


class ProductMeta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            a = dict(attrs)
            key = a.get("name") or a.get("property")
            if key in ("description", "og:description", "og:title"):
                self.meta[key] = a.get("content")


def product(identifier: str):
    identifier = str(identifier).strip()
    if identifier.isdecimal():
        if not re.fullmatch(r"[1-9]\d{0,9}", identifier):
            raise ValueError("Invalid product ID")
        if identifier not in SEEN:
            raise ValueError("ID not seen yet: search for the product first, or supply its full product URL")
        url = SEEN[identifier]["url"]
    else:
        if identifier.startswith(BASE + "/products/"):
            url = identifier
        elif re.fullmatch(r"[a-zA-Z0-9-]{3,150}-\d{1,10}", identifier):
            url = BASE + "/products/" + identifier
        else:
            raise ValueError("Supply a product ID from a prior search, full Khanoumi URL, or product slug")
        if not re.fullmatch(re.escape(BASE) + r"/products/[a-zA-Z0-9-]{3,150}-\d{1,10}/?", url):
            raise ValueError("Invalid product URL")
    product_id = re.search(r"-(\d{1,10})/?$", url).group(1)
    found = dict(SEEN.get(product_id) or {"id": product_id, "url": url, "price_unit": "تومان"})
    parser = ProductMeta()
    parser.feed(fetch(url))
    found["name"] = found.get("name") or parser.meta.get("og:title")
    found["description"] = parser.meta.get("description")
    return found


def compare(ids: list):
    if not isinstance(ids, list) or not 2 <= len(ids) <= 5:
        raise ValueError("Provide 2 to 5 product IDs")
    return {"products": [product(i) for i in ids]}


TOOLS = [
    {"name": "search_products", "description": "Search Khanoumi products by Persian or English term; current prices in toman.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}},
    {"name": "browse_category", "description": "List Khanoumi products by numeric category ID.",
     "inputSchema": {"type": "object", "properties": {"cat_id": {"type": "integer"}, "page": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 10}}, "required": ["cat_id"]}},
    {"name": "get_product", "description": "Look up a Khanoumi product by URL/slug, or ID from a previous search. The public page may not supply price.",
     "inputSchema": {"type": "object", "properties": {"identifier": {"type": "string"}}, "required": ["identifier"]}},
    {"name": "compare_products", "description": "Compare 2 to 5 product URLs/slugs or IDs from a previous search.",
     "inputSchema": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 5}}, "required": ["ids"]}},
]


def dispatch(msg):
    method = msg.get("method")
    if method == "initialize":
        return {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "khanoumi-mcp", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = msg.get("params") or {}
        args = params.get("arguments") or {}
        name = params.get("name")
        try:
            if name == "search_products":
                if not isinstance(args.get("query"), str) or not args["query"].strip():
                    raise ValueError("query is required")
                value = listing(query=args["query"], page=args.get("page", 1), limit=args.get("limit", 10))
            elif name == "browse_category":
                value = listing(cat_id=args["cat_id"], page=args.get("page", 1), limit=args.get("limit", 10))
            elif name == "get_product":
                value = product(args["identifier"])
            elif name == "compare_products":
                value = compare(args["ids"])
            else:
                raise ValueError("Unknown tool")
            return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
        except (ValueError, KeyError, TypeError, UpstreamError, json.JSONDecodeError) as exc:
            return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
    return None


def main():
    for line in sys.stdin:
        try:
            msg = json.loads(line)
            result = dispatch(msg)
            if "id" in msg:
                if result is None:
                    response = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "Method not found"}}
                else:
                    response = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
                print(json.dumps(response, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(f"MCP input error: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
