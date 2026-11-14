# Playwright base image ships Chromium + all system libraries it needs.
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY static ./static
# one process: API + queue workers + monitor loop (Render free = 512 MB)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
