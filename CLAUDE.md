# Lagrange — Byzantine Memory Consensus for Agentic AI

## Project Overview

Lagrange is a lightweight middleware layer that protects the persistent memory of AI agents from poisoning attacks (MINJA, EchoLeak, Sleeper Agents) using a three-node Byzantine Fault Tolerant consensus system.

The core insight: instead of trusting memory blindly at retrieval time, every memory write is validated by three independent nodes with different verification strategies. A memory is accepted only if at least 2/3 nodes agree on its provenance metadata.

**Threat model**: grey-box attacker with query access and context injection capability via normal user interface or external environments (emails, web pages, documents). Cannot access internal weights or backend database directly.

---

## Core Concept

```
Agent AI
    ↓ write/read memory
Lagrange Coordinator
    ↓ broadcasts to all three nodes
Node A (Semantic)  |  Node B (Cryptographic)  |  Node C (Temporal)
    ↓
2/3 consensus required → memory accepted with provenance metadata
    ↓
Vector Database (ChromaDB / Pinecone / Weaviate)
```

Each memory entry is tagged with:
- `source`: who wrote it (verified_user / internal_system / external_unverified)
- `timestamp`: when it was written
- `confidence_score`: 0.0-1.0 based on consensus
- `signature`: cryptographic hash of content + metadata
- `node_votes`: individual verdicts from each node

---

## Three Nodes — Different Verification Strategies

**Node A — Semantic Consistency**
Checks if the incoming memory is semantically consistent with existing memories. Uses embedding similarity to detect anomalies — a poisoned memory often introduces beliefs that contradict established facts.

**Node B — Cryptographic Provenance**
Verifies the source of the memory using digital signatures. Internal system memories are signed with a private key. External inputs from users or web pages are tagged as unverified. Signature mismatch = low confidence.

**Node C — Temporal Pattern Analysis**
Analyzes when the memory arrives and from what context. A memory that arrives embedded in an email, a README file, or a web page (indirect injection vector) gets flagged. Unusual timing patterns are suspicious.

---

## Tech Stack

- **Language**: Python 3.11+
- **Memory store**: ChromaDB (local, open source vector database)
- **Embeddings**: sentence-transformers (local, no API needed)
- **Consensus protocol**: simplified PBFT (Practical Byzantine Fault Tolerance)
- **Cryptography**: Python `cryptography` library (Ed25519 signatures)
- **Interface**: MCP server (Model Context Protocol) for agent integration
- **Testing**: pytest

---

## Project Structure

```
lagrange/
├── CLAUDE.md                  # this file
├── README.md
├── requirements.txt
├── lagrange/
│   ├── __init__.py
│   ├── coordinator.py         # orchestrates consensus, single entry point
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── base_node.py       # abstract base class for all nodes
│   │   ├── semantic_node.py   # Node A: embedding similarity check
│   │   ├── crypto_node.py     # Node B: signature verification
│   │   └── temporal_node.py   # Node C: timing and source pattern analysis
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py           # ChromaDB wrapper with provenance metadata
│   │   └── schema.py          # Memory and Vote dataclasses
│   ├── consensus/
│   │   ├── __init__.py
│   │   └── pbft.py            # simplified Byzantine consensus logic
│   ├── crypto/
│   │   ├── __init__.py
│   │   └── signer.py          # Ed25519 key management and signing
│   └── mcp_server.py          # MCP server exposing write_memory / read_memory tools
├── tests/
│   ├── test_coordinator.py
│   ├── test_nodes.py
│   ├── test_consensus.py
│   └── test_attacks.py        # simulated MINJA and indirect injection attacks
└── examples/
    ├── basic_usage.py          # standalone Python usage
    └── agent_integration.py   # integration with a LangChain / LlamaIndex agent
```

---

## Core Data Schema

```python
@dataclass
class Memory:
    id: str
    content: str
    source: str           # "verified_user" | "internal_system" | "external_unverified"
    timestamp: float
    embedding: list[float]
    signature: str        # Ed25519 signature of content + source + timestamp
    confidence_score: float  # 0.0-1.0, set after consensus
    accepted: bool

@dataclass
class NodeVote:
    node_id: str          # "semantic" | "crypto" | "temporal"
    verdict: bool         # accept or reject
    confidence: float     # node's confidence in its verdict
    reason: str           # human-readable explanation
```

---

## Key Behaviors

**Write flow**:
1. Agent calls `write_memory(content, source)`
2. Coordinator broadcasts to all three nodes
3. Each node independently evaluates and returns a NodeVote
4. If 2/3 nodes accept → memory is written with full provenance metadata
5. If majority rejects → memory is quarantined, alert is raised

**Read flow**:
1. Agent calls `read_memory(query)`
2. ChromaDB returns top-k semantically similar memories
3. Each memory is returned with its confidence_score and source
4. Low confidence memories are flagged in the response

**Alert system**:
- Rejected memories are logged to lagrange_alerts.jsonl
- Pattern detection: if same source generates multiple rejections → escalation

---

## Development Priorities

1. Start simple: get basic consensus working with mock nodes before implementing real verification logic
2. Test with attacks first: write test_attacks.py before implementing defenses — red team mindset
3. Keep nodes independent: nodes must not share state during consensus
4. Latency target: < 50ms overhead per memory write for production viability
5. Fail safe: if consensus cannot be reached, default to quarantine not acceptance

---

## Known Open Problems

- Coordinator is a single point of failure — future work: replicated coordinator
- Node collusion: if attacker compromises 2/3 nodes, system fails — TEE integration is long-term answer
- Cold start: semantic node needs existing memories to detect anomalies
- Performance: three-node consensus adds latency — needs benchmarking

---

## Research Context

Inspired by the Chronos Vulnerability taxonomy (arXiv:2607.19433).

Related work:
- A-MemGuard (arXiv:2510.02373) — consensus validation at retrieval time
- MINJA (arXiv:2503.03704) — the attack Lagrange defends against
- AgentPoison (arXiv:2407.12784) — memory poisoning via knowledge bases
- MemTrust (arXiv:2601.07004) — zero-trust architecture for AI memory

Lagrange differs from A-MemGuard by intervening at write time rather than retrieval time, and by using heterogeneous node strategies rather than a single consensus mechanism.

---

## Commands for Claude Code

- Always run pytest tests/ before considering any feature complete
- When implementing a node, first write the test, then implement
- Keep each node under 150 lines — complexity belongs in consensus/pbft.py
- Never let nodes communicate directly — all coordination through coordinator.py
- When in doubt, quarantine rather than accept
