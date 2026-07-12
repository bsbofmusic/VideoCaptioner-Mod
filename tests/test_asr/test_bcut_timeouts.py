"""Unit tests for Bcut request timeout and response behavior."""

import json
from typing import Any, Callable

import httpx
import pytest

from videocaptioner.core.asr.bcut import (
    API_COMMIT_UPLOAD,
    API_CREATE_TASK,
    API_QUERY_RESULT,
    API_REQ_UPLOAD,
    POLLING_DEADLINE_SECONDS,
    REQUEST_TIMEOUT,
    UPLOAD_REQUEST_TIMEOUT,
    BcutASR,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any], *, headers: dict[str, str] | None = None):
        self._payload = payload
        self.headers = headers or {}
        self.raise_for_status_calls = 0

    def raise_for_status(self) -> None:
        self.raise_for_status_calls += 1

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    def __init__(
        self,
        handler: Callable[[str, str, dict[str, Any]], FakeResponse],
    ) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)


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


def _timeout_values(timeout: httpx.Timeout) -> tuple[float | None, ...]:
    return timeout.connect, timeout.read, timeout.write, timeout.pool


def test_init_creates_one_reusable_httpx_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(lambda _method, _url, _kwargs: FakeResponse({}))
    created: list[FakeClient] = []

    def fake_client_factory() -> FakeClient:
        created.append(client)
        return client

    monkeypatch.setattr(
        "videocaptioner.core.asr.bcut.BaseASR.__init__",
        lambda self, *args, **kwargs: None,
    )
    monkeypatch.setattr("videocaptioner.core.asr.bcut.httpx.Client", fake_client_factory)

    asr = BcutASR(b"audio")

    assert asr.client is client
    assert created == [client]


def test_timeout_contracts_cover_all_four_httpx_phases() -> None:
    assert isinstance(REQUEST_TIMEOUT, httpx.Timeout)
    assert isinstance(UPLOAD_REQUEST_TIMEOUT, httpx.Timeout)
    assert _timeout_values(REQUEST_TIMEOUT) == (10, 120, 120, 10)
    assert _timeout_values(UPLOAD_REQUEST_TIMEOUT) == (10, 120, 180, 10)
    assert POLLING_DEADLINE_SECONDS == 600


def test_bounded_timeout_preserves_normal_phase_budgets_when_they_fit() -> None:
    bounded = BcutASR._bounded_timeout(REQUEST_TIMEOUT, remaining=300)

    assert _timeout_values(bounded) == (10, 120, 120, 10)


@pytest.mark.parametrize("remaining", [100.0, 0.25, 1e-9])
def test_bounded_timeout_phase_sum_never_exceeds_remaining(remaining: float) -> None:
    bounded = BcutASR._bounded_timeout(REQUEST_TIMEOUT, remaining=remaining)
    phase_values = _timeout_values(bounded)

    assert all(value is not None and value > 0 for value in phase_values)
    assert sum(value for value in phase_values if value is not None) <= remaining + 1e-12


def test_upload_uses_client_and_request_and_multipart_timeouts() -> None:
    def handler(method: str, url: str, _kwargs: dict[str, Any]) -> FakeResponse:
        if url == API_REQ_UPLOAD:
            assert method == "POST"
            return FakeResponse(
                {
                    "data": {
                        "in_boss_key": "boss-key",
                        "resource_id": "resource-id",
                        "upload_id": "upload-id",
                        "upload_urls": ["https://upload.test/part-1", "https://upload.test/part-2"],
                        "per_size": 4,
                    }
                }
            )
        if url == API_COMMIT_UPLOAD:
            assert method == "POST"
            return FakeResponse({"data": {"download_url": "https://download.test/audio.mp3"}})
        if url.startswith("https://upload.test/part-"):
            assert method == "PUT"
            part_number = url.rsplit("-", maxsplit=1)[1]
            return FakeResponse({}, headers={"Etag": f"etag-{part_number}"})
        raise AssertionError(f"unexpected request: {method} {url}")

    client = FakeClient(handler)
    asr = _make_asr(client)

    asr.upload()

    assert [(method, url) for method, url, _kwargs in client.calls] == [
        ("POST", API_REQ_UPLOAD),
        ("PUT", "https://upload.test/part-1"),
        ("PUT", "https://upload.test/part-2"),
        ("POST", API_COMMIT_UPLOAD),
    ]
    assert client.calls[0][2]["timeout"] is REQUEST_TIMEOUT
    assert client.calls[1][2]["timeout"] is UPLOAD_REQUEST_TIMEOUT
    assert client.calls[2][2]["timeout"] is UPLOAD_REQUEST_TIMEOUT
    assert client.calls[3][2]["timeout"] is REQUEST_TIMEOUT
    assert [kwargs["data"] for _method, _url, kwargs in client.calls[1:3]] == [
        b"abcd",
        b"efgh",
    ]

    completion_payload = json.loads(client.calls[3][2]["data"])
    assert completion_payload["Etags"] == "etag-1,etag-2"
    assert asr._BcutASR__download_url == "https://download.test/audio.mp3"


