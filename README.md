# Lagrange

Byzantine Memory Consensus for Agentic AI — a lightweight middleware layer
that protects the persistent memory of AI agents from poisoning attacks
(MINJA, EchoLeak, Sleeper Agents) using a three-node Byzantine Fault
Tolerant consensus system.

Every memory write is validated by three independent nodes with different
verification strategies (semantic consistency, cryptographic provenance,
temporal pattern analysis) before it is accepted into the vector store.
A memory is accepted only if at least 2/3 of the nodes agree.

See [CLAUDE.md](./CLAUDE.md) for the full design, threat model, and
development priorities.

## Status

Core consensus, the coordinator, all three real nodes (semantic,
cryptographic, temporal), the ChromaDB-backed store, an MCP server
exposing `write_memory` / `read_memory`, and runnable examples
(`examples/basic_usage.py`, `examples/agent_integration.py`) are all
implemented and tested, including an end-to-end red-team suite
(`tests/test_attacks.py`). See that file's docstring for one
intentionally-documented, not-yet-closed gap (policy injection via
trusted direct chat).

## Setup

```powershell
py -3.11 -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
```

## Testing

```powershell
./.venv/Scripts/python -m pytest tests/ -v
```

## Using with Claude Desktop / Claude Code

Add to your MCP server config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "lagrange": {
      "command": "C:/path/to/Lagrange/.venv/Scripts/python.exe",
      "args": ["-m", "lagrange.mcp_server"]
    }
  }
}
```

This exposes `write_memory(content, source, origin)` and
`read_memory(query, top_k)` as tools. The agent can never write
`source="internal_system"` through this server — see
`lagrange/mcp_server.py`'s docstring for why that matters.
