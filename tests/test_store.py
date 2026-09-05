"""Tests for lagrange/memory/store.py — the ChromaDB wrapper.

Uses chromadb.EphemeralClient() (in-memory, no disk) via path=None, so
these tests stay fast and don't leave chroma_db/ directories behind.
Embeddings are always supplied by an explicit embedder we control here
— never ChromaDB's own default embedding function — so no model ever
gets silently downloaded on first add().
"""

from __future__ import annotations

from lagrange.memory.schema import Memory
from lagrange.memory.store import MemoryStore


class FixedEmbedder:
    """Deterministic embedder for tests: exact string -> fixed vector."""

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def __call__(self, text: str):
        return self.vectors[text]


def _memory(content, source="verified_user", timestamp=1.0, memory_id=None):
    return Memory(id=memory_id or content, content=content, source=source, timestamp=timestamp)


def test_query_on_empty_store_returns_empty_list():
    store = MemoryStore(embedder=FixedEmbedder({"anything": [1.0, 0.0]}), path=None)
    assert store.query("anything") == []


def test_add_and_query_roundtrip_preserves_provenance_fields():
    embedder = FixedEmbedder({"the sky is blue": [1.0, 0.0, 0.0]})
    store = MemoryStore(embedder=embedder, path=None)
    memory = _memory("the sky is blue")
    memory.confidence_score = 0.87
    memory.accepted = True
    memory.signature = "abc123"

    store.add(memory)
    results = store.query("the sky is blue", top_k=5)

    assert len(results) == 1
    result = results[0]
    assert result.id == memory.id
    assert result.content == "the sky is blue"
    assert result.source == "verified_user"
    assert result.confidence_score == 0.87
    assert result.accepted is True
    assert result.signature == "abc123"


def test_query_returns_most_similar_memory_first():
    embedder = FixedEmbedder(
        {
            "the deployment server is prod-1.internal": [1.0, 0.0, 0.0],
            "my favorite food is pizza": [0.0, 1.0, 0.0],
            "query: server": [0.9, 0.1, 0.0],
        }
    )
    store = MemoryStore(embedder=embedder, path=None)
    store.add(_memory("my favorite food is pizza", memory_id="m1"))
    store.add(_memory("the deployment server is prod-1.internal", memory_id="m2"))

    results = store.query("query: server", top_k=1)

    assert len(results) == 1
    assert results[0].id == "m2"


def test_top_k_limits_number_of_results():
    embedder = FixedEmbedder(
        {f"fact {i}": [float(i), 0.0, 0.0] for i in range(5)} | {"query": [2.0, 0.0, 0.0]}
    )
    store = MemoryStore(embedder=embedder, path=None)
    for i in range(5):
        store.add(_memory(f"fact {i}", memory_id=f"m{i}"))

    results = store.query("query", top_k=2)

    assert len(results) == 2


def test_count_reflects_number_of_stored_memories():
    embedder = FixedEmbedder({"a": [1.0], "b": [2.0]})
    store = MemoryStore(embedder=embedder, path=None)
    assert store.count() == 0

    store.add(_memory("a", memory_id="1"))
    store.add(_memory("b", memory_id="2"))

    assert store.count() == 2


def test_reuses_memory_embedding_if_already_set_instead_of_recomputing():
    calls = []

    def tracking_embedder(text):
        calls.append(text)
        return [1.0, 0.0]

    store = MemoryStore(embedder=tracking_embedder, path=None)
    memory = _memory("precomputed", memory_id="m1")
    memory.embedding = [0.5, 0.5]

    store.add(memory)

    assert calls == []  # embedder never called: memory.embedding was already set
