FROM python:3.14-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir xhshow gmssl curl_cffi
# 安装 Playwright 浏览器（BROWSER_ENGINE=playwright 必需，否则容器内爬取必失败）
RUN python -m playwright install --with-deps chromium || true
# 可选：Camoufox 反检测浏览器（失败不阻塞主功能）
RUN python -m camoufox fetch || true
COPY . .
RUN mkdir -p output downloads logs browser_data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["python", "-m", "api.main"]
