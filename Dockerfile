FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends iptables passwd \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . /app
RUN groupadd --gid 10001 qbc \
    && useradd --uid 10001 --gid 10001 --home-dir /home/qbc \
       --create-home --shell /usr/sbin/nologin qbc \
    && groupadd --gid 10002 qbcproxy \
    && useradd --uid 10002 --gid 10002 --home-dir /home/qbcproxy \
       --create-home --shell /usr/sbin/nologin qbcproxy \
    && mkdir -p /ms-playwright /tmp \
    && chmod 1777 /tmp
USER qbc
