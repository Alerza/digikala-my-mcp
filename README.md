# Digikala My MCP

سرور MCP (Model Context Protocol) برای دیجی‌کالا — **فقط‌خواندنی**، بدون نیاز به کلید API.

۱۲ ابزار — جستجو (با فیلتر قیمت)، پیمایش دسته، جزئیات، مشخصات فنی، نظرات خریداران (فیلتر امتیاز/خریدار)، سؤالات، خلاصهٔ AI نظرات، فیلترها (برند/دسته)، batch تا ۱۰ محصول، مقایسهٔ محصولات (فقط تفاوت‌ها)، شگفت‌انگیز، پرفروش‌ترین‌ها. قیمت‌ها به **تومان**.

## ابزارها

۱۴ ابزار: `search_digikala` (با فیلتر قیمت)، `browse_category` (پیمایش دسته با slug + sort)، `product_details`، `product_specs`، `product_reviews` (فیلتر امتیاز/خریدار)، `product_questions`، `product_overview` (خلاصهٔ AI نظرات)، `get_products_batch` (۱۰ id تکجا)، `compare_products` (فقط مشخصات متفاوت)، `incredible_offers` (شگفت‌انگیز)، `best_selling` (پرفروش‌های کل سایت یا دسته)، `search_filters` (برندها/دسته‌ها)، **`smart_pick`** (جستجو + قضاوت تطابق TypeSafe Jev داخل سرور، فقط ۳ کارت برتر برمی‌گردد — توکن context کم)، **`cheap_details`** (batch با خروجی فشردهٔ تک‌خطی).

### smart_pick و TypeSafe Jev
- `smart_pick(query, need)` تا ۲۰ کاندید را با یک درخواست Noul به `api.typesafe.ai` می‌سنجد
  (مدل jev-latest؛ خروجی توکن Jev رایگان، ورودی ~$۰.۰۴۲/M توکن) و با رتبهٔ بیزی ترکیب می‌کند.
- کلید از `TYPESAFE_API_KEY` (env یا `~/.hermes/.env` یا `.env` محلی — هر دو `.gitignore` هستند).
  **کلید هرگز در ریپو کامیت/پوش نمی‌شود.** بدون کلید، ابزار به رتبهٔ بیزی خالی برمی‌گردد (`mode: jev-off`).

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


## وب‌اپ جستجو (app.py + facets.py)

یک رابط وب فارسی/RTL روی همان منطق سرور — بدون LLM، فقط regex + Jev + آمار بیزی:

- **جستجو** با صفحه‌بندی دیجی‌کالا + چیپ‌های فیلتر استخراج‌شده زنده از عناوین
  نتایج (نوع پوست، بافت، SPF، حجم، تخفیف، برند) — هر کوئری فقط ویژگی‌های
  مرتبط با خودش را می‌گیرد.
- **فیلتر چندانتخابی:** OR داخل هر گروه، AND بین گروه‌ها.
  فیلترهای معنایی با خط لولهٔ سه‌مرحله‌ای (عنوان صریح ← بدون Jev، سرنخ مبهم ←
  Jev با سقف ۹۰، بی‌سرنخ ← حذف)؛ فیلترهای عددی (حجم/SPF/برند/تخفیف) کاملاً
  محلی و رایگان.
- **رتبه‌بندی کیفیت (پیش‌فرض):** سه لایهٔ قیمتی (اقتصادی/متوسط/پرچم‌دار) با
  مرتب‌سازی بیزیِ شرطی‌شده بر لایه + اعتبار برند (وزن‌دهی bconf=n/(n+200)).
  لایه‌بندی بر مبنای **قیمت منصفانه**: هر ۱۰۰ میلی‌لیتر/گرم (با پشتیبانی
  بسته‌های چندتایی «۲ عددی/دوتایی») یا هر عدد در دسته‌های بدون حجم.
- **گارد جنسیت:** نشتی موتور دیجی‌کالا (مثل «مایو زنانه» در «مایو مردانه») حذف می‌شود.
- API: `GET /api/search?q&sort&page` · `GET /api/filter?q&conds=[{group,value}…]` ·
  `GET /api/rank?q&conds=[…]`
- اجرا: `.venv/bin/python app.py` (پورت 8890؛ پشت reverse proxy).
  هزینهٔ Jev ≈ کسری از ریال به‌ازای هر فیلتر تحلیلی (خروجی رایگان، ورودی ~۲k توکن، کش ۶۰دقیقه).


### غیرفعال‌کردن Jev در فیلتر وب
گزینهٔ «بدون Jev» در رابط وب یا پارامتر `bypass_jev=1` در `/api/filter` و
`/api/rank`، فراخوانی Jev را غیرفعال می‌کند. فیلترهای مستقیم و تطابق صریح
عنوان همچنان اعمال می‌شوند؛ محصولات مبهم پذیرفته نمی‌شوند. پیش‌فرض Jev فعال
است. این گزینه مربوط به فیلتر وب است و ابزار MCP به نام `smart_pick` را تغییر نمی‌دهد.
