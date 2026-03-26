FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

ARG BASE_PATH=
ENV BASE_PATH=${BASE_PATH}

RUN npm run build


FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uv/bin/
COPY --from=mwader/static-ffmpeg:7.0 /ffprobe /ffmpeg /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_BREAK_SYSTEM_PACKAGES=1
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:/uv/bin:$PATH"
ENV HOME=/home/tommyskaraoke
ENV TOMMYSKARAOKE_MODEL_CACHE_DIR=/models

ARG BASE_PATH=
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG INSTALL_SEPARATION_DEPS=1

ENV BASE_PATH=${BASE_PATH}

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --no-cache-dir -r pyproject.toml && \
    uv pip install pip

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_SEPARATION_DEPS" = "1" ]; then \
      uv pip install --no-cache-dir --index-url "$TORCH_INDEX_URL" torch torchaudio && \
      uv pip install --no-cache-dir "demucs>=4.0.1" "librosa>=0.10.0" "soundfile>=0.12.0" "tqdm>=4.30" "numpy>=1.21.0" "audio-separator>=0.43.0"; \
    fi

COPY docs ./docs
COPY tommyskaraoke ./tommyskaraoke
COPY frontend/package.json ./frontend/package.json
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache-dir --no-deps .

RUN adduser --disabled-password --gecos "" --uid 1000 tommyskaraoke && \
    mkdir -p /home/tommyskaraoke/.tommyskaraoke /app/tommyskaraoke-songs /models && \
    chown -R tommyskaraoke:tommyskaraoke /app /home/tommyskaraoke /models

VOLUME ["/app/tommyskaraoke-songs", "/home/tommyskaraoke/.tommyskaraoke", "/models"]
EXPOSE 5555

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5555/ || exit 1

USER tommyskaraoke

ENTRYPOINT ["python", "-m", "tommyskaraoke.app_fastapi", "-d", "/app/tommyskaraoke-songs/", "--headless"]
