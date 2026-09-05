"""Tests for the simplified PBFT consensus logic (lagrange/consensus/pbft.py).

These exercise the safety property in isolation, with no coordinator or
nodes involved: given a set of votes, does reach_consensus() make the
correct, fail-safe accept/quarantine decision?
"""

from __future__ import annotations

import pytest

from lagrange.consensus.pbft import reach_consensus
from lagrange.memory.schema import NodeVote


def vote(node_id: str, verdict: bool, confidence: float = 0.9, reason: str = "r") -> NodeVote:
    return NodeVote(node_id=node_id, verdict=verdict, confidence=confidence, reason=reason)


def test_unanimous_accept():
    votes = [vote("a", True), vote("b", True), vote("c", True)]
    result = reach_consensus(votes)
    assert result.accepted is True
    assert result.confidence_score == pytest.approx(0.9)


def test_two_of_three_accept_reaches_consensus():
    votes = [vote("a", True), vote("b", True), vote("c", False)]
    result = reach_consensus(votes)
    assert result.accepted is True


def test_one_of_three_accept_is_quarantined():
    votes = [vote("a", True), vote("b", False), vote("c", False)]
    result = reach_consensus(votes)
    assert result.accepted is False


def test_unanimous_reject():
    votes = [vote("a", False), vote("b", False), vote("c", False)]
    result = reach_consensus(votes)
    assert result.accepted is False
    assert result.confidence_score == pytest.approx(0.9)


def test_no_votes_fails_safe_to_quarantine():
    result = reach_consensus([])
    assert result.accepted is False
    assert result.confidence_score == 0.0
    assert "quarantined" in result.reason


def test_confidence_score_reflects_deciding_side_only():
    # two confident accepts should not be dragged down by one unconfident reject
    votes = [vote("a", True, 1.0), vote("b", True, 1.0), vote("c", False, 0.1)]
    result = reach_consensus(votes)
    assert result.accepted is True
    assert result.confidence_score == pytest.approx(1.0)


def test_reason_string_includes_every_node():
    votes = [vote("semantic", True), vote("crypto", False), vote("temporal", True)]
    result = reach_consensus(votes)
    for node_id in ("semantic", "crypto", "temporal"):
        assert node_id in result.reason


@pytest.mark.parametrize("threshold", [0.5, 0.9, 1.0])
def test_custom_threshold(threshold):
    votes = [vote("a", True), vote("b", True), vote("c", False)]
    result = reach_consensus(votes, threshold=threshold)
    assert result.accepted == (2 / 3 >= threshold - 1e-9)
