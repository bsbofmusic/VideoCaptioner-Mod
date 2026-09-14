import json
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, List, Optional, Union

import httpx

from .asr_data import ASRDataSeg
from .base import BaseASR
from .status import ASRStatus

__version__ = "0.0.3"

API_BASE_URL = "https://member.bilibili.com/x/bcut/rubick-interface"
API_REQ_UPLOAD = API_BASE_URL + "/resource/create"
API_COMMIT_UPLOAD = API_BASE_URL + "/resource/create/complete"
API_CREATE_TASK = API_BASE_URL + "/task"
API_QUERY_RESULT = API_BASE_URL + "/task/result"

REQUEST_TIMEOUT = httpx.Timeout(connect=10, read=120, write=120, pool=10)
UPLOAD_REQUEST_TIMEOUT = httpx.Timeout(connect=10, read=120, write=180, pool=10)

# Keep long-running successful jobs bounded, while making throttling/network failures fail fast.
POLLING_DEADLINE_SECONDS = 600.0
POLLING_INTERVAL_SECONDS = 1.0
TRANSIENT_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 5.0, 10.0)
THROTTLE_RETRY_BACKOFF_SECONDS = (2.0, 5.0)
MAX_RETRY_AFTER_SECONDS = 15.0
MAX_TRANSIENT_RESULT_RETRIES = len(TRANSIENT_RETRY_BACKOFF_SECONDS)
MAX_THROTTLE_RESULT_RETRIES = len(THROTTLE_RETRY_BACKOFF_SECONDS)
TRANSIENT_RESULT_STATUS_CODES = frozenset({500, 502, 503, 504})
THROTTLE_RESULT_STATUS_CODES = frozenset({412, 429})
BCUT_TASK_MODEL_ID = "8"
BCUT_RESULT_MODEL_ID = 7

logger = logging.getLogger(__name__)


