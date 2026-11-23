# Backend image. Build context is the project root (see docker-compose.dev.yml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

# Install packages first, so code changes do not reinstall everything.
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ /app/backend/

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
