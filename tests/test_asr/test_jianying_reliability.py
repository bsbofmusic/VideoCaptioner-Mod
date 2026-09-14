"""Failure-path tests for JianYing's upstream signing dependency."""

import pytest
import requests

from videocaptioner.core.asr.jianying import (
    MAX_SIGN_RETRY_AFTER_SECONDS,
    SIGN_RETRY_BACKOFF_SECONDS,
    SIGN_SERVICE_TIMEOUT,
    JianYingASR,
)


def _asr() -> JianYingASR:
    asr = JianYingASR.__new__(JianYingASR)
    asr.tdid = "3943278516897751"
    return asr


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_sign_success_uses_bounded_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"sign": "ABCDEF"})

    monkeypatch.setattr("videocaptioner.core.asr.jianying.requests.post", post)
    sign, timestamp = _asr()._generate_sign_parameters("/lv/v1/upload_sign")

    assert sign == "abcdef"
    assert timestamp.isdigit()
    assert calls[0][1]["timeout"] == SIGN_SERVICE_TIMEOUT


def test_persistent_429_retries_short_then_fails_with_bcut_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    sleeps = []

    def post(*_args, **_kwargs):
        calls.append(1)
        return FakeResponse(429)

    monkeypatch.setattr("videocaptioner.core.asr.jianying.requests.post", post)
    monkeypatch.setattr("videocaptioner.core.asr.jianying.time.sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="throttled with HTTP 429.*use Bcut"):
        _asr()._generate_sign_parameters("/lv/v1/upload_sign")

    assert sleeps == list(SIGN_RETRY_BACKOFF_SECONDS)
    assert len(calls) == len(SIGN_RETRY_BACKOFF_SECONDS) + 1


def test_retry_after_is_honored_but_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = iter(
        [
            FakeResponse(429, headers={"Retry-After": "999999999999999999"}),
            FakeResponse(200, {"sign": "OK"}),
        ]
    )
    sleeps = []
    monkeypatch.setattr(
        "videocaptioner.core.asr.jianying.requests.post",
        lambda *_args, **_kwargs: next(outcomes),
    )
    monkeypatch.setattr("videocaptioner.core.asr.jianying.time.sleep", sleeps.append)

    sign, _ = _asr()._generate_sign_parameters("/lv/v1/upload_sign")
    assert sign == "ok"
    assert sleeps == [MAX_SIGN_RETRY_AFTER_SECONDS]


@pytest.mark.parametrize("failure", [requests.Timeout("secret"), requests.ConnectionError("secret")])
def test_transport_errors_are_bounded_and_sanitized(
    failure: requests.RequestException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps = []
    monkeypatch.setattr(
        "videocaptioner.core.asr.jianying.requests.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr("videocaptioner.core.asr.jianying.time.sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="unavailable after bounded retries") as exc_info:
        _asr()._generate_sign_parameters("/lv/v1/upload_sign")

    assert "secret" not in str(exc_info.value)
    assert sleeps == list(SIGN_RETRY_BACKOFF_SECONDS)


def test_non_retryable_403_fails_once_without_endpoint_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def post(*_args, **_kwargs):
        calls.append(1)
        return FakeResponse(403)

    monkeypatch.setattr("videocaptioner.core.asr.jianying.requests.post", post)
    with pytest.raises(RuntimeError, match="rejected the request with HTTP 403") as exc_info:
        _asr()._generate_sign_parameters("/lv/v1/upload_sign")

    assert len(calls) == 1
    assert "asrtools-update" not in str(exc_info.value)
