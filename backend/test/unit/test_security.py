"""Unit tests needing no database or network -- the Phase 1 test gate's
unit layer (docs/19-BACKEND-SPRINT-PLAN-V2.md Phase 1)."""
from app.security.passwords import hash_password, verify_password
from app.security.tokens import generate_opaque_token, hash_token


def test_password_hash_and_verify_round_trip():
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True


def test_password_verify_rejects_wrong_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", hashed) is False


def test_password_verify_rejects_missing_hash():
    assert verify_password("anything", None) is False


def test_password_hashes_are_unique_per_call():
    # Argon2id includes a random salt -- identical inputs must not produce
    # identical hashes (otherwise rainbow-table/identical-password leakage
    # across accounts would be possible).
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


def test_opaque_tokens_are_unique_and_unguessable():
    tokens = {generate_opaque_token() for _ in range(1000)}
    assert len(tokens) == 1000  # no collisions across 1000 samples


def test_token_hash_is_deterministic_but_not_reversible():
    token = generate_opaque_token()
    h1 = hash_token(token)
    h2 = hash_token(token)
    assert h1 == h2  # same token always hashes the same way (lookup works)
    assert h1 != token  # the stored value is never the raw bearer token


def test_different_tokens_hash_differently():
    a = hash_token(generate_opaque_token())
    b = hash_token(generate_opaque_token())
    assert a != b
