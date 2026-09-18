FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 1000 botuser

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY bot ./bot

RUN mkdir -p /app/data && chown -R botuser:botuser /app

USER botuser

VOLUME ["/app/data"]

CMD ["python", "-m", "bot.main"]
