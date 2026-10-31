FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_PATH=/app/data/projects.sqlite3 \
    TRUST_PROXY=1 \
    COOKIE_SECURE=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data \
    && chown app:app /app/data

COPY --chown=app:app server.py youtube.py index.html modals.html ./
COPY --chown=app:app css ./css
COPY --chown=app:app js ./js

USER app

EXPOSE 8000

CMD ["python", "server.py"]