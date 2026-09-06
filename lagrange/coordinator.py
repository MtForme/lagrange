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
from lagrange.crypto.signer import Signer
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
        signer: Signer | None = None,
    ) -> None:
        if len(nodes) < MIN_NODES:
            raise ValueError(f"Lagrange requires at least {MIN_NODES} independent nodes for BFT")
        self.nodes = nodes
        self.store = store
        self.alert_log_path = Path(alert_log_path)
        # Note: if a CryptoNode is among `nodes`, it must be constructed
        # with this same Signer (or one sharing its keypair) — otherwise
        # it can never verify signatures produced by write_internal_fact.
        self.signer = signer or Signer()
        self._rejection_counts: dict[str, int] = {}

    # -- write path ---------------------------------------------------

    def write_memory(
        self,
        content: str,
        source: str,
        context: dict[str, Any] | None = None,
        signature: str = "",
    ) -> Memory:
        """Propose a memory write; accepted only on 2/3 node consensus.

        `signature` is only meaningful for source="internal_system" and
        must come from a Signer sharing this coordinator's keypair (see
        write_internal_fact). Untrusted, agent-facing callers should
        never be able to supply one — that capability is what lets Node B
        catch an attacker tricking an agent into mislabeling injected
        content as internal_system.

        Fail-safe: any exception raised by a node during evaluation is
        treated as a rejection vote from that node rather than crashing
        the whole write, since we'd rather quarantine than lose a memory
        write to an unrelated bug in a single node.
        """
        return self._propose(content, source, time.time(), context, signature)

    def write_internal_fact(self, content: str, context: dict[str, Any] | None = None) -> Memory:
        """Write a genuinely internal_system memory, signed with this
        coordinator's own key.

        This is the ONLY legitimate way to produce a validly-signed
        internal_system memory. It must only be reachable from trusted
        Lagrange-internal code (e.g. bootstrapping seed facts) — never
        exposed through an agent-facing tool/MCP surface, since anything
        reachable by the agent is reachable by prompt injection.
        """
        timestamp = time.time()
        signature = self.signer.sign(content, "internal_system", timestamp)
        return self._propose(content, "internal_system", timestamp, context, signature)

    def _propose(
        self,
        content: str,
        source: str,
        timestamp: float,
        context: dict[str, Any] | None,
        signature: str,
    ) -> Memory:
        """Shared write path: broadcast to nodes, apply consensus, commit or quarantine."""
        context = dict(context or {})
        memory = Memory(id=str(uuid.uuid4()), content=content, source=source, timestamp=timestamp, signature=signature)

        # Embed the new content once, here, and share it with both the
        # store and the nodes via `memory.embedding` / context, so the
        # semantic node never has to re-embed it (and neither does
        # store.add). Only possible when the store exposes its embedder.
        store_embedder = getattr(self.store, "embedder", None)
        if store_embedder is not None and not memory.embedding:
            memory.embedding = list(store_embedder(content))
            context.setdefault("query_embedding", memory.embedding)

        # Give every node equal, read-only access to existing memories for
        # similarity checks (SemanticNode's job), without letting nodes
        # touch the store directly. This is coordinator-provided context,
        # not node-to-node communication. The store returns each candidate
        # with its stored embedding, so the semantic node reuses those too.
        if self.store is not None and "similar_memories" not in context:
            context["similar_memories"] = self.store.query(content, top_k=5)

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
