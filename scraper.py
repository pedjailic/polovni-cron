import os
import re
import json
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as cffi_requests
from datetime import datetime
from pathlib import Path

BASE = "https://www.polovniautomobili.com"
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")

SEARCHES = {
    "svi": {
        "title": "🚗 Svi BG (2k-12k€)",
        "url": "/auto-oglasi/poslednja24h?price_from=2000&price_to=12000"
               "&city=Beograd%7C44.820556%7C20.462222&city_distance=25&page={page}",
    },
    "suv": {
        "title": "🛻 SUV",
        "url": "/auto-oglasi/poslednja24h?price_from=3000&price_to=14000"
               "&chassis%5B0%5D=2627&chassis%5B1%5D=277"
               "&city=Beograd%7C44.820556%7C20.462222&city_distance=50&page={page}",
    },
    "toyota": {
        "title": "🟢 Toyota",
        "url": "/auto-oglasi/poslednja24h?price_from=2000&price_to=14000"
               "&brand=toyota"
               "&city=Beograd%7C44.820556%7C20.462222&city_distance=100&page={page}",
    },
    "hibridi": {
        "title": "⚡ Hibridi",
        "url": "/auto-oglasi/poslednja24h?price_from=3000&price_to=14000"
               "&fuel%5B0%5D=3057&fuel%5B1%5D=3058"
               "&city=Beograd%7C44.820556%7C20.462222&city_distance=50&page={page}",
    },
    "jagodina": {
        "title": "🏘️ Jagodina",
        "url": "/auto-oglasi/poslednja24h?price_from=2000&price_to=12000"
               "&city=Jagodina%7C43.977222%7C21.261111&city_distance=10&page={page}",
    },
}

LISTING_RE = re.compile(r"/auto-oglasi/(\d+)/([\w\-]+)")
HEARTS_RE = re.compile(r'<span\s+class="classified-liked"[^>]*>\s*(\d+)\s*</span>')
WANT_RE = re.compile(r'<span\s+class="classified-interested"[^>]*>\s*(\d+)\s*</span>')
TITLE_RE = re.compile(r"<title>([^<]+)</title>")
PRICE_RE = re.compile(r'"price"\s*:\s*"(\d+)"')
IMG_RE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')

executor = ThreadPoolExecutor(max_workers=10)


def _fetch_sync(url):
    r = cffi_requests.get(url, impersonate="chrome", timeout=30)
    r.raise_for_status()
    return r.text


async def fetch(url):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _fetch_sync, url)


async def collect_ids(path_template, max_pages=5):
    ids = set()
    for page in range(1, max_pages + 1):
        try:
            html = await fetch(BASE + path_template.format(page=page))
        except Exception as e:
            print(f"  ⚠️  Page {page} failed: {e}")
            break
        new = LISTING_RE.findall(html)
        if not new:
            break
        before = len(ids)
        for nid, slug in new:
            ids.add(f"/auto-oglasi/{nid}/{slug}")
        if len(ids) == before:
            break
    return list(ids)


async def get_listing(path, sem):
    async with sem:
        try:
            html = await fetch(BASE + path)
            h = HEARTS_RE.search(html)
            w = WANT_RE.search(html)
            t = TITLE_RE.search(html)
            p = PRICE_RE.search(html)
            img = IMG_RE.search(html)
            return {
                "path": path,
                "url": BASE + path,
                "hearts": int(h.group(1)) if h else 0,
                "want": int(w.group(1)) if w else 0,
                "title": (t.group(1) if t else "").strip().replace("\n", " ")[:90],
                "price": p.group(1) if p else "?",
                "img": img.group(1) if img else "",
            }
        except Exception as e:
            print(f"  ⚠️  Listing failed {path}: {e}")
            return None


async def process_category(key, cat, sem):
    print(f"📂 {cat['title']}...")
    ids = await collect_ids(cat["url"])
    print(f"   Found {len(ids)} listings, fetching details...")
    results = await asyncio.gather(*[get_listing(p, sem) for p in ids])
    valid = [r for r in results if r]
    valid.sort(key=lambda r: (r["want"], r["hearts"]), reverse=True)
    print(f"   ✅ {len(valid)} valid, top5 ready")
    return key, cat["title"], valid[:10], len(ids)


def escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_html(data, updated):
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="sr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BG Auto Deals - Top 10 dnevno</title>
<meta property="og:title" content="BG Auto Deals - Top 10 dnevno">
<meta property="og:description" content="Najtraženiji polovni auti u Beogradu - automatski ažurirano svaki dan">
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
  .filters{{display:flex;gap:12px;align-items:center;margin-bottom:20px;flex-wrap:wrap}}
  .filters label{{color:#8b98a5;font-size:0.9em}}
  .filters input{{background:#1a1f24;color:#e7e9ea;border:1px solid #2f3336;
                   padding:8px 12px;border-radius:8px;width:90px;font-size:0.9em}}
  .filters input::placeholder{{color:#555}}
  .filters button{{background:#1d9bf0;color:#fff;border:none;padding:8px 16px;
                    border-radius:8px;cursor:pointer;font-size:0.9em}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
  .card{{background:#16181c;border:1px solid #2f3336;border-radius:14px;overflow:hidden;
         text-decoration:none;color:inherit;transition:transform .15s,border-color .15s;
         display:flex;flex-direction:column}}
  .card:hover{{transform:translateY(-3px);border-color:#1d9bf0}}
  .card-img{{height:170px;background-size:cover;background-position:center;
             background-color:#22272e;position:relative}}
  .rank{{position:absolute;top:10px;left:10px;background:#1d9bf0;color:#fff;
         font-weight:700;padding:4px 10px;border-radius:999px;font-size:0.85em}}
  .card-body{{padding:12px}}
  .title{{font-weight:600;font-size:0.95em;margin-bottom:8px;
          display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
          overflow:hidden}}
  .meta{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:0.9em}}
  .price{{background:#00ba7c;color:#fff;padding:3px 10px;border-radius:6px;font-weight:700}}
  .stat{{color:#8b98a5}}
  .stat.want{{color:#f4b400}}
  .empty{{color:#8b98a5;text-align:center;padding:40px}}
  footer{{text-align:center;color:#8b98a5;padding:24px;font-size:0.85em;
          border-top:1px solid #2f3336;margin-top:40px}}
  footer a{{color:#1d9bf0}}
</style>
</head>
<body>
<header>
  <h1>🚗 BG Auto Deals</h1>
  <div class="sub">Top 10 najtraženijih polovnih po kategorijama · Ažurirano: <b>{updated}</b></div>
</header>
<div class="container">
  <div class="tabs" id="tabs"></div>
  <div class="filters">
    <label>Cena:</label>
    <input type="number" id="priceMin" placeholder="od €" step="500">
    <span style="color:#555">–</span>
    <input type="number" id="priceMax" placeholder="do €" step="500">
    <button id="filterBtn">Filtriraj</button>
  </div>
  <div class="grid" id="grid"></div>
</div>
<footer>
  Podaci sa <a href="https://www.polovniautomobili.com" target="_blank">polovniautomobili.com</a> ·
  Sortirano po 🛒 želim da kupim + ❤️ srca ·
  <a href="data.json">data.json</a>
</footer>
<script>
const DATA = {data_json};
let activeTab = Object.keys(DATA.categories)[0];

function esc(s) {{ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

function renderTabs() {{
  const el = document.getElementById('tabs');
  el.innerHTML = Object.entries(DATA.categories).map(([k,v]) =>
    '<button class="tab'+(k===activeTab?' active':'')+'" data-tab="'+k+'">'
    +esc(v.title)+' <span class="badge">'+v.total+'</span></button>'
  ).join('');
}}

function renderGrid() {{
  const cat = DATA.categories[activeTab];
  const minP = parseInt(document.getElementById('priceMin').value) || 0;
  const maxP = parseInt(document.getElementById('priceMax').value) || Infinity;
  const filtered = cat.top.filter(r => {{
    const p = parseInt(r.price) || 0;
    return p >= minP && p <= maxP;
  }});
  const el = document.getElementById('grid');
  if (!filtered.length) {{
    el.innerHTML = '<p class="empty">Nema rezultata za zadati filter.</p>';
    return;
  }}
  el.innerHTML = filtered.map((r,i) => {{
    const img = r.img || 'https://via.placeholder.com/400x250?text=Polovni+Automobili';
    return '<a class="card" href="'+r.url+'" target="_blank" rel="noopener">'
      +'<div class="card-img" style="background-image:url(\\\''+img+'\\\')">'
      +'<span class="rank">#'+(i+1)+'</span></div>'
      +'<div class="card-body"><div class="title">'+esc(r.title)+'</div>'
      +'<div class="meta"><span class="price">'+r.price+'€</span>'
      +'<span class="stat">❤️ '+r.hearts+'</span>'
      +'<span class="stat want">🛒 '+r.want+'</span></div></div></a>';
  }}).join('');
}}

document.getElementById('tabs').addEventListener('click', e => {{
  const btn = e.target.closest('.tab');
  if (!btn) return;
  activeTab = btn.dataset.tab;
  renderTabs();
  renderGrid();
}});

document.getElementById('filterBtn').addEventListener('click', renderGrid);
document.querySelectorAll('.filters input').forEach(inp => {{
  inp.addEventListener('keydown', e => {{ if (e.key==='Enter') renderGrid(); }});
}});

renderTabs();
renderGrid();
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
    sem = asyncio.Semaphore(10)
    tasks = [process_category(k, c, sem) for k, c in SEARCHES.items()]
    results = await asyncio.gather(*tasks)

    updated = datetime.now().strftime("%d.%m.%Y %H:%M")
    data = {"updated": updated, "categories": {}}
    msg_parts = [f"🚗 *BG Auto Deals - {updated}*"]

    for key, title, top5, total in results:
        data["categories"][key] = {"title": title, "top": top5, "total": total}
        msg_parts.append(f"\n*{title}* _({total} oglasa)_")
        for i, r in enumerate(top5, 1):
            msg_parts.append(
                f"{i}. ❤️{r['hearts']} 🛒{r['want']} 💶{r['price']}€\n"
                f"   {r['title']}\n   {r['url']}"
            )

    Path("public").mkdir(exist_ok=True)
    Path("public/data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    Path("public/index.html").write_text(generate_html(data, updated))
    print("✅ HTML generated in public/")

    await send_telegram("\n".join(msg_parts))


if __name__ == "__main__":
    asyncio.run(main())
