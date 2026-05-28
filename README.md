# 🚗 BG Auto Deals

Automatski cron koji svakog dana skenira polovniautomobili.com i objavljuje
top 5 najtraženijih polovnih auta po kategorijama (po broju ❤️ srca i 🛒 želim da kupim).

## Kategorije
- 🚗 Svi BG (2k-12k€)
- 🛻 SUV
- 🟢 Toyota
- ⚡ Hibridi

## Stack
- Python 3.11 + aiohttp (skener)
- GitHub Actions (cron, dnevno u 07:00 UTC)
- Netlify (hosting javne stranice)
- Telegram bot (notifikacije)

## Setup

### 1. Telegram bot (opciono)
1. Pošalji `/newbot` na **@BotFather** → dobij token
2. Pošalji bilo šta svom novom botu
3. Otvori `https://api.telegram.org/bot<TOKEN>/getUpdates` → pronađi chat ID

### 2. GitHub Secrets
Repo → Settings → Secrets and variables → Actions:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `NETLIFY_AUTH_TOKEN`
- `NETLIFY_SITE_ID`

### 3. Netlify
1. netlify.com → Add new site → Import from GitHub → izaberi repo
2. Publish directory: `public`
3. Build command: prazno

### 4. Lokalno pokretanje
```bash
pip install -r requirements.txt
python scraper.py
open public/index.html
```

## Ručno pokretanje
GitHub → Actions → "Daily Scrape & Deploy" → Run workflow
