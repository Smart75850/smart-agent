FROM python:3.14-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir xhshow gmssl curl_cffi
COPY . .
RUN mkdir -p output downloads logs browser_data
EXPOSE 8000
CMD ["python", "-m", "api.main"]
