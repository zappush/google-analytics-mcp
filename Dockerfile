FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy source code
COPY analytics_mcp ./analytics_mcp

# Set environment for HTTP mode
ENV MCP_SERVER_MODE=http
ENV PORT=8080
ENV HOST=0.0.0.0

EXPOSE 8080

# Run the HTTP server
CMD ["python", "-m", "analytics_mcp.server"]
