"""Tests for the simplified PBFT consensus logic (lagrange/consensus/pbft.py).

These exercise the safety property in isolation, with no coordinator or
nodes involved: given a set of votes, does reach_consensus() make the
correct, fail-safe accept/quarantine decision?

Reject-vote confidence matters here in a way accept-vote confidence
doesn't: a reject at or above VETO_CONFIDENCE (0.85) blocks acceptance
outright (see pbft.py's veto rule docstring), so tests that aren't
specifically about the veto keep dissenting confidence below it.
"""

from __future__ import annotations

import pytest

from lagrange.consensus.pbft import VETO_CONFIDENCE, reach_consensus
from lagrange.memory.schema import NodeVote


def vote(node_id: str, verdict: bool, confidence: float = 0.6, reason: str = "r") -> NodeVote:
    return NodeVote(node_id=node_id, verdict=verdict, confidence=confidence, reason=reason)


def test_unanimous_accept():
    votes = [vote("a", True, 0.9), vote("b", True, 0.9), vote("c", True, 0.9)]
    result = reach_consensus(votes)
    assert result.accepted is True
    assert result.confidence_score == pytest.approx(0.9)


def test_two_of_three_accept_reaches_consensus():
    # dissent below veto confidence: plain 2/3 majority applies
    votes = [vote("a", True, 0.9), vote("b", True, 0.9), vote("c", False, 0.6)]
    result = reach_consensus(votes)
    assert result.accepted is True


def test_one_of_three_accept_is_quarantined():
    votes = [vote("a", True), vote("b", False), vote("c", False)]
    result = reach_consensus(votes)
    assert result.accepted is False


def test_unanimous_reject():
    votes = [vote("a", False, 0.9), vote("b", False, 0.9), vote("c", False, 0.9)]
    result = reach_consensus(votes)
    assert result.accepted is False
    assert result.confidence_score == pytest.approx(0.9)


def test_no_votes_fails_safe_to_quarantine():
    result = reach_consensus([])
    assert result.accepted is False
    assert result.confidence_score == 0.0
    assert "quarantined" in result.reason


def test_low_confidence_dissent_barely_dents_an_accept():
    # a low-confidence reject barely moves the needle on an otherwise
    # confident accept, and doesn't come close to vetoing it
    votes = [vote("a", True, 1.0), vote("b", True, 1.0), vote("c", False, 0.1)]
    result = reach_consensus(votes)
    assert result.accepted is True
    assert result.confidence_score == pytest.approx(0.9667, abs=1e-4)


def test_moderate_confidence_dissent_lowers_confidence_without_vetoing():
    # below VETO_CONFIDENCE: outvoted 2-1, but the dissent must still be
    # visible in confidence_score rather than silently discarded by the
    # majority (this is what lets "accepted but flagged" surface at read
    # time, per CLAUDE.md's read flow)
    votes = [vote("semantic", True, 0.9), vote("crypto", True, 0.9), vote("temporal", False, 0.6)]
    result = reach_consensus(votes)
    assert result.accepted is True
    unanimous_result = reach_consensus([vote("semantic", True, 0.9), vote("crypto", True, 0.9), vote("temporal", True, 0.9)])
    assert result.confidence_score < unanimous_result.confidence_score


def test_high_confidence_dissent_vetoes_acceptance_even_when_outvoted_2_to_1():
    # Node C (or any specialist) flagging something with high confidence
    # must not be overrulable just because the other two nodes — which
    # check unrelated properties and have no opinion on this one — vote
    # accept. Heterogeneous nodes mean a lone dissenter is often the only
    # node equipped to notice a given attack at all.
    votes = [vote("semantic", True, 0.9), vote("crypto", True, 0.9), vote("temporal", False, 0.95)]
    result = reach_consensus(votes)
    assert result.accepted is False
    assert "VETOED" in result.reason
    assert "temporal" in result.reason


def test_veto_threshold_is_exact():
    just_below = reach_consensus([vote("a", True, 0.9), vote("b", True, 0.9), vote("c", False, VETO_CONFIDENCE - 0.01)])
    at_threshold = reach_consensus([vote("a", True, 0.9), vote("b", True, 0.9), vote("c", False, VETO_CONFIDENCE)])
    assert just_below.accepted is True
    assert at_threshold.accepted is False


def test_reason_string_includes_every_node():
    votes = [vote("semantic", True), vote("crypto", False), vote("temporal", True)]
    result = reach_consensus(votes)
    for node_id in ("semantic", "crypto", "temporal"):
        assert node_id in result.reason


@pytest.mark.parametrize("threshold", [0.5, 0.9, 1.0])
def test_custom_threshold(threshold):
    # dissent kept below veto confidence so only `threshold` is under test
    votes = [vote("a", True, 0.9), vote("b", True, 0.9), vote("c", False, 0.5)]
    result = reach_consensus(votes, threshold=threshold)
    assert result.accepted == (2 / 3 >= threshold - 1e-9)
