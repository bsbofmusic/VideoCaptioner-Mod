"""Unit tests for Bcut request timeout and response behavior."""

import json
from typing import Any

import pytest

from videocaptioner.core.asr.bcut import (
    API_COMMIT_UPLOAD,
    API_CREATE_TASK,
    API_QUERY_RESULT,
    API_REQ_UPLOAD,
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


def _make_asr() -> BcutASR:
    asr = BcutASR.__new__(BcutASR)
    asr.file_binary = b"abcdefgh"
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


def test_timeout_constants_are_stable() -> None:
    assert REQUEST_TIMEOUT == (10, 120)
    assert UPLOAD_REQUEST_TIMEOUT == (10, 180)


def test_upload_uses_request_and_multipart_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    asr = _make_asr()
    post_calls: list[tuple[str, dict[str, Any]]] = []
    put_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        post_calls.append((url, kwargs))
        if url == API_REQ_UPLOAD:
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
            return FakeResponse({"data": {"download_url": "https://download.test/audio.mp3"}})
        raise AssertionError(f"unexpected POST URL: {url}")

    def fake_put(url: str, **kwargs: Any) -> FakeResponse:
        put_calls.append((url, kwargs))
        return FakeResponse({}, headers={"Etag": f"etag-{len(put_calls)}"})

    monkeypatch.setattr("videocaptioner.core.asr.bcut.requests.post", fake_post)
    monkeypatch.setattr("videocaptioner.core.asr.bcut.requests.put", fake_put)

    asr.upload()

    assert [url for url, _kwargs in post_calls] == [API_REQ_UPLOAD, API_COMMIT_UPLOAD]
    assert all(kwargs["timeout"] == REQUEST_TIMEOUT for _url, kwargs in post_calls)
    assert [url for url, _kwargs in put_calls] == [
        "https://upload.test/part-1",
        "https://upload.test/part-2",
    ]
    assert all(kwargs["timeout"] == UPLOAD_REQUEST_TIMEOUT for _url, kwargs in put_calls)
    assert [kwargs["data"] for _url, kwargs in put_calls] == [b"abcd", b"efgh"]

    completion_payload = json.loads(post_calls[1][1]["data"])
    assert completion_payload["Etags"] == "etag-1,etag-2"
    assert asr._BcutASR__download_url == "https://download.test/audio.mp3"


def test_create_task_uses_request_timeout_and_returns_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asr = _make_asr()
    asr._BcutASR__download_url = "https://download.test/audio.mp3"
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        calls.append((url, kwargs))
        return FakeResponse({"data": {"task_id": "task-123"}})

    monkeypatch.setattr("videocaptioner.core.asr.bcut.requests.post", fake_post)

    assert asr.create_task() == "task-123"
    assert asr.task_id == "task-123"
    assert calls == [
        (
            API_CREATE_TASK,
            {
                "json": {"resource": "https://download.test/audio.mp3", "model_id": "8"},
                "headers": asr.headers,
                "timeout": REQUEST_TIMEOUT,
            },
        )
    ]


def test_result_polling_uses_request_timeout_and_returns_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asr = _make_asr()
    asr.task_id = "stored-task"
    calls: list[tuple[str, dict[str, Any]]] = []
    expected = {"state": 4, "result": "{}"}

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append((url, kwargs))
        return FakeResponse({"data": expected})

    monkeypatch.setattr("videocaptioner.core.asr.bcut.requests.get", fake_get)

    assert asr.result() == expected
    assert calls == [
        (
            API_QUERY_RESULT,
            {
                "params": {"model_id": 7, "task_id": "stored-task"},
                "headers": asr.headers,
                "timeout": REQUEST_TIMEOUT,
            },
        )
    ]
