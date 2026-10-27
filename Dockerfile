# Build the Tailwind CSS with the standalone CLI (no Node.js), so the running app needs
# no CDN. The output is architecture-independent, so this stage runs natively on the
# build host even for multi-arch builds.
FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS css
ARG BUILDARCH
ARG TAILWIND_VERSION=3.4.17
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN case "$BUILDARCH" in amd64) arch=x64 ;; arm64) arch=arm64 ;; *) echo "unsupported: $BUILDARCH" >&2; exit 1 ;; esac \
    && curl -fsSL -o /usr/local/bin/tailwindcss \
       "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-${arch}" \
    && chmod +x /usr/local/bin/tailwindcss
WORKDIR /src
COPY tailwind/ tailwind/
COPY app/templates/ app/templates/
COPY app/static/js/ app/static/js/
RUN tailwindcss -c tailwind/tailwind.config.js -i tailwind/input.css -o tailwind.css --minify

FROM python:3.12-slim

# Shared libraries needed by opencv-python (pulled in by rapidocr_onnxruntime).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ARG GIT_HASH=unknown
ENV GIT_HASH=$GIT_HASH

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=css /src/tailwind.css app/static/css/tailwind.css

RUN mkdir -p instance uploads

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
