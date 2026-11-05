FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . /app
RUN groupadd --gid 10001 qbc \
    && useradd --uid 10001 --gid 10001 --home-dir /home/qbc \
       --create-home --shell /usr/sbin/nologin qbc \
    && mkdir -p /ms-playwright /tmp \
    && chmod 1777 /tmp
USER qbc
