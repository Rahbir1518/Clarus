# Deliberately host-agnostic. The previous backend was tied to a Render
# blueprint; this image runs anywhere that takes a container.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies resolve in their own layer so source edits don't reinstall them.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY migrations ./migrations

# Run unprivileged.
RUN useradd --create-home --uid 10001 clarus && chown -R clarus:clarus /app
USER clarus

# Hosts tell the container which port to serve on through $PORT (Render sets
# 10000 and fails the deploy if nothing listens there); 8000 when none does.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT']).read()"

# Shell form so $PORT expands; exec so uvicorn stays PID 1 and gets SIGTERM.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\""]
