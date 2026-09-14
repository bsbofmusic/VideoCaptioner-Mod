"""Contract and failure-path tests for the Mod's Bcut hardening."""

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable, cast

import httpx
import pytest

from videocaptioner.core.asr.bcut import (
    API_COMMIT_UPLOAD,
    API_CREATE_TASK,
    API_QUERY_RESULT,
    API_REQ_UPLOAD,
    BCUT_RESULT_MODEL_ID,
    BCUT_TASK_MODEL_ID,
    MAX_RETRY_AFTER_SECONDS,
    POLLING_DEADLINE_SECONDS,
    REQUEST_TIMEOUT,
    THROTTLE_RETRY_BACKOFF_SECONDS,
    TRANSIENT_RETRY_BACKOFF_SECONDS,
    UPLOAD_REQUEST_TIMEOUT,
    BcutASR,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any], *, headers: dict[str, str] | None = None):
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    def __init__(self, handler: Callable[[str, str, dict[str, Any]], Any]) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)


def _http_response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> httpx.Response:
    request = httpx.Request("GET", "https://example.invalid/task/result?task_id=secret-task")
    return httpx.Response(
        status_code,
        headers=headers,
        json=payload,
        request=request,
    )


def _next_outcome(outcomes: list[Any]) -> Callable[[str, str, dict[str, Any]], Any]:
    iterator = iter(outcomes)

    def handler(_method: str, _url: str, _kwargs: dict[str, Any]) -> Any:
        outcome = next(iterator)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return handler


def _make_asr(client: FakeClient) -> BcutASR:
    asr = BcutASR.__new__(BcutASR)
    asr.file_binary = b"abcdefgh"
    asr.client = client
    asr.task_id = None
    asr.need_word_time_stamp = False
    asr._BcutASR__etags = []
    asr._BcutASR__in_boss_key = None
    asr._BcutASR__resource_id = None
    asr._BcutASR__upload_id = None
    asr._BcutASR__upload_urls = []
    asr._BcutASR__per_size = None
    asr._BcutASR__clips = None
    asr._BcutASR__etags_final = []
    asr._BcutASR__download_url = None
    return asr


def _prepare_run(asr: BcutASR, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asr, "_check_rate_limit", lambda: None)
    monkeypatch.setattr(asr, "upload", lambda: None)
    monkeypatch.setattr(asr, "create_task", lambda: "task-123")
    asr.task_id = "task-123"


def _timeout_values(timeout: httpx.Timeout) -> tuple[float | None, ...]:
    return timeout.connect, timeout.read, timeout.write, timeout.pool


def test_upstream_model_contract_is_locked_to_8887() -> None:
    assert BCUT_TASK_MODEL_ID == "8"
    assert BCUT_RESULT_MODEL_ID == 7


def test_timeout_contracts_cover_all_httpx_phases() -> None:
    assert _timeout_values(REQUEST_TIMEOUT) == (10, 120, 120, 10)
    assert _timeout_values(UPLOAD_REQUEST_TIMEOUT) == (10, 120, 180, 10)
    assert POLLING_DEADLINE_SECONDS == 600


def test_bounded_timeout_never_exceeds_remaining_budget() -> None:
    bounded = BcutASR._bounded_timeout(REQUEST_TIMEOUT, remaining=0.25)
    values = _timeout_values(bounded)
    assert all(value is not None and value > 0 for value in values)
    assert sum(value for value in values if value is not None) <= 0.25 + 1e-12


