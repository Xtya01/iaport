IA DRIVE - Complete Fixed Version

1. Configure:
   cp .env.example .env
   Edit .env with your IA keys from https://archive.org/account/s3.php

2. Build:
   docker compose up -d --build

3. Check:
   curl http://localhost:8080/health
   Should return: {"status":"ok","s3":true,"bucket":"..."}

4. Access:
   Web: http://your-ip:8080 (PIN: 2580)
   WebDAV: http://your-ip:8081 (user: ia, pass: 2580)

Logs:
   docker logs -f ia-drive

If /api/list returns empty, check logs for S3 errors.