def test_create_task_uses_client_and_request_timeout_and_returns_task_id() -> None:
    client = FakeClient(
        lambda _method, _url, _kwargs: FakeResponse({"data": {"task_id": "task-123"}})
    )
    asr = _make_asr(client)
    asr._BcutASR__download_url = "https://download.test/audio.mp3"

    assert asr.create_task() == "task-123"
    assert asr.task_id == "task-123"
    assert client.calls == [
        (
            "POST",
            API_CREATE_TASK,
            {
                "json": {"resource": "https://download.test/audio.mp3", "model_id": "8"},
                "headers": asr.headers,
                "timeout": REQUEST_TIMEOUT,
            },
        )
    ]


def test_result_polling_uses_client_and_request_timeout_and_returns_data() -> None:
    expected = {"state": 4, "result": "{}"}
    client = FakeClient(lambda _method, _url, _kwargs: FakeResponse({"data": expected}))
    asr = _make_asr(client)
    asr.task_id = "stored-task"

    assert asr.result() == expected
    assert client.calls == [
        (
            "GET",
            API_QUERY_RESULT,
            {
                "params": {"model_id": 7, "task_id": "stored-task"},
                "headers": asr.headers,
                "timeout": REQUEST_TIMEOUT,
            },
        )
    ]


def test_timeout_failure_is_clear_and_does_not_echo_transport_details() -> None:
    secret_detail = "https://upload.test/part?credential=do-not-leak"

    def handler(_method: str, _url: str, _kwargs: dict[str, Any]) -> FakeResponse:
        raise httpx.ReadTimeout(secret_detail)

    asr = _make_asr(FakeClient(handler))

    with pytest.raises(RuntimeError, match="Bcut result request timed out") as exc_info:
        asr.result("task-123")

    assert "credential" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def _prepare_run(asr: BcutASR, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asr, "_check_rate_limit", lambda: None)
    monkeypatch.setattr(asr, "upload", lambda: None)
    monkeypatch.setattr(asr, "create_task", lambda: "task-123")


def test_run_preserves_successful_polling_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    asr = _make_asr(FakeClient(lambda _method, _url, _kwargs: FakeResponse({})))
    _prepare_run(asr, monkeypatch)
    responses = iter(
        [
            {"state": 1, "result": ""},
            {"state": 4, "result": '{"utterances": []}'},
        ]
    )
    result_timeouts: list[httpx.Timeout] = []
    sleeps: list[float] = []
    monotonic_values = iter([100.0, 100.0, 100.2, 101.0, 101.1])

    def fake_result(
        task_id: str | None = None,
        *,
        timeout: httpx.Timeout = REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        assert task_id is None
        result_timeouts.append(timeout)
        return next(responses)

    monkeypatch.setattr(asr, "result", fake_result)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleeps.append)

    assert asr._run() == {"utterances": []}
    assert len(result_timeouts) == 2
    assert all(_timeout_values(timeout) == (10, 120, 120, 10) for timeout in result_timeouts)
    assert sleeps == [1]


def test_run_stops_at_monotonic_deadline_and_caps_request_and_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asr = _make_asr(FakeClient(lambda _method, _url, _kwargs: FakeResponse({})))
    _prepare_run(asr, monkeypatch)
    result_timeouts: list[httpx.Timeout] = []
    sleeps: list[float] = []
    monotonic_values = iter(
        [
            0.0,
            POLLING_DEADLINE_SECONDS - 0.25,
            POLLING_DEADLINE_SECONDS - 0.1,
            POLLING_DEADLINE_SECONDS,
        ]
    )

    def pending_result(
        task_id: str | None = None,
        *,
        timeout: httpx.Timeout = REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        assert task_id is None
        result_timeouts.append(timeout)
        return {"state": 1, "result": ""}

    monkeypatch.setattr(asr, "result", pending_result)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="Bcut ASR polling exceeded the 600-second deadline"):
        asr._run()

    assert len(result_timeouts) == 1
    phase_values = _timeout_values(result_timeouts[0])
    assert all(value is not None and value > 0 for value in phase_values)
    assert sum(value for value in phase_values if value is not None) <= 0.25 + 1e-12
    assert sleeps == pytest.approx([0.1])


def test_run_rejects_result_that_arrives_after_hard_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asr = _make_asr(FakeClient(lambda _method, _url, _kwargs: FakeResponse({})))
    _prepare_run(asr, monkeypatch)
    result_timeouts: list[httpx.Timeout] = []
    monotonic_values = iter([0.0, POLLING_DEADLINE_SECONDS - 0.25, POLLING_DEADLINE_SECONDS])

    def completed_result(
        task_id: str | None = None,
        *,
        timeout: httpx.Timeout = REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        assert task_id is None
        result_timeouts.append(timeout)
        return {"state": 4, "result": '{"utterances": []}'}

    monkeypatch.setattr(asr, "result", completed_result)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.time.monotonic", lambda: next(monotonic_values))

    with pytest.raises(RuntimeError, match="Bcut ASR polling exceeded the 600-second deadline"):
        asr._run()

    assert len(result_timeouts) == 1
    phase_values = _timeout_values(result_timeouts[0])
    assert all(value is not None and value > 0 for value in phase_values)
    assert sum(value for value in phase_values if value is not None) <= 0.25 + 1e-12
