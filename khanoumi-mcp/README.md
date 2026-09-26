# Khanoumi MCP server

Read-only MCP server for public product information on [Khanoumi](https://www.khanoumi.com/). Python 3.10+; no third-party packages or credentials required. It runs locally using MCP `stdio` (one JSON-RPC message per line).

## Tools

| Tool | Purpose |
| --- | --- |
| `search_products(query, page=1, limit=10)` | Search Persian or English text; returns IDs, prices, stock, product links. |
| `browse_category(cat_id, page=1, limit=10)` | Browse a numeric Khanoumi category ID. |
| `get_product(identifier)` | Return public page description from a product URL or slug; an ID works after a search in the same session. |
| `compare_products(ids)` | Compare 2–5 URLs, slugs, or previously searched IDs. |

Prices from Khanoumi's public listing API are labeled **toman**. `base_price` is the original price; `effective_price` is the current price; `discount_amount` is an amount, not the sale price. Verify a price on the linked product page before purchase. A standalone product URL provides title and description; prices appear only when the product has also appeared in a search or category result in this server process. Category IDs are site identifiers (for example `27`); this server does not maintain a category catalog.

## Configure

Copy the `khanoumi-mcp` directory locally. Add to an MCP client configuration, replacing the path with your absolute path:

```json
{
  "mcpServers": {
    "khanoumi": {
      "command": "python3",
      "args": ["/absolute/path/to/khanoumi-mcp/server.py"]
    }
  }
}
```

The server reads public pages and the public `/api/ntl/v1/products` endpoint. Khanoumi can change that endpoint, the response format, or access controls. Requests use a 15-second timeout; failures are returned as MCP tool errors. There is no checkout, account access, or background scraping. Pagination and result size are bounded.

## Test

```sh
python3 -m unittest discover -s tests -v
```

For a live smoke test, run `python3 tests/live_smoke.py` from this directory. It calls the public website and will fail if access to Khanoumi is blocked.
