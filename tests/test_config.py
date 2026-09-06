"""Tests for lagrange/config.py — the deployment config dataclass, its
env-var overrides, and the build_coordinator() factory.
"""

from __future__ import annotations

import pytest

from lagrange.config import LagrangeConfig, build_coordinator


def test_from_env_with_nothing_set_is_all_defaults():
    config = LagrangeConfig.from_env({})
    assert config == LagrangeConfig()


def test_from_env_overrides_only_the_variables_that_are_set():
    config = LagrangeConfig.from_env(
        {
            "LAGRANGE_DB_PATH": "/data/chroma",
            "LAGRANGE_QUERY_TOP_K": "9",
            "LAGRANGE_CONSENSUS_THRESHOLD": "0.9",
            "LAGRANGE_EMBEDDER": "sentence-transformers",
            "UNRELATED": "ignored",
        }
    )
    assert config.db_path == "/data/chroma"
    assert config.query_top_k == 9 and isinstance(config.query_top_k, int)
    assert config.consensus_threshold == 0.9
    assert config.embedder == "sentence-transformers"
    # untouched fields keep their defaults
    assert config.key_path == LagrangeConfig().key_path
    assert config.veto_confidence == LagrangeConfig().veto_confidence


def test_from_env_rejects_an_unparseable_value():
    with pytest.raises(ValueError, match="LAGRANGE_QUERY_TOP_K"):
        LagrangeConfig.from_env({"LAGRANGE_QUERY_TOP_K": "five"})

    with pytest.raises(ValueError, match="LAGRANGE_VETO_CONFIDENCE"):
        LagrangeConfig.from_env({"LAGRANGE_VETO_CONFIDENCE": "high"})


def test_build_coordinator_wires_config_through(tmp_path):
    config = LagrangeConfig(
        key_path=str(tmp_path / "key.pem"),
        db_path=str(tmp_path / "db"),
        alert_log_path=str(tmp_path / "alerts.jsonl"),
        query_top_k=7,
        consensus_threshold=0.9,
        veto_confidence=0.75,
        escalation_threshold=2,
        temporal_burst_window_seconds=3.0,
        temporal_burst_threshold=4,
    )

    coordinator = build_coordinator(config)

    assert coordinator.query_top_k == 7
    assert coordinator.consensus_threshold == 0.9
    assert coordinator.veto_confidence == 0.75
    assert coordinator.escalation_threshold == 2
    assert (tmp_path / "key.pem").exists()  # signer key created at the configured path
    temporal = next(n for n in coordinator.nodes if n.node_id == "temporal")
    assert temporal.burst_window_seconds == 3.0
    assert temporal.burst_threshold == 4


def test_build_coordinator_rejects_an_unknown_embedder(tmp_path):
    config = LagrangeConfig(
        key_path=str(tmp_path / "key.pem"),
        db_path=str(tmp_path / "db"),
        embedder="word2vec",
    )
    with pytest.raises(ValueError, match="unknown embedder"):
        build_coordinator(config)


def test_build_coordinator_round_trips_a_signed_internal_fact(tmp_path):
    config = LagrangeConfig(
        key_path=str(tmp_path / "key.pem"),
        db_path=str(tmp_path / "db"),
        alert_log_path=str(tmp_path / "alerts.jsonl"),
    )
    coordinator = build_coordinator(config)

    fact = coordinator.write_internal_fact("the deployment server is prod-1.internal")

    assert fact.accepted is True
