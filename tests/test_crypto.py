"""Tests for lagrange/crypto/signer.py — the Ed25519 provenance signer
that backs Node B's spoofing checks in crypto_node.py.
"""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from lagrange.crypto.signer import Signer


def test_valid_signature_verifies():
    signer = Signer()
    sig = signer.sign("hello world", "internal_system", 1234.5)
    assert signer.verify("hello world", "internal_system", 1234.5, sig) is True


def test_tampered_content_fails_verification():
    signer = Signer()
    sig = signer.sign("original content", "internal_system", 1234.5)
    assert signer.verify("tampered content", "internal_system", 1234.5, sig) is False


def test_tampered_source_fails_verification():
    signer = Signer()
    sig = signer.sign("some content", "internal_system", 1234.5)
    assert signer.verify("some content", "verified_user", 1234.5, sig) is False


def test_tampered_timestamp_fails_verification():
    signer = Signer()
    sig = signer.sign("some content", "internal_system", 1234.5)
    assert signer.verify("some content", "internal_system", 9999.9, sig) is False


def test_signature_from_a_different_key_fails_verification():
    signer_a = Signer()
    signer_b = Signer()
    sig = signer_a.sign("content", "internal_system", 1.0)
    assert signer_b.verify("content", "internal_system", 1.0, sig) is False


def test_empty_signature_is_rejected():
    signer = Signer()
    assert signer.verify("content", "internal_system", 1.0, "") is False


def test_malformed_hex_signature_is_rejected_not_raised():
    signer = Signer()
    assert signer.verify("content", "internal_system", 1.0, "not-hex-at-all") is False


def test_public_key_hex_is_stable_and_matches_public_key_object():
    signer = Signer()
    expected = signer.public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    assert signer.public_key_hex() == expected


# ---------------------------------------------------------------------
# Key persistence — a Signer's keypair must survive across processes,
# otherwise internal_system memories signed before a restart can never
# be verified after it.
# ---------------------------------------------------------------------


def test_saved_key_round_trips_and_verifies_old_signatures(tmp_path):
    path = tmp_path / "signing_key.pem"
    original = Signer()
    sig = original.sign("deploy target is prod-1", "internal_system", 1000.0)
    original.save(path)

    reloaded = Signer.load(path)

    # the whole point: a signature made before "restart" still verifies
    assert reloaded.verify("deploy target is prod-1", "internal_system", 1000.0, sig) is True
    assert reloaded.public_key_hex() == original.public_key_hex()


def test_load_or_create_generates_once_then_reuses(tmp_path):
    path = tmp_path / "nested" / "signing_key.pem"

    first = Signer.load_or_create(path)
    assert path.exists()  # created, including the parent directory

    second = Signer.load_or_create(path)
    assert second.public_key_hex() == first.public_key_hex()  # reused, not regenerated


def test_save_refuses_to_overwrite_an_existing_key_by_default(tmp_path):
    path = tmp_path / "signing_key.pem"
    Signer().save(path)

    with pytest.raises(FileExistsError):
        Signer().save(path)

    Signer().save(path, overwrite=True)  # explicit opt-in is allowed


def test_load_rejects_a_file_that_is_not_an_ed25519_key(tmp_path):
    path = tmp_path / "not_a_key.pem"
    path.write_text("this is not a private key")

    with pytest.raises(ValueError):
        Signer.load(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_saved_key_file_is_not_group_or_world_readable(tmp_path):
    path = tmp_path / "signing_key.pem"
    Signer().save(path)

    assert path.stat().st_mode & 0o077 == 0
