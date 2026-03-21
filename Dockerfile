FROM python:3.11-slim

ARG VERSION=latest
ENV VERSION=$VERSION

# Install curl
RUN apt-get update && apt-get install -y curl

WORKDIR /app

COPY . /temp/pytradingbot

RUN if [ "$VERSION" = "latest" ]; then \
      cd /temp/pytradingbot && pip install --upgrade pip uv && uv pip install . --system && rm -rf /temp/pytradingbot; \
    else \
      pip install --upgrade pip uv && uv pip install "pytradingbot==$VERSION"; \
    fi

COPY healthcheck.sh /healthcheck.sh
RUN chmod +x /healthcheck.sh

HEALTHCHECK --start-period=2s --interval=5s --timeout=3s \
    CMD /healthcheck.sh || exit 1

ENTRYPOINT ["pytradingbot", "start"]
