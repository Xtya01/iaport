#!/bin/bash
set -e

# Configure rclone for Internet Archive
mkdir -p /root/.config/rclone
cat > /root/.config/rclone/rclone.conf <<EOF
[ia]
type = s3
provider = Other
env_auth = false
access_key_id = ${IA_ACCESS_KEY}
secret_access_key = ${IA_SECRET_KEY}
endpoint = https://s3.us.archive.org
acl = private
region = us-east-1
EOF

echo "Starting WebDAV on :8081 for bucket ${IA_BUCKET}"
# Start WebDAV in background
rclone serve webdav ia:${IA_BUCKET} \
  --addr :8081 \
  --user ia \
  --pass "${LOGIN_PIN}" \
  --vfs-cache-mode writes \
  --buffer-size 128M \
  --transfers 8 \
  --timeout 1h \
  --contimeout 60s \
  --low-level-retries 10 \
  --log-level INFO &
WEBDAV_PID=$!

echo "Starting Flask on :8080"
# Run Flask as appuser
su appuser -c "python /app/app.py" &
FLASK_PID=$!

# Wait for either to exit
wait -n
kill $WEBDAV_PID $FLASK_PID 2>/dev/null || true
