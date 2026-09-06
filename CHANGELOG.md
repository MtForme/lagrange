# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `lagrange/config.py` — `LagrangeConfig` dataclass, `LagrangeConfig.from_env()`
  (`LAGRANGE_*` overrides), and `build_coordinator()`, the single place the
  full three-node stack is assembled. The MCP server now uses it, so store
  path, embedder, consensus threshold, veto confidence, escalation
  threshold, and the semantic/temporal node parameters are all tunable
  from the environment. See the README's Configuration table.
- `Coordinator` accepts `query_top_k`, `consensus_threshold`,
  `veto_confidence` and `escalation_threshold` (previously module-level
  constants / hardcoded in the consensus call).
- `scripts/benchmark.py` — splits each write into vector-store time, the
  one unavoidable content embedding, and consensus overhead (p50/p95/p99).
  Consensus overhead is ~0.5 ms with the hashing embedder and ~1 ms with
  `sentence-transformers` — well under the < 50 ms target. Documented in
  the README's Performance section.

### Changed
- The coordinator now embeds the new content once and shares it with the
  store and the semantic node; `store.query` returns each candidate with
  its stored embedding, so the semantic node no longer re-embeds
  candidates on every write. Cut `sentence-transformers` consensus
  overhead from ~155 ms to ~1 ms p50.

### Fixed
- `MemoryStore` rejected `np.float32` embeddings (from
  `sentence-transformers`) because np.float32 is not a `float` subclass;
  embeddings are now normalized to plain floats.
- `Signer.load(path)` / `.save(path)` / `.load_or_create(path)` — the
  Ed25519 signing key now persists as `0600` PKCS#8 PEM, so
  `internal_system` signatures keep verifying across process restarts.
  The MCP server reads `LAGRANGE_KEY_PATH` (created on first run) and
  `LAGRANGE_DB_PATH`.
- `pyproject.toml` — the project is now an installable package
  (`lagrange-memory`), with `chroma` / `embeddings` / `mcp` / `all` /
  `dev` extras and a `lagrange-mcp` console entry point.
- `LICENSE` (Apache-2.0).
- `docs/DESIGN.md` — design reference: threat model, node strategies,
  consensus rule, provenance metadata, open problems.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- `lagrange/py.typed` — the package now ships type information.

### Changed
- `README.md` rewritten for external readers.
- `requirements.txt` is now a shortcut for `pip install -e ".[dev]"`.

## [0.1.0] — unreleased

Initial implementation.

### Added
- Core schema (`Memory`, `NodeVote`) and the `BaseNode` interface.
- Simplified PBFT consensus (`consensus/pbft.py`): 2/3 acceptance
  threshold plus a single-specialist veto at confidence ≥ 0.85, with a
  confidence score computed over all votes.
- `Coordinator` — single entry point for the write/read flow, quarantine,
  and the JSONL alert log with per-source escalation.
- Node A (`SemanticNode`) — embedding-similarity contradiction detection,
  with an offline hashing embedder by default and opt-in
  `sentence-transformers`.
- Node B (`CryptoNode`) — Ed25519 provenance verification for
  `internal_system`, trust-tier grading for unsigned sources.
- Node C (`TemporalNode`) — indirect-delivery-vector flagging and write
  burst detection.
- `Signer` — Ed25519 key management for internal_system provenance.
- `MemoryStore` — ChromaDB-backed store carrying full provenance
  metadata, with an in-memory mode for tests.
- `mcp_server.py` — MCP server exposing `write_memory` / `read_memory`,
  with `internal_system` writes blocked at the agent-facing surface.
- Examples: `examples/basic_usage.py`, `examples/agent_integration.py`.
- Test suite including an end-to-end red-team suite
  (`tests/test_attacks.py`) with one intentionally-documented open gap.

[Unreleased]: https://github.com/MtForme/lagrange/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MtForme/lagrange/releases/tag/v0.1.0
