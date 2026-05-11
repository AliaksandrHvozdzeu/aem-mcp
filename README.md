# AEM Page Analyzer — MCP + Ollama + AEM 6.5

An educational project that demonstrates the full **Model Context Protocol (MCP)** cycle in a real-world scenario: an AI agent analyzes Adobe Experience Manager pages by calling MCP tools, with a modern browser UI embedded directly inside AEM.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser / AEM Tool Page                                        │
│  http://localhost:4502/content/hvozdzeu/tools/page-analyzer     │
└───────────────┬─────────────────────────────────────────────────┘
                │  POST /analyze  (JSON body: {url: "..."})
                ▼
┌───────────────────────────┐
│  analyzer_api.py          │  HTTP server · port 5001
│  (Python · ThreadingHTTP) │  Streams SSE events back to browser
└──────┬────────────────────┘
       │  stdio (subprocess)          │  HTTP /api/chat
       ▼                              ▼
┌─────────────┐              ┌────────────────────┐
│  server.py  │              │  Ollama             │
│  MCP Server │◄─ tool call ─│  model: qwen3.6     │
│  (FastMCP)  │─ tool result─►│  port 11434        │
└──────┬──────┘              └────────────────────┘
       │  HTTP GET  *.infinity.json
       ▼
┌─────────────────────────────┐
│  AEM 6.5                    │
│  http://localhost:4502      │
│  /content/hvozdzeu/...      │
└─────────────────────────────┘
```

**Step-by-step flow:**

1. The user enters an AEM page path in the browser UI and clicks **Analyze Page**.
2. The browser sends a `POST /analyze` request to `analyzer_api.py` (port 5001).
3. `analyzer_api.py` spawns `server.py` as a subprocess (MCP stdio transport) and opens an Ollama chat session.
4. Ollama receives a system prompt + user question, then decides which MCP tools to call.
5. Each tool call is forwarded to `server.py`, which fetches the live AEM JSON.
6. Tool results are returned to Ollama for the final structured report.
7. Every step is streamed back to the browser in real time via **Server-Sent Events (SSE)**.

---

## Project Structure

```
d:\AI\MCP\
├── ollama-mcp-tutorial\
│   ├── server.py          # MCP server — 4 AEM analysis tools
│   ├── client.py          # CLI client — manual tool calling loop
│   ├── analyzer_api.py    # HTTP/SSE bridge between AEM UI and MCP
│   └── requirements.txt   # Python dependencies
│
└── aem\                   # AEM 6.5 Maven project
    ├── core\              # OSGi bundle (Sling Models)
    ├── ui.apps\
    │   └── .../apps/hvozdzeu/
    │       ├── components/
    │       │   ├── analyzer-tool/
    │       │   │   └── analyzer-tool.html   ← Page Analyzer UI
    │       │   ├── hero/
    │       │   ├── text-block/
    │       │   ├── concept-card/
    │       │   ├── key-points/
    │       │   └── code-snippet/
    │       └── templates/
    └── pom.xml
```

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | For MCP server and API |
| Java | 17 | For AEM / Maven build |
| Maven | 3.8+ | Build tool for AEM |
| Node.js | 18+ | Optional — MCP Inspector only |
| Ollama | latest | Local LLM runtime |
| AEM | 6.5 | Must be running on port 4502 |

---

## Quick Start

### 1. Python Environment

```powershell
# From the ollama-mcp-tutorial folder
cd ollama-mcp-tutorial

python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

pip install -r requirements.txt
```

**Verify:**
```powershell
python -c "from mcp.server.fastmcp import FastMCP; print('MCP OK')"
python -c "import httpx; print('httpx OK')"
```

---

### 2. Ollama — Install & Pull Model

1. Download and install Ollama from [ollama.com/download](https://ollama.com/download).

2. Start the Ollama server (it may already run as a background service):
   ```powershell
   ollama serve
   ```

3. Pull the model used by this project:
   ```powershell
   ollama pull qwen3.6
   ```

4. Verify:
   ```powershell
   curl http://localhost:11434/api/tags
   # Should list "qwen3.6" in the models array
   ```

> **Why qwen3.6?** It reliably supports multi-step tool calling, which is required for the MCP loop to work.

---

### 3. AEM — Build & Deploy

> AEM 6.5 must be running at `http://localhost:4502` before deploying.

```powershell
cd aem
mvn clean install -P autoInstallPackage
```

This builds the OSGi bundle (`core`) and the content package (`ui.apps`), then installs both into your local AEM instance.

**Verify the Page Analyzer is deployed:**
Open `http://localhost:4502/content/hvozdzeu/tools/page-analyzer.html` — you should see the analyzer UI.

**Test content page:**
Open `http://localhost:4502/content/hvozdzeu/en/mcp-principles.html` — the MCP Principles page used as a demo target.

---

### 4. Start the Analyzer API

The API server bridges the browser and the MCP+Ollama stack.

```powershell
cd ollama-mcp-tutorial
.venv\Scripts\Activate.ps1

python analyzer_api.py
```

