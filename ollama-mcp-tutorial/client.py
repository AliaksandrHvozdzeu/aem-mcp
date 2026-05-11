"""
=============================================================================
EDUCATIONAL MCP CLIENT — client.py
=============================================================================

This script demonstrates the "Manual Tool Calling" pattern:
  1. Send the user message to Ollama.
  2. Ollama returns a response requesting a tool call (tool_call).
  3. We INTERCEPT that request and call our MCP server.
  4. We send the tool result back to Ollama.
  5. Ollama produces the final response for the user.

Interaction diagram:
  ┌──────────┐  1. message     ┌─────────┐  3. tools/call  ┌────────────┐
  │   This   │ ──────────────► │  Ollama │ ───────────────► │    MCP     │
  │  script  │ ◄────────────── │  (LLM)  │ ◄─────────────── │   server   │
  └──────────┘  2. tool_call   └─────────┘  4. result       └────────────┘
                5. final answer ↑

Why "Manual"?
  Unlike automatic frameworks (LangChain, LlamaIndex),
  here WE control the loop: we see the raw JSON from the model, we decide
  when and how to call MCP, and we construct the reply messages ourselves.

Important note on transport:
  The MCP Python SDK uses a stdio transport with special message framing
  (based on anyio streams), which is incompatible with plain readline().
  We therefore use the official ClientSession from the SDK to communicate
  with the server — it handles all low-level protocol work.
=============================================================================
"""

import sys
import json                              # JSON parsing for model requests
import asyncio                           # Asynchronous programming
import httpx                             # HTTP client for Ollama API

# On Windows PowerShell/CMD the console uses cp1252 encoding.
# Force UTF-8 output so any non-ASCII characters render correctly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Official MCP Python SDK:
# - ClientSession          : manages the MCP session (initialize, list_tools, call_tool)
# - StdioServerParameters  : parameters for launching the server as a child process
# - stdio_client           : context manager that starts the process and creates
#                            a (read_stream, write_stream) pair for ClientSession
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# =============================================================================
# CONFIGURATION
# =============================================================================

# Ollama API address. By default Ollama listens on port 11434.
OLLAMA_BASE_URL = "http://localhost:11434"

# Model to use.
# Specify the name exactly as shown by `ollama list`.
# Models with tool-calling support: llama3.1, mistral-nemo, qwen2.5, qwen3
OLLAMA_MODEL = "qwen3.6"

# Parameters for launching our MCP server.
# StdioServerParameters describes how to start the server process:
# command + args is equivalent to running: python server.py
SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["server.py"],
)


# =============================================================================
# OLLAMA API FUNCTIONS
# =============================================================================

