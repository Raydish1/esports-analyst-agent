# The hosted server (deploy/README.md): the MCP server at /mcp and the demo page, with no model. The data (the live
# build, the legends and event logos) is never in this image: it's uploaded to the Fly volume at /data
# (deploy/bundle.py), which /app/data points at.
FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 CARD_BROWSER="" PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY deploy/requirements-hosted.txt deploy/requirements-hosted.txt
RUN pip install --no-cache-dir -r deploy/requirements-hosted.txt && playwright install --with-deps chromium

COPY agent agent
COPY app app
COPY curation curation
COPY ingest ingest
COPY deploy deploy
RUN ln -s /data /app/data && sed -i 's/$//' deploy/start.sh && chmod +x deploy/start.sh
$//" deploy/start.sh && chmod +x deploy/start.sh

EXPOSE 8080
CMD ["deploy/start.sh"]
