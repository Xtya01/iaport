# IA Drive - LOW Auth Edition

Fixed version that uses Internet Archive's documented LOW authorization instead of boto3.

## Problem we solved
- boto3 AWS4 signing → InvalidAccessKeyId on new IA accounts
- curl with `Authorization: LOW key:secret` → 200 OK
- This app uses direct PUT with LOW auth

## Features
- x-amz-auto-make-bucket:1 (auto creates item)
- x-archive-queue-derive:0 (instant, no OCR)
- x-archive-interactive-priority:1
- PIN login (default 2383)
- Lists files via archive.org/metadata API

## Deploy to Portainer
1. Stacks → Add stack → Upload docker-compose.yml
2. Or build from GitHub: point to repo containing these files
3. Set env vars, deploy

## Deploy locally
docker compose up -d --build

Access http://localhost:8080

## Security
Rotate keys after testing - they were posted publicly in chat.
