"""Regression tests for retired/failed Bing free authentication."""

import pytest
import requests

from videocaptioner.core.translate.bing_translator import BingTranslator


class FakeResponse:
    def __init__(self, status_code: int, text: str = "token"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _translator(outcome) -> BingTranslator:
    translator = BingTranslator.__new__(BingTranslator)
    translator.session = FakeSession(outcome)
    translator.auth_endpoint = "https://edge.microsoft.com/translate/auth"
    translator.timeout = 20
    translator.headers = {}
    return translator


def test_retired_404_has_actionable_google_or_llm_fallback() -> None:
    translator = _translator(FakeResponse(404))
    with pytest.raises(RuntimeError, match=r"retired \(HTTP 404\).*Google or LLM"):
        translator._init_session()


def test_transport_failure_is_sanitized() -> None:
    translator = _translator(requests.ConnectionError("secret endpoint detail"))
    with pytest.raises(RuntimeError, match="unavailable.*Google or LLM") as exc_info:
        translator._init_session()
    assert "secret endpoint detail" not in str(exc_info.value)


def test_success_still_populates_bearer_header() -> None:
    translator = _translator(FakeResponse(200, "abc-token"))
    translator._init_session()
    assert translator.auth_token == "abc-token"
    assert translator.headers["authorization"] == "Bearer abc-token"
