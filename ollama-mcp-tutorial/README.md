# ollama-mcp-tutorial

This folder contains the Python components of the AEM Page Analyzer project:

| File | Role |
|------|------|
| `server.py` | MCP server — exposes 4 AEM analysis tools via FastMCP (stdio transport) |
| `client.py` | CLI client — runs the full MCP + Ollama analysis loop in the terminal |
| `analyzer_api.py` | HTTP server (port 5001) — bridges the AEM browser UI to MCP + Ollama via SSE |
| `requirements.txt` | Python dependencies |

**Full documentation, architecture diagram, and setup instructions are in the root README:**  
[`../README.md`](../README.md)

---

## Minimal Quick Start

```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pull the required Ollama model (once)
ollama pull qwen3.6

# 4. Start the Analyzer API (keeps running — open a dedicated terminal)
python analyzer_api.py

# 5. (Optional) Run CLI analysis directly in the terminal
python client.py
```

Then open the AEM tool page in your browser:
```
http://localhost:4502/content/hvozdzeu/tools/page-analyzer.html
```