def test_upload_and_task_creation_keep_model_8_and_timeouts() -> None:
    def handler(method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        if url == API_REQ_UPLOAD:
            payload = json.loads(kwargs["data"])
            assert payload["model_id"] == "8"
            return FakeResponse(
                {
                    "data": {
                        "in_boss_key": "boss-key",
                        "resource_id": "resource-id",
                        "upload_id": "upload-id",
                        "upload_urls": ["https://upload.test/part-1"],
                        "per_size": 8,
                    }
                }
            )
        if url == "https://upload.test/part-1":
            return FakeResponse({}, headers={"Etag": "etag-1"})
        if url == API_COMMIT_UPLOAD:
            payload = json.loads(kwargs["data"])
            assert payload["model_id"] == "8"
            return FakeResponse({"data": {"download_url": "https://download.test/audio.mp3"}})
        if url == API_CREATE_TASK:
            assert kwargs["json"]["model_id"] == "8"
            return FakeResponse({"data": {"task_id": "task-123"}})
        raise AssertionError(f"unexpected request: {method} {url}")

    asr = _make_asr(FakeClient(handler))
    asr.upload()
    assert asr.create_task() == "task-123"
    calls = asr.client.calls
    assert calls[0][2]["timeout"] is REQUEST_TIMEOUT
    assert calls[1][2]["timeout"] is UPLOAD_REQUEST_TIMEOUT
    assert calls[2][2]["timeout"] is REQUEST_TIMEOUT
    assert calls[3][2]["timeout"] is REQUEST_TIMEOUT


def test_result_query_is_model_7_not_mod_008_model_8() -> None:
    expected = {"state": 4, "result": "{}"}
    client = FakeClient(lambda _method, _url, _kwargs: FakeResponse({"data": expected}))
    asr = _make_asr(client)
    asr.task_id = "stored-task"

    assert asr.result() == expected
    assert client.calls[0][1] == API_QUERY_RESULT
    assert client.calls[0][2]["params"] == {"model_id": 7, "task_id": "stored-task"}
    assert client.calls[0][2]["timeout"] is REQUEST_TIMEOUT


def test_request_timeout_and_transport_errors_are_sanitized() -> None:
    for failure, expected in [
        (httpx.ReadTimeout("credential=do-not-leak"), "timed out"),
        (httpx.ConnectError("credential=do-not-leak"), "transport error"),
    ]:
        def handler(_method: str, _url: str, _kwargs: dict[str, Any], err=failure) -> Any:
            raise err

        asr = _make_asr(FakeClient(handler))
        with pytest.raises(RuntimeError, match=expected) as exc_info:
            asr.result("secret-task")
        assert "credential" not in str(exc_info.value)
        assert "secret-task" not in str(exc_info.value)
        assert exc_info.value.__cause__ is None


def test_http_error_redacts_task_id_and_request_url() -> None:
    asr = _make_asr(FakeClient(lambda _method, _url, _kwargs: _http_response(403)))
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        asr.result("secret-task")
    error = exc_info.value
    assert "secret-task" not in str(error)
    assert "task/result?" not in str(error)
    assert "secret-task" not in str(error.request.url)
    assert "secret-task" not in str(error.response.request.url)


def test_retry_after_is_bounded_for_huge_integer_and_http_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    huge = _http_response(429, headers={"Retry-After": "9" * 4301})
    assert BcutASR._retry_after_seconds(huge) == MAX_RETRY_AFTER_SECONDS

    class FrozenDatetime:
        @staticmethod
        def now(tz: timezone) -> datetime:
            assert tz is timezone.utc
            return datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr("videocaptioner.core.asr.bcut.datetime", FrozenDatetime)
    dated = _http_response(
        429,
        headers={"Retry-After": "Mon, 14 Sep 2026 12:00:30 GMT"},
    )
    assert BcutASR._retry_after_seconds(dated) == MAX_RETRY_AFTER_SECONDS


@pytest.mark.parametrize("retry_after", ["１２", "١٢", "²", "garbage"])
def test_retry_after_rejects_invalid_values(retry_after: str) -> None:
    response = cast(httpx.Response, SimpleNamespace(headers={"Retry-After": retry_after}))
    assert BcutASR._retry_after_seconds(response) is None


@pytest.mark.parametrize("status", [412, 429])
def test_throttle_retries_are_short_and_then_fail_clearly(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeClient(lambda _method, _url, _kwargs: _http_response(status))
    asr = _make_asr(client)
    _prepare_run(asr, monkeypatch)
    clock = [0.0]
    sleeps: list[float] = []
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: clock[0])

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleep)

    with caplog.at_level(logging.WARNING, logger="videocaptioner.core.asr.bcut"):
        with pytest.raises(RuntimeError, match=f"upstream throttled.*HTTP {status}"):
            asr._run()

    assert sleeps == list(THROTTLE_RETRY_BACKOFF_SECONDS)
    assert len(client.calls) == len(THROTTLE_RETRY_BACKOFF_SECONDS) + 1
    assert clock[0] < 10
    assert "task-123" not in caplog.text
    assert all(call[2]["params"]["model_id"] == 7 for call in client.calls)


