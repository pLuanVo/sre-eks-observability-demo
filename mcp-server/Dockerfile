FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache curl

COPY mcp-server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp-server/pyproject.toml ./
COPY mcp-server/config.py mcp-server/server.py mcp-server/webhook.py ./
COPY mcp-server/tools/ ./tools/

COPY sre/runbooks/ ./runbooks/

ENV MCP_TRANSPORT=sse RUNBOOK_DIR=/app/runbooks

EXPOSE 8090 8091

CMD ["python", "server.py"]
