# Digikala My MCP

سرور MCP (Model Context Protocol) برای دیجی‌کالا — **فقط‌خواندنی**، بدون نیاز به کلید API.

۱۲ ابزار — جستجو (با فیلتر قیمت)، پیمایش دسته، جزئیات، مشخصات فنی، نظرات خریداران (فیلتر امتیاز/خریدار)، سؤالات، خلاصهٔ AI نظرات، فیلترها (برند/دسته)، batch تا ۱۰ محصول، مقایسهٔ محصولات (فقط تفاوت‌ها)، شگفت‌انگیز، پرفروش‌ترین‌ها. قیمت‌ها به **تومان**.

## ابزارها

۱۲ ابزار: `search_digikala` (با فیلتر قیمت)، `browse_category` (پیمایش دسته با slug + sort)، `product_details`، `product_specs`، `product_reviews` (فیلتر امتیاز/خریدار)، `product_questions`، `product_overview` (خلاصهٔ AI نظرات)، `get_products_batch` (۱۰ id تکجا)، `compare_products` (فقط مشخصات متفاوت)، `incredible_offers` (شگفت‌انگیز)، `best_selling` (پرفروش‌های کل سایت یا دسته)، `search_filters` (برندها/دسته‌ها).

## اتصال به کلاینت


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
