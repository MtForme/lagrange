# Lagrange — Design

Byzantine Memory Consensus for agentic AI. This document describes the
threat model, the architecture, the three verification nodes, the
consensus rule, and the known open problems.

> This is the design reference. For a quick start see the
> [README](../README.md). The repository's `CLAUDE.md` is an instruction
> file for the Claude Code agent and is not the design document.

---

## 1. Problem

An AI agent with persistent memory reads that memory back into its context
on later turns and acts on it. If an attacker can get a crafted "fact" or
"instruction" written into that memory once, it influences the agent
indefinitely — a memory-poisoning attack. Published instances include
MINJA (arXiv:2503.03704), AgentPoison (arXiv:2407.12784), and
indirect prompt injection delivered through documents, web pages and
emails the agent is asked to read.

The usual defense validates memory at **retrieval** time. Lagrange
validates at **write** time instead: a bad memory never enters the store,
so it cannot be retrieved, ranked, or summarized later.

## 2. Threat model

**Attacker capability.** A grey-box attacker with:

- query access to the agent, and
- the ability to inject text into the agent's context through a normal
  channel — the user-facing interface, or external content the agent
  consumes (emails, web pages, documents, tool output).

**Attacker limitation.** No access to model weights, and no direct access
to the backend vector database or the signing key. The attacker can
influence *what text* reaches a memory write and can sometimes influence
*how the agent labels* that text, but cannot forge a cryptographic
signature or write to the store directly.

**Explicitly out of scope.**

- Node collusion: an attacker who compromises 2 of 3 nodes defeats the
  consensus. Trusted-execution-environment isolation is the long-term
  answer; not implemented.
- The coordinator is a single point of failure.
- Behavioral/outcome-level attacks that look completely normal by
  provenance, timing and topical-consistency signals (see §8).

## 3. Architecture

```
                    Agent
              write_memory / read_memory
                      │
             Lagrange Coordinator         ← single entry point; the only
                      │                     component that talks to nodes
       ┌──────────────┼──────────────┐      or to the store
       ▼              ▼              ▼
  Node A          Node B          Node C
  Semantic        Crypto          Temporal
  consistency     provenance      pattern
       │              │              │
       └──────────────┼──────────────┘
                      ▼
           simplified PBFT consensus
           (2/3 majority + specialist veto)
                      │
              accepted?  ──yes──▶  Vector store (ChromaDB)
                      │                with provenance metadata
                      └──no───▶  quarantine + alert log
```

Nodes never communicate with each other or hold shared mutable state.
Each node sees only the proposed `Memory` and a read-only `context` dict
the coordinator hands it. All coordination lives in `coordinator.py`;
all consensus logic lives in `consensus/pbft.py`.

### Write flow

1. Agent calls `write_memory(content, source, origin)`.
2. Coordinator builds a `Memory`, embeds the content once (reused by the
   store and the semantic node), attaches the top-k existing similar
   memories — each with its stored embedding — as read-only context, and
   broadcasts to all three nodes.
3. Each node returns a `NodeVote(verdict, confidence, reason)`
   independently. An exception from a node is treated as a reject vote,
   never a crash.
4. `reach_consensus` decides accept or quarantine (§5).
5. Accepted → written to the store with full provenance metadata.
   Quarantined → appended to `lagrange_alerts.jsonl`, per-source
   rejection counter incremented, escalation flagged at 3 rejections
   from one source.

### Read flow

1. Agent calls `read_memory(query, top_k)`.
2. The store returns the top-k semantically nearest **accepted** memories.
3. Each result carries its `source` and `confidence_score`; anything
   below the low-confidence threshold is flagged explicitly rather than
   trusted the same as a well-corroborated memory.

## 4. The three nodes

Each node checks a **different** property. This heterogeneity is the point
— see the veto rule in §5.

### Node A — Semantic consistency (`semantic_node.py`)

