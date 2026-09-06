"""Measure the per-write latency Lagrange's consensus adds.

CLAUDE.md sets a target of < 50 ms of overhead per memory write for
production viability. "Overhead" here is everything
`coordinator.write_memory(...)` does *except* the vector-store calls a
naive memory system would also make — i.e. building the proposal,
running the three nodes, and reaching consensus. It is measured directly
by subtracting the time spent inside `store.query` + `store.add` from
the end-to-end call, on the same writes.

Also reported: the full write path, each store call, and each node's
`evaluate(...)` in isolation, on a store pre-populated with
`--store-size` memories, as p50 / p95 / p99.

Usage:

    python scripts/benchmark.py                       # offline hashing embedder
    python scripts/benchmark.py --store-size 5000
    python scripts/benchmark.py --embedder st         # sentence-transformers
    python scripts/benchmark.py --persist             # on-disk ChromaDB

Nothing here touches the network unless `--embedder st` is passed (which
downloads the model once).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lagrange.coordinator import Coordinator
from lagrange.crypto.signer import Signer
from lagrange.memory.schema import Memory
from lagrange.memory.store import MemoryStore
from lagrange.nodes.crypto_node import CryptoNode
from lagrange.nodes.semantic_node import SemanticNode
from lagrange.nodes.temporal_node import TemporalNode

_WORDS = (
    "deployment server database migration rollback latency cache token user "
    "preference notification schedule invoice tenant region backup quota "
    "endpoint retry timeout webhook cursor embedding vector index shard replica"
).split()


def _sentence(i: int) -> str:
    rng = (i * 2654435761) & 0xFFFFFFFF
    picks = []
    for _ in range(8):
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        picks.append(_WORDS[rng % len(_WORDS)])
    return f"note {i}: " + " ".join(picks)


class TimingStore:
    """Wraps a MemoryStore and accumulates time spent in query/add so the
    benchmark can subtract it from the end-to-end write latency.
    """

    def __init__(self, inner: MemoryStore) -> None:
        self.inner = inner
        self.query_s = 0.0
        self.add_s = 0.0

    def reset(self) -> None:
        self.query_s = self.add_s = 0.0

    def query(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return self.inner.query(*args, **kwargs)
        finally:
            self.query_s += time.perf_counter() - start

    def add(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return self.inner.add(*args, **kwargs)
        finally:
            self.add_s += time.perf_counter() - start


def _stats_ms(samples_s: list[float]) -> dict[str, float]:
    ordered = sorted(samples_s)
    n = len(ordered)

    def pct(p: float) -> float:
        return ordered[min(n - 1, int(p * n))] * 1000.0

    return {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99), "mean": statistics.fmean(ordered) * 1000.0}


def _report(label: str, samples_s: list[float]) -> dict[str, float]:
    s = _stats_ms(samples_s)
    print(
        f"  {label:<28} p50 {s['p50']:8.3f}   p95 {s['p95']:8.3f}   p99 {s['p99']:8.3f}   mean {s['mean']:8.3f}   (ms)"
    )
    return s


def _time_loop(label: str, count: int, fn) -> dict[str, float]:
    samples = []
    for i in range(count):
        start = time.perf_counter()
        fn(i)
        samples.append(time.perf_counter() - start)
    return _report(label, samples)


def _build_semantic(kind: str) -> SemanticNode:
    if kind == "st":
        print("loading sentence-transformers model (first run downloads it)...")
        return SemanticNode.from_sentence_transformers()
    return SemanticNode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=500, help="measured writes (default 500)")
    parser.add_argument("--store-size", type=int, default=1000, help="memories to pre-populate (default 1000)")
    parser.add_argument("--warmup", type=int, default=50, help="unmeasured warmup writes (default 50)")
    parser.add_argument("--embedder", choices=("hashing", "st"), default="hashing")
    parser.add_argument("--persist", action="store_true", help="use an on-disk ChromaDB instead of in-memory")
    args = parser.parse_args()

    semantic = _build_semantic(args.embedder)
    db_path = str(Path(tempfile.mkdtemp()) / "chroma") if args.persist else None
    raw_store = MemoryStore(embedder=semantic.embedder, path=db_path)
    store = TimingStore(raw_store)
    signer = Signer()
    coordinator = Coordinator(
        [semantic, CryptoNode(signer), TemporalNode()],
        store=store,
        signer=signer,
        alert_log_path=Path(tempfile.mkdtemp()) / "alerts.jsonl",
    )

    print(
        f"\nembedder={args.embedder}  store={'on-disk' if args.persist else 'in-memory'}  "
        f"store_size={args.store_size}  count={args.count}\n"
    )

    print(f"pre-populating {args.store_size} memories...")
    for i in range(args.store_size):
        raw_store.add(Memory(id=str(uuid.uuid4()), content=_sentence(i), source="verified_user", timestamp=1000.0 + i))

    for i in range(args.warmup):
        coordinator.write_memory(_sentence(10_000_000 + i), source="verified_user", context={"origin": "direct_chat"})

    # End-to-end, and the consensus overhead within it (total minus the
    # time spent inside store.query + store.add on that same call).
    total_samples: list[float] = []
    overhead_samples: list[float] = []
    for i in range(args.count):
        store.reset()
        start = time.perf_counter()
        coordinator.write_memory(_sentence(20_000_000 + i), source="verified_user", context={"origin": "direct_chat"})
        elapsed = time.perf_counter() - start
        total_samples.append(elapsed)
        overhead_samples.append(elapsed - store.query_s - store.add_s)

    print("full write path:")
    total = _report("write_memory (end to end)", total_samples)
    overhead = _report("consensus overhead", overhead_samples)

    print("\ncomponents:")

    def _add_fresh(i: int) -> None:
        raw_store.add(
            Memory(
                id=str(uuid.uuid4()),
                content=_sentence(30_000_000 + i),
                source="verified_user",
                timestamp=2000.0 + i,
            )
        )

    _time_loop("store.add", args.count, _add_fresh)
    _time_loop("store.query (top_k=5)", args.count, lambda i: raw_store.query(_sentence(40_000_000 + i), top_k=5))

    sample_ctx = {"origin": "direct_chat", "similar_memories": raw_store.query(_sentence(1), top_k=5)}

    def _node_call(node):
        return lambda i: node.evaluate(
            Memory(id="b", content=_sentence(50_000_000 + i), source="verified_user", timestamp=3000.0 + i),
            sample_ctx,
        )

    for node in (semantic, CryptoNode(signer), TemporalNode()):
        _time_loop(f"{node.node_id}_node.evaluate", args.count, _node_call(node))

    verdict = "PASS" if overhead["p95"] < 50 else "FAIL"
    print(
        f"\nconsensus overhead: p50 {overhead['p50']:.3f} ms, p95 {overhead['p95']:.3f} ms  "
        f"(end-to-end write p50 {total['p50']:.2f} ms)"
    )
    print(f"target: < 50 ms overhead per write  ->  {verdict}\n")


if __name__ == "__main__":
    main()
