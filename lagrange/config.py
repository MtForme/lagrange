"""Deployment configuration: one dataclass, env-var overrides, and the
factory that assembles the full three-node Coordinator.

Every field has a working default. `LagrangeConfig.from_env()` overrides
only the variables that are actually set (all named `LAGRANGE_<FIELD>`),
so an unconfigured deployment still runs. `build_coordinator()` is the
single place the signer, embedder, store, three nodes and Coordinator get
wired together — the MCP server uses it so an operator can tune behavior
without touching code.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from lagrange.consensus.pbft import DEFAULT_THRESHOLD, VETO_CONFIDENCE
from lagrange.coordinator import (
    DEFAULT_ESCALATION_THRESHOLD,
    DEFAULT_QUERY_TOP_K,
    Coordinator,
)
from lagrange.nodes.semantic_node import DEFAULT_TOPIC_THRESHOLD
from lagrange.nodes.temporal_node import TemporalNode

ENV_PREFIX = "LAGRANGE_"
_ST_EMBEDDER_ALIASES = frozenset({"st", "sentence-transformers", "sentence_transformers"})


@dataclass(frozen=True)
class LagrangeConfig:
    """Every deployment-tunable knob, with production-safe defaults."""

    # storage and keys
    key_path: str = "./lagrange_signing_key.pem"
    db_path: str = "./chroma_db"
    alert_log_path: str = "./lagrange_alerts.jsonl"

    # embedder: "hashing" (offline, default) or "sentence-transformers"
    embedder: str = "hashing"
    st_model: str = "all-MiniLM-L6-v2"

    # consensus
    query_top_k: int = DEFAULT_QUERY_TOP_K
    consensus_threshold: float = DEFAULT_THRESHOLD
    veto_confidence: float = VETO_CONFIDENCE
    escalation_threshold: int = DEFAULT_ESCALATION_THRESHOLD

    # node A — semantic
    semantic_topic_threshold: float = DEFAULT_TOPIC_THRESHOLD

    # node C — temporal
    temporal_burst_window_seconds: float = 5.0
    temporal_burst_threshold: int = 5

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> LagrangeConfig:
        """Build a config from `LAGRANGE_<FIELD>` environment variables.

        Only set variables are read; everything else keeps its default.
        A value that can't be parsed as its field's type raises ValueError
        rather than being silently ignored.
        """
        environ = os.environ if environ is None else environ
        overrides: dict[str, Any] = {}
        for f in fields(cls):
            env_key = ENV_PREFIX + f.name.upper()
            if env_key in environ:
                overrides[f.name] = _coerce(f.default, environ[env_key], env_key)
        return cls(**overrides)


def _coerce(default: Any, raw: str, env_key: str) -> Any:
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    for typ in (int, float):
        if type(default) is typ:
            try:
                return typ(raw)
            except ValueError:
                raise ValueError(f"{env_key}={raw!r} is not a valid {typ.__name__}") from None
    return raw


def build_coordinator(config: LagrangeConfig | None = None) -> Coordinator:
    """Assemble the real three-node Coordinator from `config`.

    Imports the ChromaDB-backed store lazily so `import lagrange.config`
    stays cheap and dependency-light.
    """
    config = config or LagrangeConfig()

    from lagrange.crypto.signer import Signer
    from lagrange.memory.store import MemoryStore
    from lagrange.nodes.crypto_node import CryptoNode

    signer = Signer.load_or_create(config.key_path)
    semantic = _build_semantic_node(config)
    store = MemoryStore(embedder=semantic.embedder, path=config.db_path)
    nodes = [
        semantic,
        CryptoNode(signer),
        TemporalNode(
            burst_window_seconds=config.temporal_burst_window_seconds,
            burst_threshold=config.temporal_burst_threshold,
        ),
    ]
    return Coordinator(
        nodes,
        store=store,
        signer=signer,
        alert_log_path=config.alert_log_path,
        query_top_k=config.query_top_k,
        consensus_threshold=config.consensus_threshold,
        veto_confidence=config.veto_confidence,
        escalation_threshold=config.escalation_threshold,
    )


def _build_semantic_node(config: LagrangeConfig):
    from lagrange.nodes.semantic_node import SemanticNode

    if config.embedder in _ST_EMBEDDER_ALIASES:
        return SemanticNode.from_sentence_transformers(config.st_model, topic_threshold=config.semantic_topic_threshold)
    if config.embedder != "hashing":
        raise ValueError(f"unknown embedder {config.embedder!r}; use 'hashing' or 'sentence-transformers'")
    return SemanticNode(topic_threshold=config.semantic_topic_threshold)
