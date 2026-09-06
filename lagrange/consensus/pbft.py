"""Simplified Byzantine consensus (PBFT-style, single round, no view changes).

Lagrange only needs the safety property of PBFT — accept a value iff at
least 2/3 of independent replicas agree — not its full liveness/leader
election machinery, since the coordinator itself drives every round
synchronously. This module intentionally stays small; any extra
complexity belongs here, not in coordinator.py or the nodes.

Veto rule: plain 2/3 majority is the right rule for *redundant*
replicas checking the same property, where a lone dissenter is
presumed to be the faulty/Byzantine one. Lagrange's three nodes are
deliberately heterogeneous — each checks a different property — so a
lone dissenter is often the ONLY node equipped to notice a given attack
at all (e.g. only Node C looks at delivery vector; Node A and Node B
have no opinion on it and will happily vote accept). Letting two
indifferent nodes outvote one alarmed specialist would silently defeat
the point of having specialists. So: a single vote rejecting with
confidence >= VETO_CONFIDENCE blocks acceptance outright, regardless of
the other two votes — "when in doubt, quarantine" (CLAUDE.md) extended
to "when one specialist is sure, quarantine."
"""

from __future__ import annotations

from dataclasses import dataclass

from lagrange.memory.schema import NodeVote

DEFAULT_THRESHOLD = 2 / 3
VETO_CONFIDENCE = 0.85
_EPSILON = 1e-9


@dataclass
class ConsensusResult:
    """Outcome of running consensus over a set of node votes."""

    accepted: bool
    confidence_score: float
    votes: list[NodeVote]
    reason: str


def reach_consensus(
    votes: list[NodeVote],
    threshold: float = DEFAULT_THRESHOLD,
    veto_confidence: float = VETO_CONFIDENCE,
) -> ConsensusResult:
    """Decide accept/quarantine for a set of independent node votes.

    Fail-safe by construction: no votes, a tie, anything short of the
    threshold, or a single high-confidence veto results in rejection.
    There is no code path that accepts a memory by default — silence,
    ambiguity, or a lone confident specialist always quarantines.
    """
    if not votes:
        return ConsensusResult(
            accepted=False,
            confidence_score=0.0,
            votes=votes,
            reason="no votes received — quarantined",
        )

    accept_votes = [v for v in votes if v.verdict]
    reject_votes = [v for v in votes if not v.verdict]
    accept_ratio = len(accept_votes) / len(votes)
    vetoed_by = next((v for v in reject_votes if v.confidence >= veto_confidence), None)
    accepted = accept_ratio >= threshold - _EPSILON and vetoed_by is None

    # confidence_score reflects every vote, not just the winning side: a
    # node that dissents (e.g. Node C flagging an indirect injection
    # vector) still pulls the overall confidence down even when it's
    # outvoted 2-1. A vote agreeing with the final decision contributes
    # its own confidence; a dissenting vote contributes the inverse of
    # its confidence, since a confident dissent is itself evidence
    # against the outcome. This is what lets "accepted but flagged"
    # memories surface at read time (see CLAUDE.md's read flow).
    agreement_scores = [v.confidence if v.verdict == accepted else (1 - v.confidence) for v in votes]
    confidence_score = sum(agreement_scores) / len(votes)

    reason = "; ".join(
        f"{v.node_id}={'accept' if v.verdict else 'reject'}({v.confidence:.2f}: {v.reason})" for v in votes
    )
    if vetoed_by is not None:
        reason = f"VETOED by {vetoed_by.node_id} ({vetoed_by.confidence:.2f}): {reason}"

    return ConsensusResult(
        accepted=accepted,
        confidence_score=round(confidence_score, 4),
        votes=votes,
        reason=reason,
    )
