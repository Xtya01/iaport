FROM python:3.11-slim

# Get rclone binary directly from official image (no apt)
COPY --from=rclone/rclone:1.68.1 /usr/local/bin/rclone /usr/bin/rclone

WORKDIR /app

RUN pip install --no-cache-dir \
    flask==3.0.0 \
    boto3==1.34.112 \
    requests==2.31.0 \
    internetarchive==3.6.0

COPY app.py file-manager.html entrypoint.sh ./
RUN chmod +x entrypoint.sh && useradd -m -u 1000 appuser && chown -R appuser:appuser /app

EXPOSE 8080 8081
CMD ["./entrypoint.sh"]
