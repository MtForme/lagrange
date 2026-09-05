"""Abstract base class for all Byzantine consensus nodes.

Design rule (see CLAUDE.md): nodes must never communicate with each other
or share mutable state. Each node only ever sees the `Memory` proposal and
a read-only `context` dict handed to it by the coordinator. All
coordination happens in `lagrange/coordinator.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lagrange.memory.schema import Memory, NodeVote


class BaseNode(ABC):
    """Common interface every verification strategy must implement."""

    #: short identifier used in NodeVote.node_id and in alerts/logs
    node_id: str = "base"

    @abstractmethod
    def evaluate(self, memory: Memory, context: dict[str, Any]) -> NodeVote:
        """Independently evaluate a proposed memory write.

        Args:
            memory: the proposed Memory, not yet accepted/scored.
            context: read-only side information the coordinator supplies
                (e.g. existing memories for similarity checks, the origin
                of the write call). Nodes must not mutate it.

        Returns:
            A NodeVote with this node's verdict, confidence, and reason.
        """
        raise NotImplementedError
