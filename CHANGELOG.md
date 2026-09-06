# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-06

First public release. Byzantine Fault Tolerant consensus middleware that
validates every AI-agent memory write with three independent nodes and
stores it only on 2/3 agreement.

### Consensus and nodes
- Core schema (`Memory`, `NodeVote`) and the `BaseNode` interface.
- Simplified PBFT consensus (`consensus/pbft.py`): 2/3 acceptance
  threshold plus a single-specialist veto at confidence ≥ 0.85, with a
  confidence score computed over every vote so an outvoted dissent still
  lowers it.
- `Coordinator` — single entry point for the write/read flow, quarantine,
  and a JSONL alert log with per-source escalation. Tunable `query_top_k`,
  `consensus_threshold`, `veto_confidence`, `escalation_threshold`.
- Node A (`SemanticNode`) — embedding-similarity contradiction detection.
  Offline hashing embedder by default; opt-in `sentence-transformers`.
  Reuses the coordinator's one content embedding and the store's stored
  candidate embeddings rather than re-embedding per write.
- Node B (`CryptoNode`) — Ed25519 provenance verification for
  `internal_system`, trust-tier grading for unsigned sources.
- Node C (`TemporalNode`) — indirect-delivery-vector flagging and write
  burst detection.

### Storage and keys
- `MemoryStore` — ChromaDB-backed store carrying full provenance
  metadata, with an in-memory mode for tests; embeddings normalized to
  plain floats (accepts `np.float32` from `sentence-transformers`).
- `Signer` — Ed25519 key management with `load` / `save` /
  `load_or_create`; the key persists as `0600` PKCS#8 PEM so
  `internal_system` signatures keep verifying across restarts.

### Interface and configuration
- `mcp_server.py` — MCP server exposing `write_memory` / `read_memory`;
  `internal_system` writes are blocked at the agent-facing surface.
- `lagrange/config.py` — `LagrangeConfig`, `LagrangeConfig.from_env()`
  (`LAGRANGE_*` overrides), and `build_coordinator()`, the one place the
  full stack is assembled.
- Examples: `examples/basic_usage.py`, `examples/agent_integration.py`
  (a LangChain-shaped memory backend).

### Packaging and project
- Installable as `lagrange-memory` (Apache-2.0), with `chroma` /
  `embeddings` / `mcp` / `all` / `dev` extras, a `lagrange-mcp` console
  entry point, and shipped type information (`py.typed`).
- `docs/DESIGN.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- GitHub Actions CI (ruff + pytest on 3.11 / 3.12 / 3.13) and a
  Trusted-Publishing release workflow.
- `scripts/benchmark.py` — consensus overhead is ~0.5 ms (hashing
  embedder) to ~1 ms (`sentence-transformers`) p50, well under the
  50 ms target.

### Known limitations
- A plausible policy planted through a trusted `direct_chat` write — no
  spoofed source, no indirect vector, no contradicted fact — is not
  caught (documented as `test_KNOWN_LIMITATION_*`).
- The contradiction / instruction detectors are keyword lists.
- The coordinator is a single point of failure; 2/3 compromised nodes
  defeat consensus.

[0.1.0]: https://github.com/MtForme/lagrange/releases/tag/v0.1.0
