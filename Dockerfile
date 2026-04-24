FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    flask==3.0.0 \
    internetarchive==3.6.0 \
    requests==2.31.0 \
    boto3==1.34.0 \
    botocore==1.34.0

# Copy app files
COPY app.py /app/app.py
COPY file-manager.html /app/file-manager.html

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Environment defaults
ENV FLASK_SECRET=change-me-in-production \
    LOGIN_PIN=2580 \
    IA_BUCKET=junk-manage-caution \
    WORKER_MEDIA_BASE=https://your-worker.workers.dev \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=2)"

CMD ["python", "app.py"]
