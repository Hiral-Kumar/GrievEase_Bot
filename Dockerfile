# GrievEase Bot backend — containerized for one-click deployment on any
# Docker-friendly host (Render, Railway, Fly.io, etc.). Using a plain
# Dockerfile rather than a platform-specific config keeps this portable:
# whichever free-tier host you pick, "deploy from Dockerfile" just works.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so Docker can cache this layer across rebuilds
# that only change application code, not requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# The SQLite DB file is written here at runtime (see app/core/database.py).
# On most free-tier hosts this resets on redeploy — fine for a screening
# demo; a real deployment would point DATABASE_URL at a managed Postgres
# instance instead (one-line change, see .env.example).
RUN mkdir -p /app/app/data

EXPOSE 8000

# $PORT is set by most hosts (Render, Railway) to tell the app which port
# to bind; falls back to 8000 for local `docker run`.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
