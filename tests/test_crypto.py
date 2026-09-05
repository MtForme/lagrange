"""Tests for lagrange/crypto/signer.py — the Ed25519 provenance signer
that backs Node B's spoofing checks in crypto_node.py.
"""

from __future__ import annotations

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