Expected output:
```
[API] AEM Page Analyzer API running at http://localhost:5001
[API] Model: qwen3.6  |  MCP: server.py
[API] POST http://localhost:5001/analyze  {"url": "...infinity.json"}
[API] Press Ctrl+C to stop.
```

**Health check:**
```powershell
curl http://localhost:5001/
# {"status": "ok", "model": "qwen3.6"}
```

---

### 5. Run an Analysis

Open the AEM tool page in your browser:

```
http://localhost:4502/content/hvozdzeu/tools/page-analyzer.html
```

1. The **API badge** in the top-right corner turns green when `analyzer_api.py` is reachable.
2. Enter a page path or click the **MCP Principles** quick-select button.
3. Click **Analyze Page**.
4. Watch the **pipeline diagram** highlight each step in real time.
5. Read the final **AI Analysis Report** rendered as rich Markdown.

---

## MCP Tools (server.py)

The MCP server exposes four tools that the AI model can call:

| Tool | Description |
|------|-------------|
| `fetch_aem_json` | Fetches raw JSON from any AEM `.infinity.json` URL |
| `get_page_content` | Extracts all human-readable text from an AEM page |
| `analyze_page_components` | Lists all components with their JCR paths and content |
| `compare_pages` | Compares two AEM pages: structure and content diff |

---

## CLI Client (client.py)

For terminal-based analysis without the browser UI:

```powershell
cd ollama-mcp-tutorial
.venv\Scripts\Activate.ps1
python client.py
```

The script runs the same MCP + Ollama cycle in the console and prints a full analysis of the MCP Principles page.

**What you'll see:**
```
[Ollama] Model 'qwen3.6' is available.
[MCP] Starting MCP server...
[MCP] Server ready.
[MCP] Available tools: ['fetch_aem_json', 'get_page_content', 'analyze_page_components', 'compare_pages']
[User] Analyze the AEM page at: http://localhost:4502/content/...
[Ollama] Sending request with tools...
[Intercept] Model requested 2 tool call(s):
  → Tool: analyze_page_components  → {"url": "..."}
  ← Result: Component structure ...
  → Tool: get_page_content         → {"url": "..."}
  ← Result: Page text content ...
[Ollama] Sending tool results, waiting for final response...
[Assistant] <structured markdown report>
[MCP] Server stopped.
```

---

## Debugging with MCP Inspector

MCP Inspector is an official browser-based tool for testing MCP servers interactively (no Ollama required).

```powershell
# Requires Node.js 18+
npx @modelcontextprotocol/inspector python server.py
```

Open the URL printed in the console (usually `http://localhost:6274`).

- **Tools tab → List Tools** — see all four tools with their JSON Schema.
- **Call a tool manually** — paste an AEM URL as the argument.
- **Messages tab** — inspect raw JSON-RPC 2.0 frames.

---

## SSE Event Reference

`analyzer_api.py` streams the following events to the browser:

| Event type | Payload fields | Meaning |
|------------|---------------|---------|
| `progress` | `message` | Status text (server starting, model queried, …) |
| `tools_loaded` | `tools: string[]` | List of MCP tool names now available |
| `tool_call` | `name`, `args` | Model is calling this tool with these arguments |
| `tool_result` | `name`, `preview`, `chars` | Tool returned N chars; preview of first 400 |
| `final` | `answer` | Complete Markdown analysis report |
| `error` | `message` | Something went wrong |
| `done` | — | Stream closed cleanly |

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **MCP (Model Context Protocol)** | Open standard by Anthropic for LLM ↔ tool communication over JSON-RPC 2.0 |
| **FastMCP** | Python library that turns decorated functions into MCP tools with one line |
| **stdio transport** | MCP server runs as a subprocess; messages flow over stdin/stdout |
| **Manual Tool Calling** | The client intercepts `tool_calls` from the model, executes them via MCP, and feeds results back — no framework magic |
| **Server-Sent Events (SSE)** | One-way HTTP stream from server to browser for real-time progress updates |
| **AEM `.infinity.json`** | Sling's built-in serialization of a JCR subtree to JSON; appending `.infinity.json` to any AEM path returns its full content tree |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'mcp'`**
→ Activate the virtual environment first: `.venv\Scripts\Activate.ps1`

**`Cannot connect to Ollama at http://localhost:11434`**
→ Start Ollama: `ollama serve`

**`model 'qwen3.6' not found`**
→ Pull the model: `ollama pull qwen3.6`

**AEM page analyzer shows a blank white page**
→ Ensure `ui.apps` was deployed: `cd aem && mvn clean install -P autoInstallPackage`

**API badge stays orange ("API offline")**
→ Make sure `analyzer_api.py` is running: `python analyzer_api.py`

**Analysis hangs or times out**
→ The model may be generating a very long response. The timeout is set to 300 s.  
→ Try a smaller page or reduce the prompt scope in `analyzer_api.py`.

**Garbled characters in the AEM UI**
→ Ensure the `analyzer-tool.html` file is saved as **UTF-8** (the Maven build preserves encoding).

**Model calls no tools / returns empty**
→ `qwen3.6` is confirmed to work. If you switch models, verify tool-calling support with `client.py` first.
