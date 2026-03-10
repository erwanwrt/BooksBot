FROM python:3.12-slim

# System deps: Xvfb for Playwright headless=False
RUN apt-get update && \
    apt-get install -y --no-install-recommends xvfb && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

COPY *.py .

RUN mkdir -p downloads browser_data

# Start Xvfb then the bot
CMD Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & \
    sleep 1 && \
    exec python main.py
