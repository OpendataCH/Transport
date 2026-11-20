FROM python:3.14-slim

# tzdata, because the image has to know what Europe/Zurich means. The PHP
# application sets the zone at boot and its timestamps carry no offset, so a
# container on UTC answers beside the truth without failing anything.
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Europe/Zurich

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# The dependency layer on its own, so that a code change does not reinstall
# the world. The package itself is copied afterwards.
COPY pyproject.toml README.md ./
COPY transport_api ./transport_api
RUN pip install .

# CI stamps the short commit SHA here; /v2/health reports it, which is how a
# deployment is checked without reading the compose file.
ARG SERVICE_VERSION=dev
ENV SERVICE_VERSION=${SERVICE_VERSION}

RUN useradd --system --no-create-home --uid 10001 transport

# Where the ingest loop keeps the downloaded GTFS feed. Created here, owned by
# the service user, so that a named volume mounted on it starts out writable.
RUN mkdir -p /var/cache/gtfs && chown transport /var/cache/gtfs
ENV GTFS_CACHE=/var/cache/gtfs

USER transport

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v2/health', timeout=3).status == 200 else 1)"

# The forwarded-header handling is inside the application, not a flag here -
# see main.py, where it is explained and tested. The container is never
# published directly, only reached through the proxy in front of it.
# --no-access-log: the proxy in front keeps the access log, for a set number of
# days. uvicorn's own would be a second copy of every caller's address and
# query - coordinates included - in the container log, with no say over how
# long it stays.
# --http: uvicorn's own parser, but taking raw UTF-8 in the URL - see raw_utf8.py.
CMD ["sh", "-c", "exec python -m uvicorn transport_api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --no-access-log --http transport_api.raw_utf8:RawUtf8HttpToolsProtocol"]
