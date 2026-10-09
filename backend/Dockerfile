# Recipe for the backend container: Python 3.10 + FastAPI + TensorFlow/MediaPipe.
# Installs the Python packages, copies the code, runs as a non-root user, and starts the
# API through entrypoint.sh. A health check pings /health so Docker knows when it is ready.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TF_CPP_MIN_LOG_LEVEL=2

# libGL/glib are needed by the OpenCV build that MediaPipe pulls in.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
# The cache mount keeps downloaded wheels between builds (not in the image), so a
# dropped connection during the 475 MB TensorFlow download doesn't start over.
RUN --mount=type=cache,target=/root/.cache/pip \
    unset PIP_NO_CACHE_DIR \
    && pip install --timeout 120 --retries 10 -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install --timeout 120 --retries 10 -r requirements-dev.txt; fi

COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/models \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["./entrypoint.sh"]
