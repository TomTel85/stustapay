"""Tests for stustapay.core.jwt decode hardening."""

import base64
from datetime import datetime, timezone

import pytest

from stustapay.core.jwt import InvalidTokenError, decode, encode


def test_decode_round_trip() -> None:
    payload = {"sub": "user-1", "exp": 9_999_999_999}
    token = encode(payload, key="secret", algorithm="HS256")
    assert decode(token, key="secret", algorithms=["HS256"]) == payload


def test_decode_rejects_non_object_header() -> None:
    # Header JSON is `[]` — valid JSON, not a JWT header object.
    header_b64 = "W10"  # "[]" without padding, url-safe
    payload = encode({"sub": "x", "exp": 9_999_999_999}, key="secret", algorithm="HS256")
    parts = payload.split(".")
    bad_token = f"{header_b64}.{parts[1]}.{parts[2]}"
    with pytest.raises(InvalidTokenError, match="Malformed JWT header"):
        decode(bad_token, key="secret", algorithms=["HS256"])


def test_decode_rejects_non_object_header_string() -> None:
    header_b64 = base64.urlsafe_b64encode(b'"HS256"').decode("ascii").rstrip("=")
    payload = encode({"sub": "x", "exp": 9_999_999_999}, key="secret", algorithm="HS256")
    parts = payload.split(".")
    bad_token = f"{header_b64}.{parts[1]}.{parts[2]}"
    with pytest.raises(InvalidTokenError, match="Malformed JWT header"):
        decode(bad_token, key="secret", algorithms=["HS256"])


@pytest.mark.parametrize("claim", ["exp", "nbf", "iat"])
@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"), "123"])
def test_decode_rejects_invalid_claim_times(claim: str, value: object) -> None:
    token = encode({claim: value}, key="secret", algorithm="HS256")
    with pytest.raises(InvalidTokenError, match="Invalid JWT claim type"):
        decode(token, key="secret", algorithms=["HS256"])


@pytest.mark.parametrize("segment", [0, 1, 2])
@pytest.mark.parametrize("invalid", ["!", "é", "a", "", "===="])
def test_decode_rejects_malformed_segments(segment: int, invalid: str) -> None:
    parts = encode({"sub": "user-1"}, key="secret", algorithm="HS256").split(".")
    parts[segment] = invalid
    with pytest.raises(InvalidTokenError):
        decode(".".join(parts), key="secret", algorithms=["HS256"])


def test_decode_rejects_deeply_nested_json() -> None:
    parts = encode({}, key="secret", algorithm="HS256").split(".")
    parts[1] = base64.urlsafe_b64encode(b"[" * 2000 + b"]" * 2000).decode("ascii").rstrip("=")
    with pytest.raises(InvalidTokenError):
        decode(".".join(parts), key="secret", algorithms=["HS256"])


def test_decode_rejects_oversized_token() -> None:
    with pytest.raises(InvalidTokenError):
        decode("a" * 16_385, key="secret", algorithms=["HS256"])


def test_decode_rejects_expiration_at_current_time(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDatetime:
        @staticmethod
        def now(tz):
            return datetime.fromtimestamp(1_000, tz=tz)

    monkeypatch.setattr("stustapay.core.jwt.datetime", FrozenDatetime)
    token = encode({"exp": datetime.fromtimestamp(1_000, tz=timezone.utc).timestamp()}, "secret", "HS256")
    with pytest.raises(InvalidTokenError, match="expired"):
        decode(token, "secret", ["HS256"])
