# IA Drive

Self-hosted Internet Archive file manager with permanent storage.

## Features
- Drag & drop upload
- URL fetch with live progress (KB/MB/GB, speed, ETA)
- Dedicated pages for each file: /file/video.mp4
- Video/audio/image/PDF preview
- SQLite history (persists across restarts)
- PIN login
- Mobile responsive

## Deploy (Portainer + GitHub)

1. Push all files to GitHub repo
2. Portainer → Stacks → Add Stack → Repository
3. Set repository URL
4. Add environment variables:
   - IA_BUCKET
   - IA_ACCESS_KEY
   - IA_SECRET_KEY
   - LOGIN_PIN
   - WORKER_MEDIA_BASE (optional)
5. Deploy

Data persists in Docker volume `ia-drive-data` → `/data/history.db`

## Local
```bash
docker-compose up --build
