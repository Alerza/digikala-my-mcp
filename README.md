# Digikala My MCP

سرور MCP (Model Context Protocol) برای دیجی‌کالا — **فقط‌خواندنی**، بدون نیاز به کلید API.

۱۲ ابزار — جستجو (با فیلتر قیمت)، پیمایش دسته، جزئیات، مشخصات فنی، نظرات خریداران (فیلتر امتیاز/خریدار)، سؤالات، خلاصهٔ AI نظرات، فیلترها (برند/دسته)، batch تا ۱۰ محصول، مقایسهٔ محصولات (فقط تفاوت‌ها)، شگفت‌انگیز، پرفروش‌ترین‌ها. قیمت‌ها به **تومان**.

## ابزارها

۱۲ ابزار: `search_digikala` (با فیلتر قیمت)، `browse_category` (پیمایش دسته با slug + sort)، `product_details`، `product_specs`، `product_reviews` (فیلتر امتیاز/خریدار)، `product_questions`، `product_overview` (خلاصهٔ AI نظرات)، `get_products_batch` (۱۰ id تکجا)، `compare_products` (فقط مشخصات متفاوت)، `incredible_offers` (شگفت‌انگیز)، `best_selling` (پرفروش‌های کل سایت یا دسته)، `search_filters` (برندها/دسته‌ها).

## اتصال به هرمس (یا هر کلاینت stdio MCP)

در `~/.hermes/config.yaml`:

```yaml
mcp:
  servers:
    digikala-my:
      command: /path/to/digikala-my-mcp/.venv/bin/python
      args:
        - /path/to/digikala-my-mcp/server.py
      enabled: true
```

## نصب محلی

```bash
git clone https://github.com/Alerza/digikala-my-mcp.git
cd digikala-my-mcp
python3 -m venv .venv
.venv/bin/pip install "mcp[cli]" httpx
# تست:
./.venv/bin/python - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location('server','server.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print([t.name for t in m.mcp._tool_manager.list_tools()])
PY
```

## نکته‌های API دیجی‌کالا (کشف‌شده با تست)

- **sort‑های معتبر** (به‌غیر از این‌ها دیجی‌کالا بی‌صدا 404 می‌دهد — حتی 0!):
  `1` پیشفرض · `4` ارزان‌ترین · `7` پرفروش‌ترین · `20` بیشترین تخفیف · `21` گران‌ترین · `22` امتیاز
- **قیمت در API ریال است** — برای تومان ×۱۰ تقسیم (در کد انجام می‌شود)
- Endpoint نظرات: `/v1/product/{id}/comments/` (نه v2 و نه `/reviews`)
- خلاصهٔ AI نظرات: فیلد `comments_overview.overview` در `/v2/product/{id}/`
- فیلتر برند با `brands[0]=...` کار نمی‌کند
- Endpoint تاریخچهٔ قیمت موجود نیست (فقط flag `has_price_chart`)
- فیلتر قیمت در plain search فقط با فرمت bracket `price[min]=..&price[max]=..` (فرمت dash `min-max` بی‌صدا فیلتر نمی‌کند!)
- `page_size`/`limit` در `/v1/search/` نادیده گرفته می‌شوند (همیشه ۲۰ نتیجه) — برش سمت کلاینت
- پاسخ `/v2/product/{id}/` ساختار `{status, data:{product}}` دارد — حتماً `data.product` unwrap شود
- دسته فقط slug متنی می‌پذیرد (id عددی 404 می‌دهد)؛ slug را از breadcrumb محصول بگیر

## ساختار

```
server.py       # سرور FastMCP — ۱۲ ابزار
mini_client.py  # تست stdio با JSON-RPC دستی
```

## محدودیت‌ها

- فقط‌خواندنی — هیچ ابزاری سبد خرید/سفارش/حساب ندارد
- API دیجی‌کالا مستند نیست و ممکن است تغییر کند
- هر دو ابزار `readOnlyHint`‌اند، بدون ذخیرهٔ دادهٔ کاربر

## لایسنس

MIT