Detects a memory that is topically close to an existing one but reads as a
contradiction — the signature of a quiet fact-overwrite ("the deploy
server is *actually* prod-evil.external").

- Takes the best cosine similarity between the new content and the
  candidate similar memories. The coordinator embeds the new content once
  and passes it in (`context["query_embedding"]`); each candidate is
  compared using the embedding the store already has. The node only
  embeds anything itself as a fallback (no store, or a store that doesn't
  return embeddings) — so a real `sentence-transformers` write costs one
  encode, not one per candidate.
- If similarity ≥ `topic_threshold` **and** the text contains a negation
  / override marker (`not`, `never`, `actually`, `no longer`, …) →
  **reject**, confidence scaled by similarity.
- Otherwise accept.
- **Cold start:** with no existing memories there is nothing to be
  inconsistent with, so the node accepts at confidence 0.5.
- Default embedder is a deterministic offline hashing vectorizer (numpy +
  md5) so the node works with no network and no model download. Opt into
  `sentence-transformers` via `SemanticNode.from_sentence_transformers()`.

### Node B — Cryptographic provenance (`crypto_node.py`)

Verifies that a claimed source can be cryptographically backed.

- `source="internal_system"` **must** carry a valid Ed25519 signature
  over exactly `(content, source, timestamp)` from this instance's key.
  Missing or invalid → **reject** at 0.95 (provenance spoofing).
- `source="verified_user"` / `"external_unverified"` carry no signature
  by design and are graded by trust tier (0.7 / 0.4). A signature that is
  present but does not verify on these tiers is itself suspicious →
  reject.

The only legitimate way to produce a signed `internal_system` memory is
`Coordinator.write_internal_fact()`, which is never wired into the
agent-facing MCP surface — anything reachable by the agent is reachable
by prompt injection.

The instance key is an Ed25519 private key persisted as unencrypted
PKCS#8 PEM (`0600`). `Signer.load_or_create(path)` creates it on first
run and reuses it afterwards, so a signature written before a restart
still verifies after one; the MCP server reads its path from
`LAGRANGE_KEY_PATH`. A bare `Signer()` generates a throwaway key and is
only for tests and one-shot scripts.

### Node C — Temporal pattern analysis (`temporal_node.py`)

Looks at *when* and *from what context* a memory arrives, independent of
its claimed source or content.

- `origin ∈ {email, webpage, readme, document, tool_output}` — an
  indirect injection delivery vector — is always flagged. Reject at 0.9
  if the content also reads as an imperative instruction ("ignore
  previous…", "from now on…", "you must always…"), else reject at 0.55.
- A burst of writes from one source in a short window (default > 5 in
  5 s) looks scripted → reject at 0.7.
- `origin ∈ {direct_chat, internal_bootstrap}` within normal timing →
  accept.

Node C keeps its own private burst history; that state is never shared.

## 5. Consensus rule (`consensus/pbft.py`)

Simplified PBFT: a single synchronous round, no leader election or view
changes — the coordinator drives every round, so only PBFT's *safety*
property is needed.

A memory is accepted iff:

- **≥ 2/3** of nodes vote accept, **and**
- **no** node rejects with confidence ≥ `VETO_CONFIDENCE` (0.85).

**Why the veto.** A plain 2/3 majority is right for *redundant* replicas
all checking the same property, where a lone dissenter is presumed
faulty. Lagrange's nodes are *heterogeneous* — for many attacks only one
node is even equipped to notice (only Node C looks at the delivery
vector; A and B have no opinion and happily vote accept). Letting two
indifferent nodes outvote one alarmed specialist would defeat the purpose
of having specialists. So one confident specialist rejection quarantines.

**Confidence score.** Computed from *every* vote, not just the winning
side. A dissenting vote pulls the score down even when outvoted 2–1. This
is what lets "accepted but flagged" memories (e.g. a real fact learned
from a web page) surface with visibly lower confidence at read time.

**Fail-safe by construction.** No votes, a tie, anything short of the
threshold, or one confident veto all resolve to quarantine. There is no
code path that accepts by default.

## 6. Provenance metadata

Every stored memory carries:

| Field | Meaning |
|---|---|
| `source` | `verified_user` / `internal_system` / `external_unverified` |
| `timestamp` | when it was written |
| `confidence_score` | 0.0–1.0, from consensus over all node votes |
| `signature` | Ed25519 signature of `content + source + timestamp` (internal only) |
| `accepted` | consensus outcome |
| `node_votes` | each node's verdict, confidence and reason |

## 7. Configuration

`lagrange/config.py` holds `LagrangeConfig` — every deployment-tunable
value with a production-safe default — plus `build_coordinator(config)`,
the one place the signer, embedder, store, three nodes and coordinator
are wired together. `LagrangeConfig.from_env()` reads `LAGRANGE_<FIELD>`
variables and overrides only what is set; an unparseable value raises
rather than being ignored. The MCP server is `build_coordinator(
LagrangeConfig.from_env())` and nothing more. The tunable knobs are the
store/key/log paths, the embedder choice, `query_top_k`, the consensus
`threshold` and `veto_confidence`, the escalation threshold, and the
semantic/temporal node parameters — see the README's Configuration table.

## 8. Known open problems

- **Policy injection via trusted direct chat.** A plausible brand-new
  "policy" planted through the normal interface — no spoofed source, no
  indirect vector, no existing fact to contradict — fires none of the
  three heuristics. This is MINJA's actual threat shape. Closing it needs
  outcome/behavioral analysis, not provenance metadata.
  Documented as a passing test in `tests/test_attacks.py`
  (`test_KNOWN_LIMITATION_...`).
- **Heuristic nodes.** The contradiction and instruction detectors are
  keyword lists — bypassable by paraphrase. They are defense-in-depth,
  not a solved classifier.
- **Coordinator SPOF.** Future work: replicated coordinator.
- **Node collusion.** 2/3 compromised nodes defeat the system. Future
  work: TEE attestation.
- **Cold start.** Node A needs existing memories to detect anomalies.

## 9. Research context

Inspired by the Chronos Vulnerability taxonomy (arXiv:2607.19433).

- **A-MemGuard** (arXiv:2510.02373) — consensus validation at retrieval
  time. Lagrange intervenes at write time instead, and uses heterogeneous
  node strategies rather than one mechanism.
- **MINJA** (arXiv:2503.03704) — the attack Lagrange defends against.
- **AgentPoison** (arXiv:2407.12784) — poisoning via knowledge bases.
- **MemTrust** (arXiv:2601.07004) — zero-trust architecture for AI memory.
