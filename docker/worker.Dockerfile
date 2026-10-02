# Worker image: the processing pipeline, with the GPU through the NVIDIA runtime (Docker Desktop on WSL 2).
FROM python:3.12-slim

# build-essential: diffq (a dependency of audio-separator) compiles a C extension.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

# yt-dlp needs an external JavaScript runtime for YouTube; Deno is its default.
ARG DENO_VERSION=2.9.7
RUN curl -fsSL -o /tmp/deno.zip \
      "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" \
 && unzip -q /tmp/deno.zip -d /usr/local/bin \
 && rm /tmp/deno.zip

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    KARAOKE_DATA=/data \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first, in their own layer: PyTorch with CUDA is the largest download and rarely changes.
# uv's download cache lives in a build cache mount, not in the image (it would double the image's size).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra worker --no-install-project
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra worker

ENTRYPOINT ["karaoke"]
