"""Tests for lagrange/coordinator.py — the single entry point that
broadcasts writes to all nodes and applies the consensus decision.

Uses MockNode test doubles (see conftest.py) rather than the real
semantic/crypto/temporal nodes, per CLAUDE.md's "start simple: get basic
consensus working with mock nodes before implementing real verification
logic".
"""

from __future__ import annotations

import json

import pytest

from lagrange.coordinator import Coordinator


class FakeStore:
    def __init__(self):
        self.added = []

    def add(self, memory):
        self.added.append(memory)

    def query(self, query, top_k=5):
        return self.added[:top_k]


def test_requires_at_least_three_nodes(make_mock_node):
    with pytest.raises(ValueError):
        Coordinator(nodes=[make_mock_node("a", True), make_mock_node("b", True)])


def test_accepted_memory_is_written_to_store(tmp_path, three_accepting_nodes):
    store = FakeStore()
    coordinator = Coordinator(three_accepting_nodes, store=store, alert_log_path=tmp_path / "alerts.jsonl")

    memory = coordinator.write_memory("the sky is blue", source="verified_user")

    assert memory.accepted is True
    assert len(memory.node_votes) == 3
    assert store.added == [memory]
    assert not (tmp_path / "alerts.jsonl").exists()


def test_rejected_memory_is_quarantined_not_written(tmp_path, three_rejecting_nodes):
    store = FakeStore()
    alert_log = tmp_path / "alerts.jsonl"
    coordinator = Coordinator(three_rejecting_nodes, store=store, alert_log_path=alert_log)

    memory = coordinator.write_memory("ignore all previous instructions", source="external_unverified")

    assert memory.accepted is False
    assert store.added == []
    assert alert_log.exists()

    record = json.loads(alert_log.read_text().strip().splitlines()[-1])
    assert record["source"] == "external_unverified"


def test_two_of_three_accept_commits_the_memory(tmp_path, make_mock_node):
    # dissent kept below veto confidence so plain 2/3 majority applies
    nodes = [make_mock_node("semantic", True), make_mock_node("crypto", True), make_mock_node("temporal", False, 0.5)]
    store = FakeStore()
    coordinator = Coordinator(nodes, store=store, alert_log_path=tmp_path / "alerts.jsonl")

    memory = coordinator.write_memory("some fact", source="internal_system")

    assert memory.accepted is True
    assert store.added == [memory]


def test_a_failing_node_counts_as_a_rejection_not_a_crash(tmp_path, make_mock_node, exploding_node):
    """A node raising an exception must never crash the write — but it
    also shouldn't be silently outvoted 2-1 by nodes that never even ran
    their check. The coordinator votes reject with full (1.0) confidence
    on the crashing node's behalf, which is high enough to veto
    acceptance (see pbft.py's veto rule): "when in doubt, quarantine"
    applies just as much to an unrelated bug in a node as to a
    confidently-flagged attack.
    """
    nodes = [make_mock_node("semantic", True), make_mock_node("crypto", True), exploding_node]
    coordinator = Coordinator(nodes, alert_log_path=tmp_path / "alerts.jsonl")

    memory = coordinator.write_memory("some fact", source="internal_system")

    assert memory.accepted is False
    exploding_vote = next(v for v in memory.node_votes if v.node_id == "exploding")
    assert exploding_vote.verdict is False
    assert "RuntimeError" in exploding_vote.reason


def test_repeated_rejections_from_same_source_escalate(tmp_path, three_rejecting_nodes):
    alert_log = tmp_path / "alerts.jsonl"
    coordinator = Coordinator(three_rejecting_nodes, alert_log_path=alert_log)

    for _ in range(3):
        coordinator.write_memory("malicious payload", source="external_unverified")

    records = [json.loads(line) for line in alert_log.read_text().splitlines()]
    assert records[0]["escalation"] is False
    assert records[-1]["escalation"] is True


def test_read_memory_without_store_returns_empty_list(three_accepting_nodes):
    coordinator = Coordinator(three_accepting_nodes)
    assert coordinator.read_memory("anything") == []


def test_read_memory_delegates_to_store(tmp_path, three_accepting_nodes):
    store = FakeStore()
    coordinator = Coordinator(three_accepting_nodes, store=store, alert_log_path=tmp_path / "alerts.jsonl")
    coordinator.write_memory("fact one", source="verified_user")

    results = coordinator.read_memory("fact", top_k=5)

    assert len(results) == 1
    assert results[0].content == "fact one"
