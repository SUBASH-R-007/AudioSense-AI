# Universal container for the AudioSense AI backend.
#
# One image works on Hugging Face Spaces, Koyeb, Fly.io, Google Cloud Run,
# Back4App and Render — they all accept a Dockerfile that listens on $PORT.
#
# Build context is the `backend` directory:
#   docker build -t audiosense-api ./backend
#   docker run -p 8000:8000 -e PORT=8000 audiosense-api

FROM python:3.11-slim

# libGL and libglib are the only system libraries OpenCV needs at runtime.
# The headless wheel avoids the rest of the GUI stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Matplotlib and Fontconfig both want a writable home; some platforms run
    # the container as a non-root user without one.
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp \
    PORT=8000

# Dependencies first so they stay cached when only application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No-op when the committed artifacts are present; trains them if they are not.
RUN python -m scripts.ensure_model

EXPOSE 8000

# Platforms inject $PORT at runtime, so the shell form is required to expand it.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
