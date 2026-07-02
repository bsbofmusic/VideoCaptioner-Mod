"""Unified LLM client for the application."""

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx
import openai
from openai import OpenAI
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from videocaptioner.core.utils.cache import get_llm_cache, memoize
from videocaptioner.core.utils.logger import setup_logger

from .request_logger import create_logging_http_client, log_llm_response

_global_client: Optional[OpenAI] = None
_client_config: Optional[tuple[str, str]] = None
_client_lock = threading.Lock()

logger = setup_logger("llm_client")
LLM_REQUEST_TIMEOUT = 90


@dataclass
class _ChatMessage:
    content: str


@dataclass
class _ChatChoice:
    message: _ChatMessage


@dataclass
class _ChatResponse:
    choices: List[_ChatChoice]


def normalize_base_url(base_url: str) -> str:
    """Normalize API base URL by ensuring /v1 suffix when needed."""
    url = base_url.strip()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    if not path:
        path = "/v1"

    normalized = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return normalized


def get_llm_client() -> OpenAI:
    """Get global LLM client instance (thread-safe singleton)."""
    global _global_client, _client_config

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    base_url = normalize_base_url(base_url)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not base_url or not api_key:
        raise ValueError(
            "OPENAI_BASE_URL and OPENAI_API_KEY environment variables must be set"
        )

    config = (base_url, api_key)
    if _global_client is None or _client_config != config:
        with _client_lock:
            if _global_client is None or _client_config != config:
                _global_client = OpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    http_client=create_logging_http_client(),
                )
                _client_config = config

    return _global_client


def before_sleep_log(retry_state: RetryCallState) -> None:
    logger.warning(
        "Rate Limit Error, sleeping and retrying... Please lower your thread concurrency or use better OpenAI API."
    )


@retry(
    stop=stop_after_attempt(10),
    wait=wait_random_exponential(multiplier=1, min=5, max=60),
    retry=retry_if_exception_type(openai.RateLimitError),
    before_sleep=before_sleep_log,
)
def _call_llm_api(
    messages: List[dict],
    model: str,
    temperature: float = 1,
    **kwargs: Any,
) -> Any:
    """实际调用 LLM API（带重试）"""
    kwargs.setdefault("timeout", LLM_REQUEST_TIMEOUT)

    if _is_anthropic_provider():
        return _call_anthropic_messages(messages, model, temperature, **kwargs)

    client = get_llm_client()

    if _is_codex_provider():
        response = _call_codex_responses(client, messages, model, temperature, **kwargs)
        log_llm_response(response)
        return _responses_to_chat_response(response)

    response = client.chat.completions.create(
        model=model,
        messages=messages,  # pyright: ignore[reportArgumentType]
        temperature=temperature,
        **kwargs,
    )

    log_llm_response(response)
    return response


def _is_codex_provider() -> bool:
    return os.getenv("LLM_PROVIDER", "").strip().upper() == "CODEX"


def _is_anthropic_provider() -> bool:
    return os.getenv("LLM_PROVIDER", "").strip().upper() == "ANTHROPIC"


def _messages_to_responses_input(messages: List[dict]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _call_codex_responses(
    client: OpenAI,
    messages: List[dict],
    model: str,
    temperature: float = 1,
    **kwargs: Any,
) -> Any:
    """Call Codex via Responses API only. No chat-completions fallback."""
    kwargs = dict(kwargs)
    kwargs.pop("stream", None)
    return client.responses.create(
        model=model,
        input=_messages_to_responses_input(messages),
        temperature=temperature,
        stream=False,
        **kwargs,
    )


def _call_anthropic_messages(
    messages: List[dict],
    model: str,
    temperature: float = 1,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> _ChatResponse:
    """Call Anthropic-compatible Messages API and normalize to chat response."""
    request_timeout = kwargs.pop("timeout", LLM_REQUEST_TIMEOUT)
    max_tokens = kwargs.pop("max_tokens", 4096)
    base_url = (base_url or os.getenv("OPENAI_BASE_URL", "")).strip().rstrip("/")
    api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()

    if not base_url or not api_key:
        raise ValueError("Anthropic Base URL and API Key must be set")

    system_parts: list[str] = []
    anthropic_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        else:
            anthropic_messages.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": content,
                }
            )

    payload: dict[str, Any] = {
        "model": model,
        "messages": anthropic_messages or [{"role": "user", "content": "Hello"}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    start_time = time.time()
    logger.info("Anthropic request start: model=%s, timeout=%ss", model, request_timeout)
    try:
        timeout = httpx.Timeout(float(request_timeout), connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/messages", headers=headers, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Anthropic API error {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Anthropic API timeout after {request_timeout}s") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Anthropic API connection error: {exc}") from exc
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Anthropic request finished: model=%s, duration_ms=%s",
            model,
            duration_ms,
        )

    return _anthropic_to_chat_response(data)


def _anthropic_to_chat_response(response_data: dict) -> _ChatResponse:
    parts: list[str] = []
    for block in response_data.get("content") or []:
        if isinstance(block, dict):
            text = block.get("text")
            if text:
                parts.append(str(text))

    content = "".join(parts)
    if not content:
        raise ValueError("Invalid Anthropic API response: empty content")

    return _ChatResponse(choices=[_ChatChoice(message=_ChatMessage(content=content))])


def _responses_to_chat_response(response: Any) -> _ChatResponse:
    content = getattr(response, "output_text", None)
    if not content:
        output = getattr(response, "output", None) or []
        parts: list[str] = []
        for item in output:
            for content_item in getattr(item, "content", None) or []:
                text = getattr(content_item, "text", None)
                if text:
                    parts.append(str(text))
        content = "".join(parts)

    if not content:
        raise ValueError("Invalid Codex Responses API response: empty output_text")

    return _ChatResponse(choices=[_ChatChoice(message=_ChatMessage(content=content))])


@memoize(get_llm_cache(), expire=3600, typed=True)
def call_llm(
    messages: List[dict],
    model: str,
    temperature: float = 1,
    **kwargs: Any,
) -> Any:
    """Call LLM API with automatic caching."""
    response = _call_llm_api(messages, model, temperature, **kwargs)

    if not (
        response
        and hasattr(response, "choices")
        and response.choices
        and len(response.choices) > 0
        and hasattr(response.choices[0], "message")
        and response.choices[0].message.content
    ):
        raise ValueError("Invalid OpenAI API response: empty choices or content")

    return response
