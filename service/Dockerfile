FROM python:3.13-slim

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
USER transport

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v2/health', timeout=3).status == 200 else 1)"

# --proxy-headers with the forwarded address trusted: the caller's IP and
# User-Agent are what search.ch applies its rate limit to, so losing them puts
# every caller in the world into one bucket. The container is never published
# directly, only reached through the proxy on the compose network.
CMD ["sh", "-c", "exec python -m uvicorn transport_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers ${WEB_CONCURRENCY:-2}"]
