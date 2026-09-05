"""Node B — Cryptographic Provenance.

Checks whether a memory's claimed source can be cryptographically
backed up. This is the node that catches the specific privilege-
escalation shape of attack described in CLAUDE.md's threat model: a
grey-box attacker with query access / context-injection capability can
influence *content* and can sometimes get an agent to mislabel that
content's source, but cannot access the backend signing key. So:

- source="internal_system" MUST carry a valid Ed25519 signature from
  this Lagrange instance's own key, over exactly this memory's
  (content, source, timestamp). No valid signature = treated as a
  spoofing attempt, rejected with high confidence.
- source="verified_user" / "external_unverified" carry no signature by
  design (see Coordinator.write_memory's docstring) and are graded by
  trust tier instead. If one shows up with a signature that doesn't
  verify, that's itself suspicious (someone trying to dress up
  low-trust content as more credible) and is rejected.
"""

from __future__ import annotations

from typing import Any

from lagrange.crypto.signer import Signer
from lagrange.memory.schema import Memory, NodeVote
from lagrange.nodes.base_node import BaseNode

# Baseline confidence for sources that carry no signature at all,
# reflecting how much this node alone trusts that trust tier.
_UNSIGNED_TIER_CONFIDENCE = {
    "verified_user": 0.7,
    "external_unverified": 0.4,
}


class CryptoNode(BaseNode):
    node_id = "crypto"

    def __init__(self, signer: Signer) -> None:
        self.signer = signer

    def evaluate(self, memory: Memory, context: dict[str, Any]) -> NodeVote:
        if memory.source == "internal_system":
            return self._evaluate_internal_claim(memory)
        return self._evaluate_unsigned_tier(memory)

    def _evaluate_internal_claim(self, memory: Memory) -> NodeVote:
        if self.signer.verify(memory.content, memory.source, memory.timestamp, memory.signature):
            return NodeVote(self.node_id, True, 0.99, "valid internal_system signature")
        return NodeVote(
            self.node_id,
            False,
            0.95,
            "source claims internal_system but signature is missing or invalid — possible provenance spoofing",
        )

    def _evaluate_unsigned_tier(self, memory: Memory) -> NodeVote:
        if memory.signature and not self.signer.verify(
            memory.content, memory.source, memory.timestamp, memory.signature
        ):
            return NodeVote(
                self.node_id,
                False,
                0.6,
                f"unverifiable signature attached to a {memory.source} memory",
            )
        confidence = _UNSIGNED_TIER_CONFIDENCE.get(memory.source, 0.3)
        return NodeVote(self.node_id, True, confidence, f"{memory.source} requires no signature")
