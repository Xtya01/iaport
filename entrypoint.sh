#!/bin/bash
set -e
mkdir -p /root/.config/rclone
cat > /root/.config/rclone/rclone.conf <<EOF
[ia]
type = s3
provider = Other
access_key_id = ${IA_ACCESS_KEY}
secret_access_key = ${IA_SECRET_KEY}
endpoint = https://s3.us.archive.org
acl = private
EOF

echo "Starting WebDAV on :8081..."
rclone serve webdav ia:${IA_BUCKET} --addr :8081 --user ia --pass "${LOGIN_PIN}" --vfs-cache-mode writes --buffer-size 128M --transfers 8 > /var/log/rclone.log 2>&1 &

echo "Starting Flask on :8080..."
exec su appuser -c "python /app/app.py"
