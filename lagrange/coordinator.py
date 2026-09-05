"""Coordinator — single entry point orchestrating consensus across nodes.

Broadcasts every proposed memory write to all nodes, runs the simplified
PBFT consensus, and either commits the memory to the store or quarantines
it with an alert. Nodes never talk to each other or to the store directly
— everything routes through here.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from lagrange.consensus.pbft import reach_consensus
from lagrange.memory.schema import Memory
from lagrange.nodes.base_node import BaseNode

MIN_NODES = 3
ESCALATION_THRESHOLD = 3  # rejections from the same source before escalating


class Coordinator:
    """Orchestrates the write/read flow described in CLAUDE.md."""

    def __init__(
        self,
        nodes: list[BaseNode],
        store: Any | None = None,
        alert_log_path: str | Path = "lagrange_alerts.jsonl",
    ) -> None:
        if len(nodes) < MIN_NODES:
            raise ValueError(f"Lagrange requires at least {MIN_NODES} independent nodes for BFT")
        self.nodes = nodes
        self.store = store
        self.alert_log_path = Path(alert_log_path)
        self._rejection_counts: dict[str, int] = {}

    # -- write path ---------------------------------------------------

    def write_memory(self, content: str, source: str, context: dict[str, Any] | None = None) -> Memory:
        """Propose a memory write; accepted only on 2/3 node consensus.

        Fail-safe: any exception raised by a node during evaluation is
        treated as a rejection vote from that node rather than crashing
        the whole write, since we'd rather quarantine than lose a memory
        write to an unrelated bug in a single node.
        """
        context = dict(context or {})
        memory = Memory(
            id=str(uuid.uuid4()),
            content=content,
            source=source,
            timestamp=time.time(),
        )

        votes = [self._safe_evaluate(node, memory, context) for node in self.nodes]
        result = reach_consensus(votes)

        memory.node_votes = result.votes
        memory.confidence_score = result.confidence_score
        memory.accepted = result.accepted

        if result.accepted:
            if self.store is not None:
                self.store.add(memory)
        else:
            self._quarantine(memory, result.reason)

        return memory

    def _safe_evaluate(self, node: BaseNode, memory: Memory, context: dict[str, Any]):
        from lagrange.memory.schema import NodeVote

        try:
            return node.evaluate(memory, context)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            return NodeVote(
                node_id=getattr(node, "node_id", "unknown"),
                verdict=False,
                confidence=1.0,
                reason=f"node raised {exc.__class__.__name__}: {exc}",
            )

    # -- read path ------------------------------------------------------

    def read_memory(self, query: str, top_k: int = 5) -> list[Memory]:
        """Return the top-k semantically similar accepted memories."""
        if self.store is None:
            return []
        return self.store.query(query, top_k=top_k)

    # -- quarantine / alerting ------------------------------------------

    def _quarantine(self, memory: Memory, reason: str) -> None:
        self._rejection_counts[memory.source] = self._rejection_counts.get(memory.source, 0) + 1
        self._log_alert(memory, reason)

    def _log_alert(self, memory: Memory, reason: str) -> None:
        count = self._rejection_counts.get(memory.source, 0)
        record = {
            "id": memory.id,
            "source": memory.source,
            "timestamp": memory.timestamp,
            "reason": reason,
            "rejection_count_for_source": count,
            "escalation": count >= ESCALATION_THRESHOLD,
        }
        with self.alert_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
