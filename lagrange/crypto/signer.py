"""Ed25519 key management and signing for internal_system provenance.

Only Lagrange's own trusted internal code holds the private key produced
here. A memory that *claims* `source="internal_system"` is only genuine
if it carries a signature this Signer's public key can verify — an
attacker who tricks an agent into mislabeling injected content as
internal_system still cannot forge that signature (see crypto_node.py
and CLAUDE.md's threat model: grey-box, no backend key access).
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)


def _message(content: str, source: str, timestamp: float) -> bytes:
    """Canonical byte representation signed/verified for a memory.

    Binding content + source + timestamp together means a valid
    signature can't be replayed against different metadata (e.g.
    lifting a legitimately-signed internal_system signature and
    reattaching it to different, attacker-chosen content).
    """
    return f"{content}\x00{source}\x00{timestamp!r}".encode()


class Signer:
    """Holds an Ed25519 keypair and signs/verifies memory provenance."""

    def __init__(self, private_key: Ed25519PrivateKey | None = None) -> None:
        self._private_key = private_key or Ed25519PrivateKey.generate()
        self.public_key: Ed25519PublicKey = self._private_key.public_key()

    def sign(self, content: str, source: str, timestamp: float) -> str:
        """Return a hex-encoded signature over (content, source, timestamp)."""
        signature = self._private_key.sign(_message(content, source, timestamp))
        return signature.hex()

    def verify(self, content: str, source: str, timestamp: float, signature_hex: str) -> bool:
        """Return True iff signature_hex is a valid signature for these fields."""
        if not signature_hex:
            return False
        try:
            raw_signature = bytes.fromhex(signature_hex)
        except ValueError:
            return False
        try:
            self.public_key.verify(raw_signature, _message(content, source, timestamp))
            return True
        except InvalidSignature:
            return False

    def public_key_hex(self) -> str:
        return self.public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
