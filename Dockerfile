# Smart Agent Pro — Multi-stage Docker build
# Stage 1: dependencies (browsers are large, cache this layer)
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Playwright + Camoufox (Firefox) system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnspr4 libnss3 libexpat1 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 \
    libxi6 libxrandr2 libxrender1 libxtst6 libglib2.0-0 \
    libdbus-1-3 libasound2 libatk-bridge2.0-0 libatspi2.0-0 \
    libcups2 libdrm2 libgbm1 libpango-1.0-0 libcairo2 \
    fonts-noto-color-emoji fonts-unifont \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install python-dotenv

# Install Playwright browsers (Chromium + Firefox for Camoufox)
RUN playwright install --with-deps chromium firefox

# Stage 2: application
FROM base AS app

# Create non-root user
RUN useradd --create-home --shell /bin/bash smartagent \
    && mkdir -p /app/output /app/downloads /app/browser_data \
    && chown -R smartagent:smartagent /app

COPY --chown=smartagent:smartagent . .

USER smartagent

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/config || exit 1

CMD ["python", "-m", "api.main"]
