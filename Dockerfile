FROM python:3.11-slim

# Install rclone and deps
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl https://rclone.org/install.sh | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir flask==3.0.0 internetarchive==3.6.0 requests==2.31.0 boto3==1.34.0

COPY app.py file-manager.html entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Create non-root for flask (rclone runs as root for mount)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

EXPOSE 8080 8081

HEALTHCHECK --interval=30s CMD curl -f http://localhost:8080/health || exit 1

CMD ["/app/entrypoint.sh"]
