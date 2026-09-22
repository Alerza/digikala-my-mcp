"""Digikala search web app — روی همان منطق سرور MCP.
اجرا: .venv/bin/python app.py   (پورت 8890، Caddy روی 8794 پروکسی می‌کند)
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import server  # سرور MCP: _get, _card, API, SORTS را اینجا reuse می‌کنیم
import facets as facets_mod  # استخراج فیلت‌ها + فیلتر Jev

PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>جستجوی دیجی‌کالا</title>
<style>
  :root { --red:#ef4056; --gray:#8f8f8f; --bg:#f5f5f7; }
  * { box-sizing:border-box; font-family:Vazirmatn,Tahoma,sans-serif; }
  body { margin:0; background:var(--bg); color:#3f4064; }
  header { background:#fff; border-bottom:1px solid #e5e5e5; position:sticky; top:0; z-index:5; }
  .wrap { max-width:720px; margin:0 auto; padding:12px 16px; }
  .brand { color:var(--red); font-weight:800; font-size:20px; margin-bottom:8px; }
  form { display:flex; gap:8px; }
  input[type=text] { flex:1; padding:12px 14px; border:1px solid #d5d5d5; border-radius:10px; font-size:16px; outline:none; }
  input[type=text]:focus { border-color:var(--red); }
  select, button { padding:0 14px; border-radius:10px; border:1px solid #d5d5d5; background:#fff; font-size:15px; }
  button { background:var(--red); color:#fff; border:none; font-weight:700; cursor:pointer; }
  .hint { color:var(--gray); font-size:13px; margin-top:6px; }
  .card { background:#fff; border-radius:12px; margin-top:10px; padding:14px; display:flex; gap:12px;
          box-shadow:0 1px 3px rgba(0,0,0,.06); align-items:center; }
  .thumb { width:64px; height:64px; border-radius:8px; background:#f0f0f0; object-fit:contain; flex-shrink:0; }
  .info { flex:1; min-width:0; }
  .title { font-size:14.5px; line-height:1.7; }
  .title a { color:#3f4064; text-decoration:none; }
  .title a:hover { color:var(--red); }
  .meta { display:flex; gap:10px; align-items:center; margin-top:6px; flex-wrap:wrap; }
  .price { font-weight:800; font-size:15px; }
  .old { color:var(--gray); text-decoration:line-through; font-size:12px; }
  .off { background:#e8f7ef; color:#1a9a4f; font-size:12px; border-radius:6px; padding:1px 6px; font-weight:700; }
  .rate { color:#f9a825; font-size:12.5px; }
  .nostock { color:var(--gray); font-size:12px; }
  .pager { display:flex; justify-content:center; gap:8px; margin:16px 0 32px; }
  .pager button { background:#fff; color:#3f4064; border:1px solid #d5d5d5; }
  .empty { text-align:center; color:var(--gray); padding:40px 0; }
  .spinner { text-align:center; padding:40px; color:var(--gray); display:none; }
  .facets { background:#fff; border-radius:12px; margin-top:10px; padding:6px 14px 12px;
            box-shadow:0 1px 3px rgba(0,0,0,.06); display:none; }
  .fgroup { margin-top:10px; }
  .fgroup .gname { font-size:12.5px; color:var(--gray); font-weight:700; margin-bottom:6px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { border:1px solid #d5d5d5; background:#fafafa; border-radius:20px; padding:5px 12px;
          font-size:13px; cursor:pointer; color:#3f4064; }
  .chip:hover { border-color:var(--red); color:var(--red); }
  .chip.on { background:var(--red); color:#fff; border-color:var(--red); font-weight:700; }
  .chip .n { opacity:.65; font-size:11px; }
  .filterbar { display:none; margin-top:10px; background:#fff3f4; border:1px solid #f7c8ce;
               border-radius:10px; padding:8px 14px; font-size:13.5px; align-items:center; gap:10px; }
  .filterbar b { color:var(--red); }
  .filterbar .x { margin-right:auto; cursor:pointer; color:var(--gray); font-weight:700; }
  .jev { background:#e8f0fe; color:#1967d2; font-size:11px; border-radius:6px; padding:1px 6px; }
  .tier { margin-top:18px; }
  .tabs { display:flex; gap:6px; margin-top:12px; background:#fff; border-radius:12px; padding:6px;
          box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .tab { flex:1; text-align:center; padding:9px 6px; border-radius:9px; cursor:pointer;
         font-size:13.5px; color:#555; border:none; background:transparent; font-weight:600; }
  .tab small { display:block; font-weight:400; color:var(--gray); font-size:11px; margin-top:2px; }
  .tab.on { background:var(--red); color:#fff; }
  .tab.on small { color:#ffd3da; }
  .tier h2 { font-size:15px; margin:0 0 4px; display:flex; align-items:center; gap:8px; }
  .tier h2 .trange { color:var(--gray); font-size:12px; font-weight:400; }
  .rank { width:26px; height:26px; border-radius:50%; background:#eee; color:#555; font-size:12px;
          font-weight:800; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
  .card.top .rank { background:#ffd54f; color:#7a5b00; }
  .qscore { background:#e8f7ef; color:#1a9a4f; font-size:11.5px; border-radius:6px; padding:1px 7px; font-weight:700; }
  .unit { color:#7c4dff; font-size:11.5px; background:#f3edff; border-radius:6px; padding:1px 7px; }
</style>
</head>
<body>
<header><div class="wrap">
  <div class="brand">🛒 جستجوی دیجی‌کالا</div>
  <form id="f">
    <input type="text" id="q" placeholder="چی می‌خوای؟ مثلاً گوشی سامسونگ" autofocus>
    <select id="sort">
      <option value="tiered" selected>🏆 رتبه‌بندی کیفیت (۳ لایهٔ قیمتی)</option>
      <option value="default">مرتبط‌ترین</option>
      <option value="cheap">ارزان‌ترین</option>
      <option value="expensive">گران‌ترین</option>
      <option value="bestselling">پرفروش‌ترین</option>
      <option value="newest">جدیدترین</option>
      <option value="most_discount">بیشترین تخفیف</option>
    </select>
    <button>جستجو</button>
  </form>
  <div class="hint" id="hint"></div>
</div></header>
<main class="wrap">
  <div class="filterbar" id="fbar"></div>
  <div class="facets" id="facets"></div>
  <div class="spinner" id="sp">در حال جستجو…</div>
  <div id="results"></div>
  <div class="pager" id="pager"></div>
</main>
<script>
let page = 1, lastQ = "", lastSort = "tiered", active = [], lastFacets = null, tierData = null, tierShown = 1;
const fmt = n => n.toLocaleString("fa-IR");
const $ = id => document.getElementById(id);

function cardHtml(p, rank) {
  return `
  <div class="card${rank && rank <= 3 ? " top" : ""}">
    ${rank ? `<div class="rank">${fmt(rank)}</div>` : ""}
    ${p.image ? `<img class="thumb" src="${p.image}" loading="lazy" onerror="this.style.display='none'">` : ""}
    <div class="info">
      <div class="title"><a href="${p.url}" target="_blank" rel="noopener">${p.title}</a></div>
      <div class="meta">
        <span class="price">${fmt(p.price_toman)} تومان</span>
        ${p.unit_price_toman ? (() => { const L = p.unit_label || "ml"; if (L.includes("عددی")) return `<span class="unit">هر ${L.replace(/×\\d+/g,"")} = ${fmt(p.unit_price_toman)} ت</span>`; return `<span class="unit">هر ۱۰۰${L.includes("×") ? " (بسته‌ای)" : ""} ${L.replace(/×\\d+/g,"") || "ml"} = ${fmt(p.unit_price_toman)} ت${p.unit_est ? " ⚠︎" : ""}</span>`; })() : ""}
        ${p.rrp_toman ? `<span class="old">${fmt(p.rrp_toman)}</span><span class="off">${fmt(p.discount_pct)}٪ تخفیف</span>` : ""}
        ${p.rating_pct ? `<span class="rate">★ ${fmt(Math.round(p.rating_pct/20*10)/10)} (${fmt(p.votes)} نظر)</span>` : ""}
        ${p.score ? `<span class="qscore">امتیاز کیفیت ${fmt(p.score)}</span>` : ""}
        ${p.jev_match ? `<span class="jev">تطابق ${fmt(p.jev_match)}</span>` : ""}
        ${!p.in_stock ? `<span class="nostock">ناموجود</span>` : ""}
      </div>
    </div>
  </div>`;
}

function renderTiers(r) {
  tierData = r.tiers || [];
  if (!tierData.some(t => t.tier === tierShown)) tierShown = tierData[0] ? tierData[0].tier : 1;
  drawTier();
}
function drawTier() {
  const TIER_ICON = {1: "💰", 2: "⚖️", 3: "👑"};
  if (!tierData || !tierData.length) { $("results").innerHTML = ""; return; }
  const isVol = (tierData[0].items[0]?.unit_label || "").match(/ml|g/);
  const tabs = `<div class="tabs">${tierData.map(t =>
    `<button class="tab${t.tier === tierShown ? " on" : ""}" onclick="tierShown=${t.tier};drawTier()">
       ${TIER_ICON[t.tier] || ""} ${t.name}<small>${isVol && t.unit_range ? `هر۱۰۰ ${fmt(t.unit_range[0])}–${fmt(t.unit_range[1])} ت` : `${fmt(t.range_toman[0])}–${fmt(t.range_toman[1])} ت`} · ${fmt(t.items.length)} تا</small>
     </button>`).join("")}</div>`;
  const t = tierData.find(x => x.tier === tierShown) || tierData[0];
  $("results").innerHTML = tabs +
    `<div class="tier">${t.items.map((p, i) => cardHtml(p, i + 1)).join("")}</div>`;
}

function renderFacets(fs) {
  const box = $("facets");
  if (!fs || !fs.length) { box.style.display = "none"; return; }
  box.style.display = "block";
  box.innerHTML = fs.map(g => `
    <div class="fgroup">
      <div class="gname">${g.group}${g.mode === "jev" ? ' <span class="jev">تحلیلی Jev</span>' : ""}</div>
      <div class="chips">${g.options.map(o => {
        const on = active.some(a => a.group === g.group && a.value === o.label);
        return `<button class="chip${on ? " on" : ""}" data-g="${g.group}" data-v="${o.label}">${o.label} <span class="n">${fmt(o.count)}</span></button>`;
      }).join("")}</div>
    </div>`).join("");
  box.querySelectorAll(".chip").forEach(ch => ch.addEventListener("click", () => {
    const g = ch.dataset.g, v = ch.dataset.v;
    const i = active.findIndex(a => a.group === g && a.value === v);
    if (i >= 0) active.splice(i, 1); else active.push({group: g, value: v});
    filter();
  }));
}

function condParams() {
  return "conds=" + encodeURIComponent(JSON.stringify(active));
}
function renderActiveBar(extra) {
  $("fbar").style.display = "flex";
  const chips = active.map((a, i) =>
    `<span class="fchip"><b>${a.group}: ${a.value}</b><span class="x" onclick="active.splice(${i},1);filter()">✕</span></span>`).join("");
  $("fbar").innerHTML = (extra || "") + " " + (chips
    ? `فیلترها: ${chips}` : "") +
    (active.length > 1 ? ` <span class="x" onclick="active=[];filter()">پاک‌کردن همه</span>` : "");
}

function renderPager(pages) {
  const pg = $("pager");
  pg.innerHTML = pages > 1 ?
    (page > 1 ? `<button onclick="run(${page-1})">→ قبلی</button>` : "") +
    `<button disabled style="border:none;background:none">${fmt(page)} / ${fmt(pages)}</button>` +
    (page < pages ? `<button onclick="run(${page+1})">بعدی ←</button>` : "") : "";
}

async function filter() {
  $("sp").style.display = "block"; $("results").innerHTML = ""; $("pager").innerHTML = "";
  $("fbar").style.display = "none";
  const tieredMode = lastSort === "tiered";
  if (!tieredMode && !active.length) { return run(1); }
  let r;
  try {
    r = await fetch(`${tieredMode ? "/api/rank" : "/api/filter"}?q=${encodeURIComponent(lastQ)}&${condParams()}`);
    r = await r.json();
  } catch (e) { r = {error: "خطای شبکه"}; }
  $("sp").style.display = "none";
  if (r.error) { $("results").innerHTML = `<div class="empty">⚠️ ${r.error}</div>`; renderFacets(lastFacets); return; }
  if (tieredMode) {
    renderActiveBar(active.length ? "🏆 رتبه‌بندی کیفیت —"
      : `🏆 رتبه‌بندی کیفیت: سه لایهٔ قیمتی، داخل هر لایه بر پایهٔ امتیاز بیزی + اعتبار برند`);
    if (r.tiers && r.tiers.length) {
      renderTiers(r);
    } else {
      $("results").innerHTML = `<div class="empty">${r.note || "چیزی نماند — فیلتر را بردار 🔍"}</div>`;
    }
    lastFacets = r.facets || lastFacets;
    renderFacets(lastFacets);
    const total = (r.tiers || []).reduce((s, t) => s + t.items.length, 0);
    $("hint").textContent = `${fmt(total)} محصول رتبه‌بندی‌شده در ${fmt((r.tiers||[]).length)} لایه` +
      (String(r.mode).startsWith("jev") ? " (فیلتر تحلیلی Jev)" : "");
    scrollTo(0, 0);
    return;
  }
  renderActiveBar();
  $("results").innerHTML = r.items.length ? r.items.map(cardHtml).join("") :
    `<div class="empty">با این فیلتر چیزی نماند — فیلتر را بردار 🔍</div>`;
  lastFacets = r.facets || lastFacets;
  renderFacets(lastFacets);
  const modeTxt = r.stats ? `عنوان صریح ${fmt(r.stats.explicit_kept)} · تحلیلی Jev ${fmt(r.stats.jev_called)}`
    : "تطبیق مستقیم عنوان";
  $("hint").textContent = `${fmt(r.items.length)} نتیجهٔ فیلترشده (${modeTxt}) — از ${fmt(r.candidates)} کاندیدا`;
  scrollTo(0, 0);
}

function facetsFromTiers(r) {
  // in tiered mode the /api/rank response has no facets; rebuild counts from tiers
  return null;
}

async function run(p) {
  if (!lastQ) return;
  if (lastSort === "tiered") { return filter(); }
  if (active.length) { return filter(); }
  page = p || 1;
  $("sp").style.display = "block"; $("results").innerHTML = ""; $("pager").innerHTML = "";
  $("fbar").style.display = "none";
  let r;
  try {
    r = await fetch(`/api/search?q=${encodeURIComponent(lastQ)}&sort=${lastSort}&page=${page}`);
    r = await r.json();
  } catch (e) { r = {error: "خطای شبکه"}; }
  $("sp").style.display = "none";
  if (r.error) { $("results").innerHTML = `<div class="empty">⚠️ ${r.error}</div>`; return; }
  $("results").innerHTML = r.items.length ? r.items.map(cardHtml).join("") :
    `<div class="empty">چیزی پیدا نشد — کوتاه‌تر یا متفاوت جستجو کن 🔍</div>`;
  renderPager(r.pager?.total_pages || 1);
  lastFacets = r.facets;
  renderFacets(r.facets);
  $("hint").textContent = `${fmt(r.pager?.total_items || r.items.length)} نتیجه برای «${lastQ}»`;
  scrollTo(0, 0);
}
document.getElementById("f").addEventListener("submit", e => {
  e.preventDefault();
  lastQ = $("q").value.trim();
  lastSort = $("sort").value;
  active = [];
  run(1);
});
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if u.path == "/api/search":
            qs = parse_qs(u.query)
            q = (qs.get("q") or [""])[0].strip()
            if not q:
                self._send(400, json.dumps({"error": "query خالی است"}))
                return
            page = max(1, int((qs.get("page") or ["1"])[0] or 1))
            sort = (qs.get("sort") or ["default"])[0]
            params = {"q": q, "page": page}
            # بیشترین تخفیف: دیجی‌کالا چنین سورتی ندارد — سمت ما روی کاندیداها
            if sort == "most_discount":
                try:
                    all_cards = facets_mod.get_products(q)
                except Exception as e:
                    self._send(502, json.dumps({"error": str(e)[:120]}))
                    return
                dsc = [{k: v for k, v in c.items() if k not in ("_t", "_dl")}
                       for c in sorted((c for c in all_cards if (c.get("discount_pct") or 0) > 0),
                                       key=lambda c: -(c.get("discount_pct") or 0))]
                self._send(200, json.dumps({
                    "items": dsc, "facets": [],
                    "pager": {"total_pages": 1, "total_items": len(dsc)},
                    "sort_note": f"مرتب‌سازی محلی روی {len(all_cards)} کاندیدا",
                }, ensure_ascii=False))
                return
            sid = facets_mod.resolve_sort(q, sort) if sort != "default" else None
            if sid is None and sort != "default":
                sid = server.SORTS.get(sort)
            if sid and sid != 1:
                params["sort"] = sid
            try:
                data = server._get(f"{server.API}/search/", params)
            except Exception as e:
                self._send(502, json.dumps({"error": f"digikala API: {str(e)[:120]}"}))
                return
            items = data.get("data", {}).get("products", [])
            cards = []
            for p in items:
                c = server._card(p)
                main = (p.get("images") or {}).get("main") or {}
                urls = main.get("webp_url") or main.get("url") or []
                c["image"] = urls[0] if urls else None
                cards.append(c)
            facets = []
            if page == 1 and sort == "default":
                try:
                    facets = facets_mod.facets_for(q)
                except Exception:
                    facets = []
            self._send(200, json.dumps({
                "items": cards,
                "facets": facets,
                "pager": data.get("data", {}).get("pager", {}),
                "total_estimate": data.get("data", {}).get("pager", {}).get("total"),
            }, ensure_ascii=False))
            return
        if u.path in ("/api/filter", "/api/rank"):
            qs = parse_qs(u.query)
            q = (qs.get("q") or [""])[0].strip()
            rank = u.path == "/api/rank"
            if not q:
                self._send(400, json.dumps({"error": "q لازم است"}))
                return
            conds = []
            raw = (qs.get("conds") or [""])[0]
            if raw:
                try:
                    conds = [(c.get("group", ""), c.get("value", ""))
                             for c in json.loads(raw)
                             if c.get("group") and c.get("value")]
                except Exception:
                    conds = []
            elif (qs.get("group") or [""])[0] and (qs.get("value") or [""])[0]:
                conds = [(qs["group"][0], qs["value"][0])]
            try:
                if rank:
                    out = facets_mod.tiered_rank(q, conds)
                else:
                    out = (facets_mod.apply_filters(q, conds) if conds
                           else {"items": [], "facets": facets_mod.facets_for(q)})
            except Exception as e:
                out = {"error": str(e)[:150]}
            self._send(200, json.dumps(out, ensure_ascii=False))
            return
        self._send(404, json.dumps({"error": "not found"}))


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8890), Handler).serve_forever()
