"""Simplified Byzantine consensus (PBFT-style, single round, no view changes).

Lagrange only needs the safety property of PBFT — accept a value iff at
least 2/3 of independent replicas agree — not its full liveness/leader
election machinery, since the coordinator itself drives every round
synchronously. This module intentionally stays small; any extra
complexity belongs here, not in coordinator.py or the nodes.
"""

from __future__ import annotations

from dataclasses import dataclass

from lagrange.memory.schema import NodeVote

DEFAULT_THRESHOLD = 2 / 3
_EPSILON = 1e-9


@dataclass
class ConsensusResult:
    """Outcome of running consensus over a set of node votes."""

    accepted: bool
    confidence_score: float
    votes: list[NodeVote]
    reason: str


def reach_consensus(votes: list[NodeVote], threshold: float = DEFAULT_THRESHOLD) -> ConsensusResult:
    """Decide accept/quarantine for a set of independent node votes.

    Fail-safe by construction: no votes, a tie, or anything short of the
    threshold results in rejection. There is no code path that accepts a
    memory by default — silence or ambiguity always quarantines.
    """
    if not votes:
        return ConsensusResult(
            accepted=False,
            confidence_score=0.0,
            votes=votes,
            reason="no votes received — quarantined",
        )

    accept_votes = [v for v in votes if v.verdict]
    accept_ratio = len(accept_votes) / len(votes)
    accepted = accept_ratio >= threshold - _EPSILON

    if accepted:
        # confidence in an accept = how confident the accepting nodes were
        confidence_score = sum(v.confidence for v in accept_votes) / len(accept_votes)
    else:
        # confidence in a reject = how confident the rejecting nodes were
        reject_votes = [v for v in votes if not v.verdict]
        confidence_score = sum(v.confidence for v in reject_votes) / len(reject_votes)

    reason = "; ".join(
        f"{v.node_id}={'accept' if v.verdict else 'reject'}({v.confidence:.2f}: {v.reason})"
        for v in votes
    )

    return ConsensusResult(
        accepted=accepted,
        confidence_score=round(confidence_score, 4),
        votes=votes,
        reason=reason,
    )
