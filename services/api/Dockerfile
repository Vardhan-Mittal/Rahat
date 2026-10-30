FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RAHAT_DB=/data/rahat.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user (uid 1000, as Hugging Face Spaces requires) with a writable data folder.
RUN useradd -m -u 1000 rahat && mkdir -p /data && chown rahat /data
USER rahat

# Run exactly one instance: the Telegram bot uses long polling, and two pollers on one token conflict.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
