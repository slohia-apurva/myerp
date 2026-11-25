# Production image: the React app built once, served by Django (WhiteNoise)
# from the same origin as the API. Used by the staging deploy workflow.
# Local development uses docker-compose.yml and backend/Dockerfile instead.

FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000
WORKDIR /app
# DejaVu fonts carry the rupee sign for printed PDFs (core/printout.py).
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=frontend /frontend/dist ./frontend_dist
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app
EXPOSE 8000
# --preload imports Django in the master before the workers fork, so a new
# instance does that work while Cloud Run is still starting it (with the startup
# CPU boost) instead of inside the first person's request: locally the first
# request drops from 0.61 s to 0.20 s (2026-11-25).
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 --preload"]
