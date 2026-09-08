# Builds the SentinelAI backend (apps/api) — one image, two roles.
# Build context is the repo root so this image can be produced the same
# way from docker-compose and CI without special-casing a subdirectory
# context.
#
# Milestone F5: `docker-compose.yml`'s `api` service runs
# `uvicorn app.main:app` from this image; its `worker` service runs
# `python -m app.worker.main` from the *same* image (a different
# `command:`, not a second Dockerfile) — API and worker always run the
# exact same application code, never two builds that can drift apart.
#
# CPU-only by construction: plain `python:3.12-slim` (no CUDA base
# image), `torch`/`torchvision` installed from the PyTorch CPU wheel
# index explicitly — must build and run correctly with no GPU present,
# matching every developer's actual machine.

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Pillow/psycopg[binary] need no system build toolchain beyond this.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/ ./

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu .

# A persistent, named volume (see docker-compose.yml's `model-cache`)
# should be mounted at these paths so the CLIP checkpoint downloads once
# and survives container restarts/rebuilds. open_clip_torch resolves its
# checkpoint through huggingface_hub (HF_HOME) and/or torch.hub
# (TORCH_HOME) depending on the pretrained tag; both point at the same
# volume.
ENV HF_HOME=/model-cache
ENV TORCH_HOME=/model-cache
RUN mkdir -p /model-cache storage/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
