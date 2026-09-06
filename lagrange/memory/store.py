"""ChromaDB wrapper carrying full provenance metadata on every memory.

Embeddings are always supplied explicitly by the caller-provided
`embedder` — this store never falls back to ChromaDB's own default
embedding function, since that would silently download a model the
first time `add()` runs. Use the same embedder here as in SemanticNode
so the coordinator's "similar_memories" context and this store's own
similarity search agree on one vector space.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Any

import chromadb

from lagrange.memory.schema import Memory

Embedder = Callable[[str], Sequence[float]]

DEFAULT_COLLECTION_NAME = "lagrange_memories"


class MemoryStore:
    def __init__(
        self,
        embedder: Embedder,
        path: str | None = "./chroma_db",
        collection_name: str | None = None,
    ) -> None:
        """`path=None` uses an in-memory ephemeral client (no disk) —
        handy for tests. Any other path persists to that directory, per
        CLAUDE.md's "ChromaDB (local, open source vector database)".

        `collection_name` defaults to a shared, stable name for
        persistent stores (so re-opening the same path reattaches to
        the same data), but to a fresh random name per instance for
        ephemeral stores — otherwise, since chromadb's ephemeral
        backend is shared in-process, two unrelated `MemoryStore(path=
        None)` instances in the same test run (e.g. different tests
        using different embedding dimensions) would collide on the same
        default collection.
        """
        self.embedder = embedder
        self._client = chromadb.EphemeralClient() if path is None else chromadb.PersistentClient(path=path)
        if collection_name is None:
            collection_name = DEFAULT_COLLECTION_NAME if path is not None else f"ephemeral-{uuid.uuid4().hex}"
        self._collection = self._client.get_or_create_collection(collection_name)

    def add(self, memory: Memory) -> None:
        embedding = memory.embedding or self.embedder(memory.content)
        self._collection.add(
            ids=[memory.id],
            documents=[memory.content],
            embeddings=[list(embedding)],
            metadatas=[self._to_metadata(memory)],
        )

    def query(self, query_text: str, top_k: int = 5) -> list[Memory]:
        if self.count() == 0:
            return []
        query_embedding = self.embedder(query_text)
        results = self._collection.query(query_embeddings=[list(query_embedding)], n_results=top_k)
        return self._results_to_memories(results)

    def count(self) -> int:
        return self._collection.count()

    @staticmethod
    def _to_metadata(memory: Memory) -> dict[str, Any]:
        return {
            "source": memory.source,
            "timestamp": memory.timestamp,
            "confidence_score": memory.confidence_score,
            "accepted": memory.accepted,
            "signature": memory.signature,
        }

    @staticmethod
    def _results_to_memories(results: dict[str, Any]) -> list[Memory]:
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        memories = []
        for memory_id, content, meta in zip(ids, documents, metadatas, strict=True):
            memories.append(
                Memory(
                    id=memory_id,
                    content=content,
                    source=meta["source"],
                    timestamp=meta["timestamp"],
                    confidence_score=meta.get("confidence_score", 0.0),
                    accepted=meta.get("accepted", True),
                    signature=meta.get("signature", ""),
                )
            )
        return memories
