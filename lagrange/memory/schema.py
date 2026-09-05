"""Core data schema shared by every node, the coordinator, and the store.

Kept dependency-free (stdlib only) so nodes can import it without pulling
in ChromaDB, sentence-transformers, or cryptography.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_SOURCES = ("verified_user", "internal_system", "external_unverified")


@dataclass
class NodeVote:
    """A single node's independent verdict on a proposed memory write."""

    node_id: str  # "semantic" | "crypto" | "temporal"
    verdict: bool  # True = accept, False = reject
    confidence: float  # node's confidence in its own verdict, 0.0-1.0
    reason: str  # human-readable explanation, surfaced in alerts/logs

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


@dataclass
class Memory:
    """A memory entry, before or after consensus.

    `accepted`, `confidence_score`, and `node_votes` are unset (falsy) at
    proposal time and are filled in by the coordinator once consensus has
    been reached — never by a node directly.
    """

    id: str
    content: str
    source: str  # "verified_user" | "internal_system" | "external_unverified"
    timestamp: float
    embedding: list[float] = field(default_factory=list)
    signature: str = ""
    confidence_score: float = 0.0
    accepted: bool = False
    node_votes: list[NodeVote] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}, got {self.source!r}")
