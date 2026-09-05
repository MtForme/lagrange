"""Node A — Semantic Consistency.

Checks whether an incoming memory is semantically consistent with
existing memories, using embedding similarity to detect anomalies: a
poisoned memory often introduces a belief that contradicts an
established fact on the same topic (e.g. quietly overwriting "the
deployment server is prod-1.internal" with a lookalike claim pointing
at attacker infrastructure).

The production embedder is sentence-transformers (see
`from_sentence_transformers`), but it is never imported or downloaded
implicitly — only when the application explicitly opts in. The default
embedder is a small deterministic hashing vectorizer (numpy + md5, no
network, no PYTHONHASHSEED dependence) so this node works out of the
box and stays fast and offline in tests. Swapping embedders never
changes this node's logic, only the vectors it compares.

Known limitation (see CLAUDE.md's "cold start" open problem): with no
existing memories to compare against, there is nothing to be
inconsistent with, so new memories are accepted by default.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Sequence

import numpy as np

from lagrange.memory.schema import Memory, NodeVote
from lagrange.nodes.base_node import BaseNode

Embedder = Callable[[str], Sequence[float]]

# Lower than it might look: this is calibrated for the bag-of-words
# fallback embedder, where even near-duplicate topic sentences don't
# score as high as a real sentence embedding model would (see
# _hashing_embedder). Swapping in from_sentence_transformers() gives
# much better-separated similarity scores; this threshold may need
# retuning per embedder in practice.
DEFAULT_TOPIC_THRESHOLD = 0.6
_HASHING_VECTOR_DIM = 256

# Common function words stripped before hashing so two sentences about
# the same entity aren't pulled apart just by shared "the"/"is"/etc.
# noise, and aren't falsely pulled together by it either. Negation words
# are deliberately kept — they're the signal _looks_contradictory looks
# for, and topic-similarity should still see them as part of the text.
_STOPWORDS = frozenset({"the", "a", "an", "is", "are", "was", "were", "it", "to", "of", "in", "on", "for", "and", "or"})
_PUNCTUATION = ",.;:!?\"'()[]{}"

# Heuristic cues that a sentence is negating/overwriting something,
# rather than restating or elaborating on it. Combined with high topical
# similarity, this is the signature of a quiet fact-overwrite attack.
_CONTRADICTION_MARKERS = (
    " not ",
    "n't ",
    " never ",
    " false",
    " incorrect",
    " actually,",
    " actually ",
    " no longer",
    " isn't",
    " wasn't",
    " won't",
)


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    for char in _PUNCTUATION:
        lowered = lowered.replace(char, "")
    return [token for token in lowered.split() if token not in _STOPWORDS]


def _hashing_embedder(text: str) -> np.ndarray:
    """Deterministic bag-of-words hashing vectorizer — the offline default.

    Uses md5 (stable across processes/runs) rather than Python's built-in
    hash(), which is randomized per-process by default for str objects.
    """
    vector = np.zeros(_HASHING_VECTOR_DIM)
    for token in _tokenize(text):
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % _HASHING_VECTOR_DIM
        vector[idx] += 1.0
    return vector


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    norm_a, norm_b = np.linalg.norm(a_arr), np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


class SemanticNode(BaseNode):
    node_id = "semantic"

    def __init__(self, embedder: Embedder | None = None, topic_threshold: float = DEFAULT_TOPIC_THRESHOLD) -> None:
        self.embedder = embedder or _hashing_embedder
        self.topic_threshold = topic_threshold

    @classmethod
    def from_sentence_transformers(cls, model_name: str = "all-MiniLM-L6-v2", **kwargs) -> "SemanticNode":
        """Opt-in production embedder. Imports and downloads the model
        only when explicitly called — never as an implicit default, so
        constructing a SemanticNode() never triggers network access.
        """
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        return cls(embedder=lambda text: model.encode(text), **kwargs)

    def evaluate(self, memory: Memory, context: dict[str, Any]) -> NodeVote:
        existing: list[Memory] = context.get("similar_memories") or []
        if not existing:
            return NodeVote(
                self.node_id,
                True,
                0.5,
                "cold start: no existing memories to compare against",
            )

        query_vector = self.embedder(memory.content)
        best_similarity = max(
            _cosine_similarity(query_vector, self.embedder(candidate.content)) for candidate in existing
        )

        if best_similarity >= self.topic_threshold and self._looks_contradictory(memory.content):
            confidence = round(min(0.95, 0.5 + best_similarity / 2), 4)
            return NodeVote(
                self.node_id,
                False,
                confidence,
                f"semantically close (similarity={best_similarity:.2f}) to an existing memory but reads as a contradiction",
            )

        confidence = round(min(0.95, 0.6 + 0.3 * best_similarity), 4)
        return NodeVote(
            self.node_id,
            True,
            confidence,
            f"consistent with existing memories (best similarity={best_similarity:.2f})",
        )

    @staticmethod
    def _looks_contradictory(content: str) -> bool:
        padded = f" {content.lower()} "
        return any(marker in padded for marker in _CONTRADICTION_MARKERS)
