"""Shared fixtures: simple mock nodes for exercising consensus/coordinator
logic before the real semantic/crypto/temporal nodes exist.
"""

from __future__ import annotations

from typing import Any

import pytest

from lagrange.memory.schema import Memory, NodeVote
from lagrange.nodes.base_node import BaseNode


class MockNode(BaseNode):
    """A node whose verdict is fixed at construction time."""

    def __init__(self, node_id: str, verdict: bool, confidence: float = 0.9, reason: str = "mock"):
        self.node_id = node_id
        self._verdict = verdict
        self._confidence = confidence
        self._reason = reason

    def evaluate(self, memory: Memory, context: dict[str, Any]) -> NodeVote:
        return NodeVote(
            node_id=self.node_id,
            verdict=self._verdict,
            confidence=self._confidence,
            reason=self._reason,
        )


class ExplodingNode(BaseNode):
    """A node that always raises, to test the coordinator's fail-safe path."""

    node_id = "exploding"

    def evaluate(self, memory: Memory, context: dict[str, Any]) -> NodeVote:
        raise RuntimeError("simulated node failure")


@pytest.fixture
def make_mock_node():
    return MockNode


@pytest.fixture
def three_accepting_nodes():
    return [
        MockNode("semantic", True, 0.9, "consistent"),
        MockNode("crypto", True, 0.95, "signature valid"),
        MockNode("temporal", True, 0.8, "normal timing"),
    ]


@pytest.fixture
def exploding_node():
    return ExplodingNode()


@pytest.fixture
def three_rejecting_nodes():
    return [
        MockNode("semantic", False, 0.9, "contradicts known facts"),
        MockNode("crypto", False, 0.95, "signature missing"),
        MockNode("temporal", False, 0.8, "injected via document"),
    ]
