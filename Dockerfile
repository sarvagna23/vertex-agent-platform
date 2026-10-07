FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The MCP server runs as a subprocess of the API (python -m mcp_server.server), so it ships in the same image.
COPY config.py ./
COPY mcp_server ./mcp_server
COPY agents ./agents
COPY pii ./pii
COPY api ./api

# Cloud Run injects PORT.
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
