"""MCP server exposing Lagrange's write_memory / read_memory as tools.

This is the ONLY agent-facing surface into Lagrange, and two things are
deliberately enforced here on top of whatever the nodes decide:

1. `source` is restricted to {"verified_user", "external_unverified"} —
   an agent (and therefore anything that manages to inject text into
   what the agent sends) can never claim source="internal_system"
   through this tool. That claim is only ever legitimate via
   Coordinator.write_internal_fact, called from trusted, non-agent-
   facing code — never wired into this server. This is defense-in-depth
   alongside CryptoNode's own signature check, not a replacement for it.
2. Every response surfaces accepted / confidence_score / source
   explicitly, so the calling agent (and the human behind it) can see
   when something was quarantined or accepted with low confidence,
   rather than that information being silently swallowed at read time.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from lagrange.config import LagrangeConfig, build_coordinator
from lagrange.coordinator import Coordinator
from lagrange.memory.schema import Memory

ALLOWED_AGENT_SOURCES = ("verified_user", "external_unverified")
LOW_CONFIDENCE_THRESHOLD = 0.6

mcp = FastMCP("lagrange")

_coordinator: Coordinator | None = None


def _get_coordinator() -> Coordinator:
    """Build the real three-node system once, lazily — importing this
    module (e.g. to run tests against the tool functions) must never by
    itself touch disk or do any work.

    Configuration comes from `LAGRANGE_*` environment variables (see
    lagrange/config.py and the README): at minimum the signing key is
    loaded from LAGRANGE_KEY_PATH (created on first run) so internal_system
    signatures keep verifying across restarts, and the store persists to
    LAGRANGE_DB_PATH.
    """
    global _coordinator
    if _coordinator is None:
        _coordinator = build_coordinator(LagrangeConfig.from_env())
    return _coordinator


def _memory_to_dict(memory: Memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "content": memory.content,
        "source": memory.source,
        "accepted": memory.accepted,
        "confidence_score": memory.confidence_score,
        "low_confidence": memory.confidence_score < LOW_CONFIDENCE_THRESHOLD,
        "votes": [
            {"node": vote.node_id, "verdict": vote.verdict, "confidence": vote.confidence, "reason": vote.reason}
            for vote in memory.node_votes
        ],
    }


@mcp.tool()
def write_memory(content: str, source: str = "external_unverified", origin: str = "direct_chat") -> dict[str, Any]:
    """Propose writing `content` to Lagrange's Byzantine-consensus-protected memory.

    source: "verified_user" for content directly and verifiably from the
    authenticated user in this conversation, or "external_unverified"
    (the default) for anything else — a document, webpage, email, tool
    output, or content you're otherwise not certain originated with the
    user. This tool can never write source="internal_system"; only
    trusted, non-agent-facing code can do that.

    origin: where the content came from — "direct_chat" (default),
    "email", "webpage", "readme", "document", or "tool_output". Used by
    the temporal node to detect indirect injection vectors.

    The memory is only actually stored if the nodes reach consensus on
    its provenance; otherwise it's quarantined, and this call still
    returns normally with accepted=False so you can see what happened.
    """
    if source not in ALLOWED_AGENT_SOURCES:
        raise ValueError(
            f"source must be one of {ALLOWED_AGENT_SOURCES}; internal_system memories can only be "
            "written by trusted internal code, never through this tool"
        )
    memory = _get_coordinator().write_memory(content, source=source, context={"origin": origin})
    return _memory_to_dict(memory)


@mcp.tool()
def read_memory(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Retrieve up to `top_k` memories most relevant to `query`.

    Each result includes its source and confidence_score, with
    low_confidence=True flagged explicitly for anything below
    LOW_CONFIDENCE_THRESHOLD — per CLAUDE.md's read flow, low-confidence
    memories should be surfaced to the caller, not silently trusted the
    same as everything else.
    """
    memories = _get_coordinator().read_memory(query, top_k=top_k)
    return [_memory_to_dict(memory) for memory in memories]


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
