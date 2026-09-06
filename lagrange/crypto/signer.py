"""Ed25519 key management and signing for internal_system provenance.

Only Lagrange's own trusted internal code holds the private key produced
here. A memory that *claims* `source="internal_system"` is only genuine
if it carries a signature this Signer's public key can verify — an
attacker who tricks an agent into mislabeling injected content as
internal_system still cannot forge that signature (see crypto_node.py
and CLAUDE.md's threat model: grey-box, no backend key access).

The keypair must persist across processes: a signature written before a
restart has to still verify after it. Use `Signer.load_or_create(path)`
for a long-lived deployment; a bare `Signer()` generates a throwaway key
and is only appropriate for tests and one-shot scripts.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
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

    # -- persistence --------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> Signer:
        """Load a Signer from an unencrypted PKCS#8 PEM private key file.

        Raises ValueError if the file is not a valid Ed25519 private key.
        """
        path = Path(path)
        try:
            key = load_pem_private_key(path.read_bytes(), password=None)
        except Exception as exc:  # noqa: BLE001 - normalize every parse failure
            raise ValueError(f"{path} is not a readable PEM private key: {exc}") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"{path} holds a {type(key).__name__}, not an Ed25519 private key")

        if os.name == "posix" and path.stat().st_mode & 0o077:
            warnings.warn(
                f"signing key {path} is group/world-accessible; run: chmod 600 {path}",
                stacklevel=2,
            )
        return cls(key)

    def save(self, path: str | Path, *, overwrite: bool = False) -> None:
        """Write the private key to `path` as unencrypted PKCS#8 PEM.

        The file is created with 0600 permissions. Refuses to clobber an
        existing file unless `overwrite=True`, so a stale path never
        silently rotates the key out from under already-signed memories.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pem = self._private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            raise FileExistsError(f"{path} already exists; pass overwrite=True to replace the signing key") from None
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        os.chmod(path, 0o600)  # tighten even if the file pre-existed with looser bits

    @classmethod
    def load_or_create(cls, path: str | Path) -> Signer:
        """Load the key at `path`, or generate one and save it if absent.

        The intended entry point for a long-lived deployment: first run
        creates the key, every run after that reuses it.
        """
        path = Path(path)
        if path.exists():
            return cls.load(path)
        signer = cls()
        signer.save(path)
        return signer

    # -- signing ----------------------------------------------------------

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
