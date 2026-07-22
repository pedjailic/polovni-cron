import os
import re
import json
import time
import aiohttp
import asyncio
from curl_cffi import requests as cffi_requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = "https://www.polovniautomobili.com"
CORE_API = "https://core.polovniautomobili.com"
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")

SEARCHES = {
    "bg": {
        "title": "🚗 Beograd 2-12k€",
        "params": "priceFrom=2000&priceTo=12000&cityId=308&cityDistance=25&sort=basic",
    },
    "suv": {
        "title": "🛻 SUV BG 3-14k€",
        "params": "priceFrom=3000&priceTo=14000&chassis%5B%5D=suv"
                  "&cityId=308&cityDistance=50&sort=basic",
    },
    "toyota": {
        "title": "🟢 Toyota 2-14k€",
        "params": "brand=Toyota&priceFrom=2000&priceTo=14000"
                  "&cityId=308&cityDistance=100&sort=basic",
    },
    "hibridi": {
        "title": "⚡ Hibridi 3-14k€",
        "params": "priceFrom=3000&priceTo=14000&fuel=electric&fuel=hybrid"
                  "&cityId=308&cityDistance=50&sort=basic",
    },
    "jagodina": {
        "title": "🏘️ Jagodina 2-12k€",
        "params": "priceFrom=2000&priceTo=12000&city=Jagodina&cityDistance=10&sort=basic",
    },
}

NEXTDATA_RE = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

session = cffi_requests.Session(impersonate="chrome")

ENGAGEMENT_HEADERS = {
    "Referer": "https://www.polovniautomobili.com/",
    "Accept": "application/json",
}


def get_build_id():
    html = fetch("https://www.polovniautomobili.com/auto-oglasi/pretraga?sort=basic")
    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        raise RuntimeError("Could not find Next.js buildId")
    return m.group(1)


def fetch(url):
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            if ('429' in str(e) or '503' in str(e)) and attempt < 2:
                time.sleep(2 ** attempt + 1)
                continue
            raise