class BcutASR(BaseASR):
    """Bilibili Bcut ASR API implementation.

    Uses Bilibili's cloud ASR service with multipart upload support.
    """

    headers = {
        "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
        "Content-Type": "application/json",
    }

    def __init__(
        self,
        audio_input: Union[str, bytes],
        use_cache: bool = True,
        need_word_time_stamp: bool = False,
    ):
        super().__init__(audio_input, use_cache=use_cache)
        self.client = httpx.Client()
        self.task_id: Optional[str] = None
        self.__etags: List[str] = []

        self.__in_boss_key: Optional[str] = None
        self.__resource_id: Optional[str] = None
        self.__upload_id: Optional[str] = None
        self.__upload_urls: List[str] = []
        self.__per_size: Optional[int] = None
        self.__clips: Optional[int] = None

        self.__etags_final: Optional[List[str]] = []
        self.__download_url: Optional[str] = None

        self.need_word_time_stamp = need_word_time_stamp

    @staticmethod
    def _bounded_timeout(timeout: httpx.Timeout, remaining: float) -> httpx.Timeout:
        """Fit all timeout phases within the remaining polling deadline."""
        if remaining <= 0:
            raise ValueError("remaining timeout budget must be positive")

        phase_values = [
            remaining if value is None or value <= 0 else float(value)
            for value in (timeout.connect, timeout.read, timeout.write, timeout.pool)
        ]
        total = sum(phase_values)
        if total > remaining:
            scale = remaining / total
            phase_values = [value * scale for value in phase_values]

        return httpx.Timeout(
            connect=phase_values[0],
            read=phase_values[1],
            write=phase_values[2],
            pool=phase_values[3],
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        timeout: httpx.Timeout,
        operation: str,
        retryable_transport: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send one Bcut request with bounded timeouts and sanitized failures."""
        request_error: Optional[RuntimeError] = None
        try:
            response = self.client.request(method, url, timeout=timeout, **kwargs)
        except httpx.TimeoutException:
            if retryable_transport:
                raise
            request_error = RuntimeError(f"Bcut {operation} request timed out")
        except httpx.TransportError:
            if retryable_transport:
                raise
            request_error = RuntimeError(
                f"Bcut {operation} request failed due to transport error"
            )
        else:
            http_error: Optional[httpx.HTTPStatusError] = None
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                safe_request = httpx.Request(method, "https://redacted.invalid/")
                retry_after = response.headers.get("Retry-After")
                safe_headers = {"Retry-After": retry_after} if retry_after else {}
                safe_response = httpx.Response(
                    response.status_code,
                    headers=safe_headers,
                    request=safe_request,
                )
                http_error = httpx.HTTPStatusError(
                    f"Bcut {operation} request failed with HTTP {response.status_code}",
                    request=safe_request,
                    response=safe_response,
                )
            if http_error is not None:
                raise http_error
            return response

        if request_error is not None:
            raise request_error
        raise RuntimeError(f"Bcut {operation} request failed")

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> Optional[float]:
        """Parse Retry-After and cap it so throttling cannot look like a hang."""
        retry_after = response.headers.get("Retry-After", "").strip()
        if not retry_after:
            return None

        if retry_after.isdigit() and retry_after.isascii():
            normalized = retry_after.lstrip("0") or "0"
            if len(normalized) > 6:
                return MAX_RETRY_AFTER_SECONDS
            return min(float(normalized), MAX_RETRY_AFTER_SECONDS)

        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (IndexError, TypeError, ValueError, OverflowError):
            return None
        if retry_at is None or retry_at.tzinfo is None:
            return None

        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return min(max(0.0, seconds), MAX_RETRY_AFTER_SECONDS)

    @staticmethod
    def _retry_delay(
        backoff: tuple[float, ...], attempt: int, retry_after: Optional[float]
    ) -> float:
        """Return the bounded delay for one retry attempt."""
        delay = backoff[min(attempt - 1, len(backoff) - 1)]
        if retry_after is not None:
            delay = max(delay, retry_after)
        return min(delay, MAX_RETRY_AFTER_SECONDS)

    def upload(self) -> None:
        """Request upload authorization and upload audio file."""
        if not self.file_binary:
            raise ValueError("No audio data to upload")
        payload = json.dumps(
            {
                "type": 2,
                "name": "audio.mp3",
                "size": len(self.file_binary),
                "ResourceFileType": "mp3",
                "model_id": BCUT_TASK_MODEL_ID,
            }
        )

        resp = self._request(
            "POST",
            API_REQ_UPLOAD,
            data=payload,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
            operation="upload authorization",
        )
        resp = resp.json()
        resp_data = resp["data"]

        self.__in_boss_key = resp_data["in_boss_key"]
        self.__resource_id = resp_data["resource_id"]
        self.__upload_id = resp_data["upload_id"]
        self.__upload_urls = resp_data["upload_urls"]
        self.__per_size = resp_data["per_size"]
        self.__clips = len(resp_data["upload_urls"])

        self.__upload_part()
        self.__commit_upload()

    def __upload_part(self) -> None:
        """Upload audio data in multiple parts."""
        if (
            self.__clips is None
            or self.__per_size is None
            or self.__upload_urls is None
            or self.file_binary is None
        ):
            raise ValueError("Upload parameters not initialized")

        for clip in range(self.__clips):
            start_range = clip * self.__per_size
            end_range = (clip + 1) * self.__per_size
            resp = self._request(
                "PUT",
                self.__upload_urls[clip],
                data=self.file_binary[start_range:end_range],
                headers=self.headers,
                timeout=UPLOAD_REQUEST_TIMEOUT,
                operation="multipart upload",
            )
            etag = resp.headers.get("Etag")
            if etag is not None:
                self.__etags.append(etag)

    def __commit_upload(self) -> None:
        """Commit the upload and get download URL."""
        data = json.dumps(
            {
                "InBossKey": self.__in_boss_key,
                "ResourceId": self.__resource_id,
                "Etags": ",".join(self.__etags) if self.__etags else "",
                "UploadId": self.__upload_id,
                "model_id": BCUT_TASK_MODEL_ID,
            }
        )
        resp = self._request(
            "POST",
            API_COMMIT_UPLOAD,
            data=data,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
            operation="upload commit",
        )
        resp = resp.json()
        self.__download_url = resp["data"]["download_url"]

    def create_task(self) -> str:
        """Create ASR task."""
        resp = self._request(
            "POST",
            API_CREATE_TASK,
            json={"resource": self.__download_url, "model_id": BCUT_TASK_MODEL_ID},
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
            operation="task creation",
        )
        resp = resp.json()
        self.task_id = resp["data"]["task_id"]
        return self.task_id or ""

    def result(
        self,
        task_id: Optional[str] = None,
        *,
        timeout: httpx.Timeout = REQUEST_TIMEOUT,
        _retry_transport: bool = False,
    ):
        """Query ASR result using Bcut's upstream result-model contract."""
        resp = self._request(
            "GET",
            API_QUERY_RESULT,
            params={"model_id": BCUT_RESULT_MODEL_ID, "task_id": task_id or self.task_id},
            headers=self.headers,
            timeout=timeout,
            operation="result",
            retryable_transport=_retry_transport,
        )
        resp = resp.json()
        return resp["data"]

    def _run(
        self, callback: Optional[Callable[[int, str], None]] = None, **kwargs: Any
    ) -> dict:
        """Execute ASR workflow: upload -> create task -> poll result."""

        self._check_rate_limit()

        def _default_callback(x, y):
            pass

        if callback is None:
            callback = _default_callback

        callback(*ASRStatus.UPLOADING.callback_tuple())
        self.upload()

        callback(*ASRStatus.CREATING_TASK.callback_tuple())
        self.create_task()

        callback(*ASRStatus.TRANSCRIBING.callback_tuple())

        # Successful jobs may take time, but repeated network/throttle failures get only a
        # short bounded retry budget so they cannot masquerade as a ten-minute hang.
        deadline = time.monotonic() + POLLING_DEADLINE_SECONDS
        transient_attempt = 0
        throttle_attempt = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Bcut ASR polling exceeded the {POLLING_DEADLINE_SECONDS:g}-second deadline"
                )

            retry_after: Optional[float] = None
            try:
                task_resp = self.result(
                    timeout=self._bounded_timeout(REQUEST_TIMEOUT, remaining),
                    _retry_transport=True,
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retry_after = self._retry_after_seconds(exc.response)
                if status in THROTTLE_RESULT_STATUS_CODES:
                    throttle_attempt += 1
                    transient_attempt = 0
                    if throttle_attempt > MAX_THROTTLE_RESULT_RETRIES:
                        raise RuntimeError(
                            f"Bcut upstream throttled result polling with HTTP {status}"
                        ) from None
                    retry_kind = "throttle"
                    retry_attempt = throttle_attempt
                    retry_backoff = THROTTLE_RETRY_BACKOFF_SECONDS
                elif status in TRANSIENT_RESULT_STATUS_CODES:
                    transient_attempt += 1
                    throttle_attempt = 0
                    if transient_attempt > MAX_TRANSIENT_RESULT_RETRIES:
                        raise RuntimeError(
                            f"Bcut upstream result polling repeatedly failed with HTTP {status}"
                        ) from None
                    retry_kind = "transient"
                    retry_attempt = transient_attempt
                    retry_backoff = TRANSIENT_RETRY_BACKOFF_SECONDS
                else:
                    raise
            except httpx.TimeoutException:
                status = "timeout"
                transient_attempt += 1
                throttle_attempt = 0
                if transient_attempt > MAX_TRANSIENT_RESULT_RETRIES:
                    raise RuntimeError(
                        "Bcut upstream result polling repeatedly timed out"
                    ) from None
                retry_kind = "transient"
                retry_attempt = transient_attempt
                retry_backoff = TRANSIENT_RETRY_BACKOFF_SECONDS
            except httpx.TransportError:
                status = "transport"
                transient_attempt += 1
                throttle_attempt = 0
                if transient_attempt > MAX_TRANSIENT_RESULT_RETRIES:
                    raise RuntimeError(
                        "Bcut upstream result polling repeatedly hit transport errors"
                    ) from None
                retry_kind = "transient"
                retry_attempt = transient_attempt
                retry_backoff = TRANSIENT_RETRY_BACKOFF_SECONDS
            else:
                transient_attempt = 0
                throttle_attempt = 0
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"Bcut ASR polling exceeded the {POLLING_DEADLINE_SECONDS:g}-second deadline"
                    )
                if task_resp["state"] == 4:
                    break
                time.sleep(min(POLLING_INTERVAL_SECONDS, remaining))
                continue

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Bcut ASR polling exceeded the {POLLING_DEADLINE_SECONDS:g}-second deadline"
                )
            delay = min(
                self._retry_delay(retry_backoff, retry_attempt, retry_after),
                remaining,
            )
            logger.warning(
                "Bcut result retry kind=%s status=%s attempt=%d delay=%g",
                retry_kind,
                status,
                retry_attempt,
                delay,
            )
            time.sleep(delay)

        callback(*ASRStatus.COMPLETED.callback_tuple())
        return json.loads(task_resp["result"])

    def _make_segments(self, resp_data: dict) -> List[ASRDataSeg]:
        if self.need_word_time_stamp:
            return [
                ASRDataSeg(w["label"].strip(), w["start_time"], w["end_time"])
                for u in resp_data["utterances"]
                for w in u["words"]
            ]
        else:
            return [
                ASRDataSeg(u["transcript"], u["start_time"], u["end_time"])
                for u in resp_data["utterances"]
            ]


if __name__ == "__main__":
    # Example usage
    audio_file = r"test.mp3"
    asr = BcutASR(audio_file)
    asr_data = asr.run()
    print(asr_data)
