IA Drive with WebDAV
==================

Features:
- Web UI on port 8080 (upload, browse, stream)
- WebDAV on port 8081 (mount as network drive)
- Multipart uploads for 15GB+ files
- Auto-detect URL size

Setup:
1. Set env vars in .env:
   IA_ACCESS_KEY=xxx
   IA_SECRET_KEY=yyy

2. Build:
   docker compose up -d --build

3. Web UI: http://your-ip:8080 (PIN: 2580)
4. WebDAV: 
   Windows: Map network drive to http://your-ip:8081
   User: ia / Pass: 2580
   macOS: Finder > Connect > http://your-ip:8081

Upload limits:
- Web UI: unlimited via multipart
- WebDAV: unlimited (rclone handles chunking)
- URL uploads: auto-switches to direct for >1GB