def get_mcp_tools_for_ollama(tools: list) -> list[dict]:
    """
    Converts MCP tool objects into the format expected by the Ollama API.

    MCP returns Tool objects with fields: name, description, inputSchema.
    Ollama expects the OpenAI-compatible format: {"type": "function", "function": {...}}

    MCP format (inputSchema is JSON Schema of parameters):
      Tool(name="get_current_time", description="...", inputSchema={...})

    Ollama format:
      {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    ollama_tools = []
    for tool in tools:
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                # inputSchema in MCP == parameters in OpenAI/Ollama format
                "parameters": tool.inputSchema if tool.inputSchema else {
                    "type": "object",
                    "properties": {},
                },
            },
        })
    return ollama_tools


async def chat_with_ollama(
    client: httpx.AsyncClient,
    messages: list[dict],
    tools: list[dict],
) -> dict:
    """
    Sends a request to the Ollama Chat API and returns the model response.

    Ollama API is compatible with the OpenAI Chat Completions API.

    Request:
      POST http://localhost:11434/api/chat
      {
        "model": "llama3.1",
        "messages": [...],
        "tools": [...],   <-- pass available tools
        "stream": false
      }

    Model response (when the model wants to call a tool):
      {
        "message": {
          "role": "assistant",
          "content": "",
          "tool_calls": [
            {
              "function": {
                "name": "get_current_time",
                "arguments": {"timezone": "Europe/London"}
              }
            }
          ]
        }
      }
    """
    response = await client.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "tools": tools,
            "stream": False,  # Wait for the complete response, no streaming
        },
        timeout=300.0,  # 300-second timeout (AEM data is large; model needs time)
    )
    response.raise_for_status()
    return response.json()


# =============================================================================
# MAIN FUNCTION — MANUAL TOOL CALLING LOOP
# =============================================================================

async def check_ollama() -> None:
    """
    Verifies that Ollama is reachable and the required model is available
    BEFORE starting the MCP server.

    We check upfront because errors inside an anyio TaskGroup
    (created by stdio_client) are wrapped in ExceptionGroup and lose
    readability. It is much cleaner to exit with a clear message
    before the MCP session is even opened.
    """
    async with httpx.AsyncClient() as client:
        # Step A: check whether Ollama is running at all
        try:
            tags_resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        except httpx.ConnectError:
            raise SystemExit(
                "\n[Error] Ollama is not running or unreachable at "
                f"{OLLAMA_BASE_URL}\n\n"
                "What to do:\n"
                "  1. Download Ollama: https://ollama.com/download\n"
                "  2. Start the server: ollama serve\n"
                f"  3. Pull the model:   ollama pull {OLLAMA_MODEL}"
            )

        # Step B: check that the required model is downloaded
        available = [m["name"] for m in tags_resp.json().get("models", [])]
        # Ollama stores names as "llama3.1:latest", so we check by prefix
        model_found = any(m.startswith(OLLAMA_MODEL) for m in available)

        if not model_found:
            models_str = "\n  ".join(available) if available else "(no models downloaded)"
            raise SystemExit(
                f"\n[Error] Model '{OLLAMA_MODEL}' not found in Ollama.\n\n"
                f"Downloaded models:\n  {models_str}\n\n"
                f"Pull the required model:\n"
                f"  ollama pull {OLLAMA_MODEL}\n\n"
                "Alternatives with tool-calling support:\n"
                "  ollama pull mistral-nemo\n"
                "  ollama pull qwen2.5\n"
                "  ollama pull llama3.2"
            )

    print(f"[Ollama] Model '{OLLAMA_MODEL}' is available. Continuing...\n")


async def main():
    """
    Demonstrates the complete Manual Tool Calling cycle:
      1. Check Ollama availability
      2. Connect to the MCP server via the official ClientSession
      3. Retrieve its list of tools
      4. Send a request to Ollama with the tools
      5. Intercept the tool_call and execute it via MCP
      6. Return the result to Ollama
      7. Receive the final response
    """
    # ------------------------------------------------------------------
    # STEP 0: Check Ollama BEFORE entering the MCP context
    # ------------------------------------------------------------------
    # Important: the check runs OUTSIDE the stdio_client block so that
    # any error is not wrapped by anyio into an ExceptionGroup.
    await check_ollama()

    # ------------------------------------------------------------------
    # STEP 1: Start the MCP server and open a session
    # ------------------------------------------------------------------
    # stdio_client(SERVER_PARAMS) does the following:
    #   - Launches `python server.py` as a child process
    #   - Creates a pair of async streams: read_stream and write_stream
    #   - Manages the process lifecycle (start and teardown)
    #
    # ClientSession(read, write) does the following:
    #   - Accepts the streams from stdio_client
    #   - Implements the MCP protocol: initialize, list tools, call tools
    #   - Uses anyio internally for async I/O
    print("[MCP] Starting MCP server...")

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:

            # MCP handshake.
            # initialize() sends {"method": "initialize", ...}
            # and receives the server's capabilities in response.
            # Without this step, all subsequent requests will be rejected.
            await session.initialize()
            print("[MCP] Server is ready.\n")

            # ------------------------------------------------------------------
            # STEP 2: Retrieve the list of tools from the MCP server
            # ------------------------------------------------------------------
            # list_tools() sends {"method": "tools/list"} and returns
            # a ListToolsResult object with a .tools field — a list of Tool objects.
            tools_result = await session.list_tools()
            mcp_tools = tools_result.tools

            print(f"[MCP] Available tools: {[t.name for t in mcp_tools]}")

            # Convert MCP Tool objects to Ollama format
            ollama_tools = get_mcp_tools_for_ollama(mcp_tools)

            # ------------------------------------------------------------------
            # STEP 3: Send the user question to Ollama
            # ------------------------------------------------------------------
            # The AEM page with MCP principles, deployed from our project.
            # The .infinity.json suffix is a built-in Sling suffix that returns
            # the full JCR node tree without additional configuration.
            # Alternatives: ._jcr_content.infinity.json, .1.json (one level only)
            AEM_PAGE_URL = "http://localhost:4502/content/hvozdzeu/en/mcp-principles.infinity.json"

            user_question = (
                "Analyze the AEM page at: " + AEM_PAGE_URL + ". "
                "First, show the component structure, then read the page content "
                "and give a brief summary of what the page is about."
            )
            print(f"\n[User] {user_question}")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AEM (Adobe Experience Manager) expert. "
                        "You have tools to analyze AEM pages through their JSON API. "
                        "Use analyze_page_components to inspect the component structure, "
                        "and get_page_content to read the text content. "
                        "Always use both tools, then provide a structured summary."
                    ),
                },
                {
                    "role": "user",
                    "content": user_question,
                },
            ]

            async with httpx.AsyncClient() as http_client:

                # First Ollama request — we expect the model to request a tool call
                print("\n[Ollama] Sending request with tools...")
                response_data = await chat_with_ollama(http_client, messages, ollama_tools)
                assistant_message = response_data["message"]

                # ------------------------------------------------------------------
                # STEP 4: INTERCEPT THE TOOL CALL REQUEST
                # ------------------------------------------------------------------
                # If the model wants to call a tool, the response will include tool_calls.
                # Example model response:
                # {
                #   "role": "assistant",
                #   "content": "",
                #   "tool_calls": [
                #     {"function": {"name": "get_current_time", "arguments": {"timezone": "Europe/London"}}},
                #     {"function": {"name": "get_current_time", "arguments": {"timezone": "America/New_York"}}}
                #   ]
                # }
                tool_calls = assistant_message.get("tool_calls", [])

                if tool_calls:
                    print(f"\n[Intercept] Model requested {len(tool_calls)} tool call(s):")

                    # Append the assistant message with tool_calls to the conversation.
                    # Important: the model must see its own previous response in history.
                    messages.append(assistant_message)

                    # Execute each requested tool
                    for tool_call in tool_calls:
                        func = tool_call["function"]
                        tool_name = func["name"]

                        # Arguments may be a JSON string or already a dict —
                        # different Ollama versions return different formats.
                        raw_args = func.get("arguments", {})
                        if isinstance(raw_args, str):
                            tool_args = json.loads(raw_args)
                        else:
                            tool_args = raw_args

                        print(f"  → Tool:      {tool_name}")
                        print(f"  → Arguments: {json.dumps(tool_args, ensure_ascii=False)}")

                        # ----------------------------------------------------------
                        # STEP 4.1: CALL THE MCP SERVER
                        # ----------------------------------------------------------
                        # session.call_tool() sends a JSON-RPC request:
                        # {"method": "tools/call", "params": {"name": "...", "arguments": {...}}}
                        # and returns a CallToolResult object with a .content field
                        call_result = await session.call_tool(tool_name, tool_args)

                        # Extract text from the first content block in the response.
                        # MCP returns a list of blocks: [TextContent(type="text", text="...")]
                        tool_result_text = ""
                        if call_result.content:
                            first_block = call_result.content[0]
                            tool_result_text = getattr(first_block, "text", str(first_block))

                        print(f"  ← Result:    {tool_result_text}")

                        # Append the tool result to the conversation history.
                        # Ollama (like the OpenAI API) expects a message with role="tool".
                        # The model will see this result in the next request.
                        messages.append({
                            "role": "tool",
                            "content": tool_result_text,
                        })

                    # ------------------------------------------------------------------
                    # STEP 5: Send tool results back to Ollama
                    # ------------------------------------------------------------------
                    # messages now contains: system + user + assistant(tool_calls) + tool + tool
                    # The model will generate a final text answer based on these results.
                    print("\n[Ollama] Sending tool results, waiting for final response...")
                    final_response = await chat_with_ollama(http_client, messages, ollama_tools)
                    final_answer = final_response["message"]["content"]

                else:
                    # Model answered directly, without calling any tools.
                    # This can happen if the model decided a tool wasn't needed,
                    # or if the model does not support tool calling.
                    print("\n[Warning] Model did not call any tools. Direct response:")
                    final_answer = assistant_message.get("content", "")

                # ------------------------------------------------------------------
                # STEP 6: Final answer
                # ------------------------------------------------------------------
                print(f"\n[Assistant] {final_answer}")

    # After exiting the `async with` blocks the server is automatically stopped.
    print("\n[MCP] Server stopped.")


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    asyncio.run(main())
