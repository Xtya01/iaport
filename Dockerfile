FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y aria2 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN mkdir -p /data /tmp/downloads
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "app.py"]