def fetch_engagement(ad_id):
    url = f"{CORE_API}/api/v1/classifieds/{ad_id}/additional/info"
    for attempt in range(2):
        try:
            r = session.get(url, headers=ENGAGEMENT_HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("followersNumber", 0), data.get("interestedInAdNumber", 0)
        except Exception:
            if attempt == 0:
                time.sleep(1)
    return 0, 0


def fetch_search_page(build_id, params, page):
    url = f"{BASE}/_next/data/{build_id}/auto-oglasi/pretraga.json?{params}&page={page}"
    text = fetch(url)
    data = json.loads(text)
    sr = data.get("pageProps", {}).get("searchResults", {})
    page_count = sr.get("pageCount", 0)
    total_items = sr.get("totalItems", 0)
    results = []
    for item in sr.get("results", []):
        price = item.get("price")
        if not price:
            continue
        brand_slug = item.get("brand", "").lower().replace(" ", "-")
        model_slug = item.get("title", "").lower().replace(" ", "-")
        results.append({
            "id": item.get("id", ""),
            "url": f"{BASE}/auto-oglasi/{item['id']}/{brand_slug}-{model_slug}",
            "title": item.get("title", ""),
            "price": price,
            "year": item.get("year", 0),
            "mileage": item.get("mileage", 0),
            "fuel": item.get("fuel", ""),
            "hp": item.get("horsePower", 0),
            "city": item.get("city", ""),
            "img": item.get("imageMain", ""),
            "indexedAt": item.get("indexedAt", ""),
        })
    return results, page_count, total_items


def collect_category(key, cat, build_id, max_pages=3):
    print(f"📂 {cat['title']}...")
    all_listings = {}

    for page in range(1, max_pages + 1):
        try:
            listings, page_count, total_items = fetch_search_page(build_id, cat["params"], page)
        except Exception as e:
            print(f"  ⚠️  Page {page} failed: {e}")
            break

        if not listings:
            break

        before = len(all_listings)
        for lst in listings:
            if lst["id"] not in all_listings:
                all_listings[lst["id"]] = lst

        print(f"    p{page}: +{len(all_listings) - before} ({len(all_listings)} total)")

        if page >= page_count:
            break
        time.sleep(1)

    print(f"   📊 Fetching engagement for {len(all_listings)} ads...")
    for ad_id, lst in all_listings.items():
        followers, interested = fetch_engagement(ad_id)
        lst["followers"] = followers
        lst["interested"] = interested

    valid = list(all_listings.values())
    valid.sort(key=lambda x: (x["followers"] + x["interested"] * 3, x["followers"]), reverse=True)
    top = valid[:10]

    newest = sorted(valid, key=lambda x: x.get("indexedAt", ""), reverse=True)[:30]
    newest.sort(key=lambda x: (x["followers"] + x["interested"] * 3, x["followers"]), reverse=True)
    newest = newest[:10]

    engaged = sum(1 for v in valid if v["followers"] > 0 or v["interested"] > 0)
    print(f"   ✅ {len(valid)} valid, {engaged} with engagement, top10 ready")
    return key, cat["title"], top, newest, len(valid)


def generate_html(data, updated):
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="sr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BG Auto Deals - Top 10</title>
<meta property="og:title" content="BG Auto Deals - Top 10">
<meta property="og:description" content="Najtraženiji polovni auti po kategorijama - automatski ažurirano">
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0f1419;color:#e7e9ea;line-height:1.5}}
  header{{padding:24px 16px;text-align:center;border-bottom:1px solid #2f3336;
          background:linear-gradient(180deg,#1a1f24,#0f1419)}}
  h1{{margin:0;font-size:1.8em}}
  .sub{{color:#8b98a5;margin-top:8px;font-size:0.95em}}
  .container{{max-width:1200px;margin:0 auto;padding:24px 16px}}
  .tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}}
  .tab{{background:#1a1f24;color:#e7e9ea;border:1px solid #2f3336;padding:10px 16px;
        border-radius:999px;cursor:pointer;font-size:0.95em;transition:all .2s}}
  .tab:hover{{background:#22272e}}
  .tab.active{{background:#1d9bf0;border-color:#1d9bf0;color:#fff}}
  .badge{{background:rgba(255,255,255,.15);padding:2px 8px;border-radius:999px;
          font-size:0.8em;margin-left:6px}}
  .refresh{{background:none;border:1px solid #2f3336;color:#8b98a5;padding:8px 14px;
            border-radius:999px;cursor:pointer;font-size:0.9em;transition:all .2s}}
  .refresh:hover{{background:#22272e;color:#e7e9ea}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
  .card{{background:#16181c;border:1px solid #2f3336;border-radius:14px;overflow:hidden;
         text-decoration:none;color:inherit;transition:transform .15s,border-color .15s;
         display:flex;flex-direction:column}}
  .card:hover{{transform:translateY(-3px);border-color:#1d9bf0}}
  .card-img{{height:170px;background-size:cover;background-position:center;
             background-color:#22272e;position:relative}}
  .rank{{position:absolute;top:10px;left:10px;background:#1d9bf0;color:#fff;
         font-weight:700;padding:4px 10px;border-radius:999px;font-size:0.85em}}
  .engage{{position:absolute;top:10px;right:10px;display:flex;gap:4px}}
  .engage span{{background:rgba(0,0,0,.7);color:#fff;padding:3px 8px;border-radius:999px;
                font-size:0.8em;backdrop-filter:blur(4px)}}
  .card-body{{padding:12px}}
  .title{{font-weight:600;font-size:0.95em;margin-bottom:8px;
          display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
          overflow:hidden}}
  .meta{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:0.85em}}
  .price{{background:#00ba7c;color:#fff;padding:3px 10px;border-radius:6px;font-weight:700}}
  .stat{{color:#8b98a5;background:#1a1f24;padding:2px 8px;border-radius:6px}}
  .empty{{color:#8b98a5;text-align:center;padding:40px}}
  footer{{text-align:center;color:#8b98a5;padding:24px;font-size:0.85em;
          border-top:1px solid #2f3336;margin-top:40px}}
  footer a{{color:#1d9bf0}}
</style>
</head>
<body>
<header>
  <h1>🚗 BG Auto Deals</h1>
  <div class="sub">Top 10 najtraženijih (💛 pratioci + 🤝 zainteresovani) · Ažurirano: <b>{updated}</b></div>
</header>
<div class="container">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
    <div class="tabs" id="tabs" style="flex:1;display:flex;gap:8px;flex-wrap:wrap"></div>
    <span style="color:#8b98a5;font-size:0.85em">🕐 {updated}</span>
    <button class="refresh" onclick="location.reload()">🔄 Osveži</button>
  </div>
  <div class="grid" id="grid"></div>
  <h2 style="margin-top:40px;font-size:1.3em;border-top:1px solid #2f3336;padding-top:24px">🆕 Najnoviji oglasi</h2>
  <div class="grid" id="newest-grid"></div>
</div>
<footer>
  Podaci sa <a href="https://www.polovniautomobili.com" target="_blank">polovniautomobili.com</a> ·
  Rangirano po interesovanju (💛 pratioci + 🤝 zainteresovani za kupovinu) ·
  <a href="data.json">data.json</a>
</footer>
<script>
const DATA = {data_json};
let activeTab = Object.keys(DATA.categories)[0];

function esc(s) {{ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

function fmtKm(km) {{ return km ? km.toLocaleString('sr') + ' km' : ''; }}

function renderTabs() {{
  const el = document.getElementById('tabs');
  el.innerHTML = Object.entries(DATA.categories).map(([k,v]) =>
    '<button class="tab'+(k===activeTab?' active':'')+'" data-tab="'+k+'">'
    +esc(v.title)+' <span class="badge">'+v.total+'</span></button>'
  ).join('');
}}

function renderCard(r, i, showDate) {{
  const img = r.img || '';
  const imgStyle = img ? "background-image:url('"+img+"')" : "";
  const badges = [];
  if (r.followers > 0) badges.push('<span>💛 '+r.followers+'</span>');
  if (r.interested > 0) badges.push('<span>🤝 '+r.interested+'</span>');
  const dateBadge = showDate && r.indexedAt
    ? '<span class="stat">🕐 '+r.indexedAt.slice(0,10)+'</span>' : '';
  return '<a class="card" href="'+r.url+'" target="_blank" rel="noopener">'
    +'<div class="card-img" style="'+imgStyle+'">'
    +'<span class="rank">#'+(i+1)+'</span>'
    +(badges.length ? '<div class="engage">'+badges.join('')+'</div>' : '')
    +'</div>'
    +'<div class="card-body"><div class="title">'+esc(r.title)+'</div>'
    +'<div class="meta"><span class="price">'+r.price+'€</span>'
    +dateBadge
    +(r.year ? '<span class="stat">📅 '+r.year+'</span>' : '')
    +(r.mileage ? '<span class="stat">🛣️ '+fmtKm(r.mileage)+'</span>' : '')
    +(r.hp ? '<span class="stat">🐴 '+r.hp+' KS</span>' : '')
    +(r.fuel ? '<span class="stat">⛽ '+esc(r.fuel)+'</span>' : '')
    +'</div></div></a>';
}}

function renderGrid() {{
  const cat = DATA.categories[activeTab];
  const el = document.getElementById('grid');
  if (!cat.top.length) {{
    el.innerHTML = '<p class="empty">Nema rezultata za ovu kategoriju.</p>';
    return;
  }}
  el.innerHTML = cat.top.map((r,i) => renderCard(r, i, false)).join('');
}}

function renderNewest() {{
  const cat = DATA.categories[activeTab];
  const el = document.getElementById('newest-grid');
  if (!cat.newest || !cat.newest.length) {{
    el.innerHTML = '<p class="empty">Nema najnovijih rezultata.</p>';
    return;
  }}
  el.innerHTML = cat.newest.map((r,i) => renderCard(r, i, true)).join('');
}}

document.getElementById('tabs').addEventListener('click', e => {{
  const btn = e.target.closest('.tab');
  if (!btn) return;
  activeTab = btn.dataset.tab;
  renderTabs();
  renderGrid();
  renderNewest();
}});

renderTabs();
renderGrid();
renderNewest();
</script>
</body>
</html>"""


async def send_telegram(msg):
    if not (TG_TOKEN and TG_CHAT):
        print("⚠️  Telegram nije konfigurisan, preskačem slanje")
        return
    async with aiohttp.ClientSession() as session:
        while msg:
            chunk, msg = msg[:3800], msg[3800:]
            try:
                async with session.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": chunk, "parse_mode": "Markdown",
                          "disable_web_page_preview": True}
                ) as r:
                    print(await r.text())
            except Exception as e:
                print(f"Telegram error: {e}")


async def main():
    print("🔍 Getting buildId...")
    build_id = get_build_id()
    print(f"   buildId: {build_id}")

    results = []
    for key, cat in SEARCHES.items():
        result = collect_category(key, cat, build_id)
        results.append(result)
        time.sleep(2)

    total_listings = sum(r[4] for r in results)
    if total_listings == 0:
        print("⚠️  0 rezultata ukupno — sajt možda u remontu, preskačem deploy")
        return

    belgrade = timezone(timedelta(hours=2))
    updated = datetime.now(belgrade).strftime("%d.%m.%Y %H:%M")
    data = {"updated": updated, "categories": {}}
    msg_parts = [f"🚗 *BG Auto Deals - {updated}*"]

    for key, title, top10, newest10, total in results:
        data["categories"][key] = {"title": title, "top": top10, "newest": newest10, "total": total}
        msg_parts.append(f"\n*{title}* _({total} oglasa)_")
        for i, r in enumerate(top10, 1):
            eng = ""
            if r["followers"] > 0 or r["interested"] > 0:
                eng = f" 💛{r['followers']} 🤝{r['interested']}"
            msg_parts.append(
                f"{i}. 💶{r['price']}€ 📅{r['year']} 🛣️{r['mileage']}km{eng}\n"
                f"   {r['title']}\n   {r['url']}"
            )

    Path("public").mkdir(exist_ok=True)
    Path("public/data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    Path("public/index.html").write_text(generate_html(data, updated))
    print(f"✅ HTML generated in public/ ({total_listings} total listings)")

    await send_telegram("\n".join(msg_parts))


if __name__ == "__main__":
    asyncio.run(main())
