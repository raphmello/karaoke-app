# Phase 0 spike image: everything the measurements need, GPU via the NVIDIA runtime.
FROM python:3.12-slim

# build-essential: diffq (a Demucs dependency) compiles a C extension.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg rubberband-cli curl unzip ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

# yt-dlp needs an external JavaScript runtime for YouTube; Deno is its default.
RUN curl -fsSL -o /tmp/deno.zip https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip \
 && unzip -q /tmp/deno.zip -d /usr/local/bin \
 && rm /tmp/deno.zip \
 && deno --version

# Own layer: the CUDA build of PyTorch is the largest download and rarely changes.
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# faster-whisper (CTranslate2) loads cuBLAS and cuDNN from the pip-installed NVIDIA wheels.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib

WORKDIR /spike/scripts
