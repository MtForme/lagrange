# Lagrange

Byzantine Memory Consensus for Agentic AI — a lightweight middleware layer
that protects the persistent memory of AI agents from poisoning attacks
(MINJA, EchoLeak, Sleeper Agents) using a three-node Byzantine Fault
Tolerant consensus system.

Every memory write is validated by three independent nodes with different
verification strategies (semantic consistency, cryptographic provenance,
temporal pattern analysis) before it is accepted into the vector store.
A memory is accepted only if at least 2/3 of the nodes agree.

See [CLAUDE.md](./CLAUDE.md) for the full design, threat model, and
development priorities.

## Status

Early scaffold. Core consensus (`lagrange/consensus/pbft.py`) and the
coordinator (`lagrange/coordinator.py`) are implemented and tested against
mock nodes. The real semantic/crypto/temporal nodes are not implemented
yet.

## Setup

```powershell
py -3.11 -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
```

## Testing

```powershell
./.venv/Scripts/python -m pytest tests/ -v
```