def test_retry_after_is_respected_but_capped_under_throttling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(
        lambda _method, _url, _kwargs: _http_response(429, headers={"Retry-After": "999999"})
    )
    asr = _make_asr(client)
    _prepare_run(asr, monkeypatch)
    clock = [0.0]
    sleeps: list[float] = []
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: clock[0])

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleep)
    with pytest.raises(RuntimeError, match="upstream throttled"):
        asr._run()
    assert sleeps == [MAX_RETRY_AFTER_SECONDS, MAX_RETRY_AFTER_SECONDS]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_transient_server_errors_use_bounded_retry_budget(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(lambda _method, _url, _kwargs: _http_response(status))
    asr = _make_asr(client)
    _prepare_run(asr, monkeypatch)
    clock = [0.0]
    sleeps: list[float] = []
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: clock[0])

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleep)
    with pytest.raises(RuntimeError, match=f"repeatedly failed with HTTP {status}"):
        asr._run()
    assert sleeps == list(TRANSIENT_RETRY_BACKOFF_SECONDS)
    assert len(client.calls) == len(TRANSIENT_RETRY_BACKOFF_SECONDS) + 1


@pytest.mark.parametrize(
    "failure,expected",
    [
        (httpx.ReadTimeout("credential=do-not-leak"), "repeatedly timed out"),
        (httpx.ConnectError("credential=do-not-leak"), "transport errors"),
    ],
)
def test_transient_transport_failures_are_bounded_and_do_not_leak(
    failure: httpx.TransportError,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeClient(lambda _method, _url, _kwargs: (_ for _ in ()).throw(failure))
    asr = _make_asr(client)
    _prepare_run(asr, monkeypatch)
    clock = [0.0]
    sleeps: list[float] = []
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: clock[0])

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleep)
    with caplog.at_level(logging.WARNING, logger="videocaptioner.core.asr.bcut"):
        with pytest.raises(RuntimeError, match=expected):
            asr._run()
    assert sleeps == list(TRANSIENT_RETRY_BACKOFF_SECONDS)
    assert "credential" not in caplog.text
    assert "task-123" not in caplog.text


def test_single_throttle_then_success_reuses_same_task_and_model_7(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(
        _next_outcome(
            [
                _http_response(412, headers={"Retry-After": "3"}),
                _http_response(
                    200,
                    payload={"data": {"state": 4, "result": '{"utterances": []}'}},
                ),
            ]
        )
    )
    asr = _make_asr(client)
    _prepare_run(asr, monkeypatch)
    clock = [0.0]
    sleeps: list[float] = []
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: clock[0])

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleep)
    assert asr._run() == {"utterances": []}
    assert sleeps == [3.0]
    assert len(client.calls) == 2
    assert all(
        kwargs["params"] == {"model_id": 7, "task_id": "task-123"}
        for _method, _url, kwargs in client.calls
    )


def test_successful_pending_polling_keeps_normal_one_second_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asr = _make_asr(FakeClient(lambda _method, _url, _kwargs: FakeResponse({})))
    _prepare_run(asr, monkeypatch)
    responses = iter(
        [
            {"state": 1, "result": ""},
            {"state": 4, "result": '{"utterances": []}'},
        ]
    )
    sleeps: list[float] = []
    clock = [100.0]

    def fake_result(
        task_id: str | None = None,
        *,
        timeout: httpx.Timeout = REQUEST_TIMEOUT,
        _retry_transport: bool = False,
    ) -> dict[str, Any]:
        assert task_id is None
        assert _retry_transport is True
        assert isinstance(timeout, httpx.Timeout)
        return next(responses)

    def monotonic() -> float:
        return clock[0]

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(asr, "result", fake_result)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", monotonic)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleep)
    assert asr._run() == {"utterances": []}
    assert sleeps == [1.0]


def test_hard_deadline_still_bounds_healthy_but_never_finishing_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asr = _make_asr(FakeClient(lambda _method, _url, _kwargs: FakeResponse({})))
    _prepare_run(asr, monkeypatch)
    clock = [0.0]

    def pending_result(
        task_id: str | None = None,
        *,
        timeout: httpx.Timeout = REQUEST_TIMEOUT,
        _retry_transport: bool = False,
    ) -> dict[str, Any]:
        assert _retry_transport is True
        clock[0] = POLLING_DEADLINE_SECONDS
        return {"state": 1, "result": ""}

    monkeypatch.setattr(asr, "result", pending_result)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: clock[0])
    with pytest.raises(RuntimeError, match="polling exceeded the 600-second deadline"):
        asr._run()
