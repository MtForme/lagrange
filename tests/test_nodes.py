"""Tests for the node interface contract (lagrange/nodes/base_node.py).

Real semantic/crypto/temporal node logic isn't implemented yet — this
file only pins down the abstract contract every node must satisfy, using
the MockNode test double from conftest.py.
"""

from __future__ import annotations

import pytest

from lagrange.memory.schema import Memory, NodeVote
from lagrange.nodes.base_node import BaseNode


def test_base_node_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseNode()


def test_mock_node_returns_well_formed_vote(make_mock_node):
    node = make_mock_node("semantic", True, 0.75, "looks fine")
    memory = Memory(id="1", content="hello", source="verified_user", timestamp=0.0)

    result = node.evaluate(memory, context={})

    assert isinstance(result, NodeVote)
    assert result.node_id == "semantic"
    assert result.verdict is True
    assert result.confidence == 0.75


def test_node_vote_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        NodeVote(node_id="semantic", verdict=True, confidence=1.5, reason="bad")


def test_memory_rejects_unknown_source():
    with pytest.raises(ValueError):
        Memory(id="1", content="x", source="not_a_real_source", timestamp=0.0)
