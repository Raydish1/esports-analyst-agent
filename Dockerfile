# The hosted server (deploy/README.md): the MCP server at /mcp and the demo page, with no model. The data (the live
# build, the legends and event logos) is never in this image: it's uploaded to the Fly volume at /data
# (deploy/bundle.py), which /app/data points at.
FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 CARD_BROWSER="" PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY deploy/requirements-hosted.txt deploy/requirements-hosted.txt
# Playwright's own driver needs libatomic, which the slim image lacks; --with-deps then installs Chromium's libraries
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/* \n    && pip install --no-cache-dir -r deploy/requirements-hosted.txt && playwright install --with-deps chromium

COPY agent agent
COPY app app
COPY curation curation
COPY ingest ingest
COPY deploy deploy
# start.sh may arrive with Windows line endings from a Windows checkout: strip them
RUN ln -s /data /app/data && tr -d '\015' < deploy/start.sh > /tmp/start.sh && mv /tmp/start.sh deploy/start.sh \
    && chmod +x deploy/start.sh

EXPOSE 8080
CMD ["deploy/start.sh"]
