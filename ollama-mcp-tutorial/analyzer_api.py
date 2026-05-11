"""
=============================================================================
AEM PAGE ANALYZER API — analyzer_api.py
=============================================================================

HTTP server on port 5001 that accepts requests from the AEM tool page
(or any browser) and runs an MCP-powered page analysis via Ollama.

Uses Server-Sent Events (SSE) to stream progress in real time:
  Browser → POST /analyze → server → MCP + Ollama → SSE events → browser

SSE events (each is a JSON line):
  {type: "progress",     message: "..."}     — status text
  {type: "tools_loaded", tools: [...]}        — list of MCP tools
  {type: "tool_call",    name, args}          — model is calling a tool
  {type: "tool_result",  name, preview}       — tool execution result
  {type: "final",        answer: "..."}       — final model response
  {type: "error",        message: "..."}      — error

Usage:
  python analyzer_api.py
  → server listens at http://localhost:5001
=============================================================================
"""

import sys
import json
import asyncio

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# =============================================================================
# CONFIGURATION
# =============================================================================
PORT          = 5001
OLLAMA_URL    = "http://localhost:11434"
OLLAMA_MODEL  = "qwen3.6"
SERVER_PARAMS = StdioServerParameters(command="python", args=["server.py"])


# =============================================================================
# ANALYSIS LOGIC
# =============================================================================

def get_mcp_tools_for_ollama(tools: list) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


async def analyze_page(page_url: str, emit):
    """
    Full page analysis cycle with an emit() callback for SSE events.

    emit(event_type, data_dict) is called at each step —
    the HTTP handler immediately sends it to the browser as an SSE event.
    """
    emit("progress", {"message": "Starting MCP server..."})

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            emit("progress", {"message": "MCP server ready."})

            tools_result = await session.list_tools()
            mcp_tools    = tools_result.tools
            emit("tools_loaded", {"tools": [t.name for t in mcp_tools]})

            ollama_tools = get_mcp_tools_for_ollama(mcp_tools)

            question = (
                f"Analyze the AEM page at: {page_url}. "
                "Use analyze_page_components to inspect component structure "
                "and get_page_content to read all text. "
                "Then write a structured report with: components overview, "
                "content summary, and key observations."
            )

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AEM (Adobe Experience Manager) content analyst. "
                        "Analyze pages using the available tools and produce clear, "
                        "structured reports in Markdown. Be concise but thorough."
                    ),
                },
                {"role": "user", "content": question},
            ]

            emit("progress", {"message": f"Asking {OLLAMA_MODEL} to analyze the page..."})

            async with httpx.AsyncClient() as http:
                # First request — model decides which tools to call
                try:
                    resp = await http.post(
                        f"{OLLAMA_URL}/api/chat",
                        json={"model": OLLAMA_MODEL, "messages": messages,
                              "tools": ollama_tools, "stream": False},
                        timeout=120.0,
                    )
                    resp.raise_for_status()
                except httpx.ConnectError:
                    emit("error", {"message": f"Cannot connect to Ollama at {OLLAMA_URL}. Is it running?"})
                    return
                except httpx.HTTPStatusError as e:
                    emit("error", {"message": f"Ollama HTTP {e.response.status_code}: model '{OLLAMA_MODEL}' not found? Run: ollama pull {OLLAMA_MODEL}"})
                    return

                assistant_msg = resp.json()["message"]
                tool_calls    = assistant_msg.get("tool_calls", [])

                if not tool_calls:
                    # Model answered without calling any tools
                    emit("final", {"answer": assistant_msg.get("content", "(no response)")})
                    return

                emit("progress", {"message": f"Model requested {len(tool_calls)} tool call(s). Executing..."})
                messages.append(assistant_msg)

                # Execute each tool via MCP
                for tc in tool_calls:
                    func      = tc["function"]
                    tool_name = func["name"]
                    raw_args  = func.get("arguments", {})
                    tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                    emit("tool_call", {"name": tool_name, "args": tool_args})

                    result      = await session.call_tool(tool_name, tool_args)
                    result_text = ""
                    if result.content:
                        result_text = getattr(result.content[0], "text", str(result.content[0]))

                    # Send a preview (not the full text — it can be very large)
                    preview = result_text[:400] + ("..." if len(result_text) > 400 else "")
                    emit("tool_result", {"name": tool_name, "preview": preview,
                                        "chars": len(result_text)})

                    messages.append({"role": "tool", "content": result_text})

                # Second request — final answer based on tool results
                emit("progress", {"message": "Generating final analysis report..."})

                try:
                    final_resp = await http.post(
                        f"{OLLAMA_URL}/api/chat",
                        json={"model": OLLAMA_MODEL, "messages": messages,
                              "tools": ollama_tools, "stream": False},
                        timeout=300.0,
                    )
                    final_resp.raise_for_status()
                except httpx.ReadTimeout:
                    emit("error", {"message": "Timeout waiting for final response. Try a simpler question."})
                    return

                final_answer = final_resp.json()["message"]["content"]
                emit("final", {"answer": final_answer})


# =============================================================================
# HTTP SERVER WITH SSE
# =============================================================================

class AnalyzerHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[API] {self.address_string()} - {fmt % args}")

    def _cors(self):
        """Add CORS headers for requests from AEM (localhost:4502)."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        """CORS preflight request from the browser before POST."""
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        """Health-check: GET / → 200 OK."""
        body = json.dumps({"status": "ok", "model": OLLAMA_MODEL}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/analyze":
            self.send_response(404)
            self.end_headers()
            return

        # Read request body
        length   = int(self.headers.get("Content-Length", 0))
        body     = json.loads(self.rfile.read(length)) if length else {}
        page_url = body.get("url", "").strip()

        if not page_url:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing 'url' field"}).encode())
            return

        # Open the SSE stream
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

        def emit(event_type: str, data: dict):
            """Send a single SSE event to the client."""
            payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
            line    = f"data: {payload}\n\n"
            try:
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except BrokenPipeError:
                pass  # Client closed the connection

        # Run the async analysis in this thread
        try:
            asyncio.run(analyze_page(page_url, emit))
        except Exception as exc:
            emit("error", {"message": str(exc)})
        finally:
            # End-of-stream signal
            try:
                self.wfile.write(b"data: {\"type\":\"done\"}\n\n")
                self.wfile.flush()
            except Exception:
                pass


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AnalyzerHandler)
    print(f"[API] AEM Page Analyzer API running at http://localhost:{PORT}")
    print(f"[API] Model: {OLLAMA_MODEL}  |  MCP: server.py")
    print(f"[API] POST http://localhost:{PORT}/analyze  {{\"url\": \"...infinity.json\"}}")
    print(f"[API] Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[API] Stopped.")
