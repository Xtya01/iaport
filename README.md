# IA Drive — Private Internet Archive File Manager

Google Drive clone using Internet Archive for unlimited storage + Cloudflare for CDN.

## Files
- app.py — Flask backend (port 8080)
- worker.js — Cloudflare Worker
- file-manager.html — frontend (Tailwind + Konsta UI style + Plyr)
- Dockerfile + requirements.txt
- wrangler.toml — Worker config

## Setup
1. Set env vars:
   IA_BUCKET=junk-manage-caution
   IA_ACCESS_KEY=xxx
   IA_SECRET_KEY=xxx
   WORKER_MEDIA_BASE=https://your-worker.workers.dev
   LOGIN_PIN=2580
   FLASK_SECRET=random-string

2. Deploy Worker: wrangler deploy
3. Build Docker: docker build -t ia-drive . && docker run -p 8080:8080 --env-file .env ia-drive

Default PIN: 2580
