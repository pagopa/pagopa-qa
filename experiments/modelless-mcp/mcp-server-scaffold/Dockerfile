# Multi-stage build for the MCP server (MVP)
#
# Base images: Chainguard's Wolfi-based Python images (low-to-zero known CVEs,
# daily-rebuilt, minimal attack surface). The "-dev" variant (pip/shells/apk)
# is only used to build the virtualenv; the final runtime stage is the
# minimal, shell-less, package-manager-less "latest" variant which already
# runs as a non-root user by default. See:
# https://github.com/chainguard-images/images/tree/main/images/python
FROM cgr.dev/chainguard/python:latest-dev AS build

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

FROM cgr.dev/chainguard/python:latest AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/venv/bin:$PATH"

COPY --from=build /app/venv /app/venv
COPY app ./app
COPY assets ./assets
COPY manifests ./manifests

# The base image already runs as the non-root "nonroot" user; there is no
# runtime write path (assets are added by rebuilding the image from an
# updated repo, see manifests/ and the add-catalog-asset skill).

EXPOSE 8080

# Auth is validated at the edge (API Management) + in-app; /v1/health is public.
# Exec form only (no shell available in the minimal runtime image).
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys\ntry:\n    urllib.request.urlopen('http://127.0.0.1:8080/v1/health')\nexcept Exception:\n    sys.exit(1)"]

# Base image entrypoint is /usr/bin/python; pass module + args as CMD.
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8080"]
