#!/usr/bin/env python

# Copyright 2025 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Entry point for the Google Analytics MCP server.

Supports two modes:
- stdio: Original mode for local CLI usage (default)
- http: HTTP server mode for multi-user deployments (Cloud Run, etc.)

HTTP mode extracts OAuth tokens from the Authorization header, enabling
per-user credentials in a multi-tenant environment.
"""

import os

from analytics_mcp.coordinator import mcp

# The following imports are necessary to register the tools with the `mcp`
# object, even though they are not directly used in this file.
from analytics_mcp.tools.admin import info  # noqa: F401
from analytics_mcp.tools.reporting import realtime  # noqa: F401
from analytics_mcp.tools.reporting import core  # noqa: F401


def run_server() -> None:
    """Runs the server in stdio mode.

    Serves as the entrypoint for the 'runmcp' command.
    This is the original behavior for local CLI usage.
    """
    mcp.run()


def run_http_server() -> None:
    """Runs the server in HTTP mode for multi-user deployments.

    Uses Starlette for HTTP handling. Extracts OAuth tokens from the
    Authorization header of each request, enabling per-user credentials.

    Environment variables:
    - PORT: HTTP port to listen on (default: 8080)
    - HOST: Host to bind to (default: 0.0.0.0)
    """
    import json
    import logging
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware

    from analytics_mcp.tools.utils import set_access_token, clear_access_token

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    async def health(request):
        """Health check endpoint for Cloud Run."""
        return JSONResponse({"status": "ok"})

    async def mcp_endpoint(request):
        """Handle MCP protocol requests over HTTP.

        This is a simplified HTTP-to-MCP bridge that:
        1. Extracts OAuth token from Authorization header
        2. Sets token in context
        3. Calls the appropriate MCP tool
        4. Returns the result

        Request format:
        {
            "method": "tools/call",
            "params": {
                "name": "get_account_summaries",
                "arguments": {}
            }
        }
        """
        # Extract access token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header. Use 'Bearer <token>'"},
                status_code=401
            )

        access_token = auth_header[7:]  # Remove "Bearer " prefix

        # Set the token in context for this request
        set_access_token(access_token)

        try:
            body = await request.json()
            method = body.get("method", "")
            params = body.get("params", {})

            if method == "tools/list":
                # List available tools
                tools = []
                for tool_name, tool_info in mcp._tool_manager._tools.items():
                    tools.append({
                        "name": tool_name,
                        "description": tool_info.description or "",
                        "inputSchema": tool_info.parameters or {}
                    })
                return JSONResponse({"tools": tools})

            elif method == "tools/call":
                # Call a specific tool
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if not tool_name:
                    return JSONResponse(
                        {"error": "Missing tool name"},
                        status_code=400
                    )

                # Get the tool function
                tool_info = mcp._tool_manager._tools.get(tool_name)
                if not tool_info:
                    return JSONResponse(
                        {"error": f"Unknown tool: {tool_name}"},
                        status_code=404
                    )

                # Call the tool
                import asyncio
                result = await tool_info.fn(**arguments)

                return JSONResponse({
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}]
                })

            elif method == "initialize":
                # MCP initialization
                return JSONResponse({
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "google-analytics-mcp",
                        "version": "0.1.1"
                    },
                    "capabilities": {
                        "tools": {}
                    }
                })

            else:
                return JSONResponse(
                    {"error": f"Unknown method: {method}"},
                    status_code=400
                )

        except Exception as e:
            logger.exception("Error handling MCP request")
            return JSONResponse(
                {"error": str(e)},
                status_code=500
            )
        finally:
            # Clear the token after request is processed
            clear_access_token()

    # Create app with CORS
    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/mcp", mcp_endpoint, methods=["POST", "OPTIONS"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ]
    )

    logger.info(f"Starting HTTP server on {host}:{port}")
    logger.info(f"Health check: http://{host}:{port}/health")
    logger.info(f"MCP endpoint: http://{host}:{port}/mcp")

    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    """Main entry point that selects server mode based on environment."""
    mode = os.environ.get("MCP_SERVER_MODE", "stdio").lower()

    if mode == "http":
        run_http_server()
    else:
        run_server()


if __name__ == "__main__":
    main()
