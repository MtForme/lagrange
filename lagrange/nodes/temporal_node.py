"""Node C — Temporal Pattern Analysis.

Analyzes *when* a memory arrives and *from what context*, independent of
its claimed source (that's Node B's job) or its semantic content versus
existing memories (that's Node A's job). Two concerns, per CLAUDE.md:

1. Indirect injection vectors: a memory that arrives embedded in an
   email, a web page, a README/document, or raw tool output is exactly
   the delivery mechanism used by indirect prompt injection and MINJA-
   style attacks — the agent never had a direct, attributable
   interaction with whoever actually wrote the content. These are
   always flagged; content that additionally reads as an imperative
   instruction ("ignore previous instructions", "from now on always...")
   is flagged with higher confidence, since that phrasing is the
   textbook payload shape for hijacking an agent's future behavior.

2. Unusual timing patterns: a burst of writes from the same source in a
   short window looks more like an automated/scripted attack than normal
   interactive use.

This node keeps its own internal history to detect bursts. That state is
private to this node — it is never shared with the other nodes or the
coordinator, per CLAUDE.md's "nodes must not share state" rule.
"""

from __future__ import annotations

from typing import Any

from lagrange.memory.schema import Memory, NodeVote
from lagrange.nodes.base_node import BaseNode

INDIRECT_ORIGINS = frozenset({"email", "webpage", "readme", "document", "tool_output"})
TRUSTED_ORIGINS = frozenset({"direct_chat", "internal_bootstrap"})

# Heuristic phrases characteristic of prompt-injection-style payloads
# trying to hijack future agent behavior. Not exhaustive — this is one
# signal among three nodes, not the sole line of defense.
INSTRUCTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "disregard all previous",
    "from now on",
    "new instruction",
    "override",
    "you must always",
    "always approve",
    "as an ai you should",
)


class TemporalNode(BaseNode):
    node_id = "temporal"

    def __init__(self, burst_window_seconds: float = 5.0, burst_threshold: int = 5) -> None:
        self.burst_window_seconds = burst_window_seconds
        self.burst_threshold = burst_threshold
        self._recent_writes: dict[str, list[float]] = {}

    def evaluate(self, memory: Memory, context: dict[str, Any]) -> NodeVote:
        origin = context.get("origin", "direct_chat")

        if origin in INDIRECT_ORIGINS:
            if self._looks_like_instruction(memory.content):
                return NodeVote(
                    self.node_id,
                    False,
                    0.9,
                    f"indirect injection vector ({origin}) carrying instruction-shaped content",
                )
            return NodeVote(
                self.node_id,
                False,
                0.55,
                f"indirect injection vector ({origin}) — flagged per threat model even without instruction phrasing",
            )

        is_burst, burst_reason = self._check_burst(memory.source, memory.timestamp)
        if is_burst:
            return NodeVote(self.node_id, False, 0.7, burst_reason)

        confidence = 0.85 if origin in TRUSTED_ORIGINS else 0.6
        return NodeVote(self.node_id, True, confidence, f"origin={origin} within normal temporal pattern")

    def _check_burst(self, source: str, timestamp: float) -> tuple[bool, str]:
        history = self._recent_writes.setdefault(source, [])
        history.append(timestamp)
        window_start = timestamp - self.burst_window_seconds
        recent = [t for t in history if t >= window_start]
        self._recent_writes[source] = recent
        if len(recent) > self.burst_threshold:
            return True, (
                f"{len(recent)} writes from {source!r} within {self.burst_window_seconds}s "
                "— unusual burst pattern"
            )
        return False, ""

    @staticmethod
    def _looks_like_instruction(content: str) -> bool:
        lowered = content.lower()
        return any(marker in lowered for marker in INSTRUCTION_MARKERS)
