FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -s https://rclone.org/install.sh | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir flask==3.0.0 boto3==1.34.0 requests==2.31.0 internetarchive==3.6.0

COPY app.py file-manager.html entrypoint.sh ./
RUN chmod +x entrypoint.sh && useradd -m -u 1000 appuser && chown -R appuser:appuser /app

EXPOSE 8080 8081
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8080/health || exit 1

CMD ["./entrypoint.sh"]
