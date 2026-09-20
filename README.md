# Digikala My MCP

سرور MCP (Model Context Protocol) برای دیجی‌کالا — **فقط‌خواندنی**، بدون نیاز به کلید API.

۸ ابزار: جستجو، پیمایش دسته، جزئیات، مشخصات فنی، نظرات خریداران، سؤالات، خلاصهٔ نظرات و فیلترها. قیمت‌ها به **تومان**.

## ابزارها (۸)

| ابزار | کار |
|---|---|
| `search_digikala` | جستجوی محصول با کوئری فارسی — کارت فشرده (قیمت، امتیاز، رأی، لینک)، پشتیبانی صفحه‌بندی |
| `browse_category` | پیمایش دستهٔ رسمی با slug (`sunscreen-cream`، `mobile-phone` و...) + فیلتر قیمت تومانی + مرتب‌سازی + صفحه‌بندی |
| `product_details` | جزئیات کامل یک dkp: قیمت، گارانتی، فروشنده، امتیاز، موجودی |
| `product_specs` | مشخصات فنی گروه‌بندی‌شده (SPF، جنس، ابعاد و...) — تا ۶۰ ویژگی |
| `product_reviews` | نظرات خریداران + خلاصهٔ امتیازهای زیرمجموعه؛ فیلتر `rate` (۱-۵) و `buyers_only` |
| `product_questions` | سؤالات خریدارها + جواب‌ها |
| `product_overview` | خلاصهٔ AI دیجی‌کالا (comments_overview) + امتیازها + پیش‌نمایش نظرها |
| `search_filters` | برندها/دسته‌های مرتبط با یک کوئری (id + code) |

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

## ساختار

```
server.py       # سرور FastMCP — ۸ ابزار
mini_client.py  # تست stdio با JSON-RPC دستی
```

## محدودیت‌ها

- فقط‌خواندنی — هیچ ابزاری سبد خرید/سفارش/حساب ندارد
- API دیجی‌کالا مستند نیست و ممکن است تغییر کند
- هر دو ابزار `readOnlyHint`‌اند، بدون ذخیرهٔ دادهٔ کاربر

## لایسنس

MIT
