import json
import time
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

# The legacy 500 x 1-second polling loop intended an approximately 500-second wait.
# Use a ten-minute wall-clock cap so slow requests cannot stretch polling into hours.
POLLING_DEADLINE_SECONDS = 600.0
POLLING_INTERVAL_SECONDS = 1.0


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
        **kwargs: Any,
    ) -> httpx.Response:
        """Send one Bcut request and redact transport details from timeout failures."""
        try:
            response = self.client.request(method, url, timeout=timeout, **kwargs)
        except httpx.TimeoutException:
            raise RuntimeError(f"Bcut {operation} request timed out") from None
        response.raise_for_status()
        return response

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
                "model_id": "8",
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
                "model_id": "8",
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
            json={"resource": self.__download_url, "model_id": "8"},
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
    ):
        """Query ASR result."""
        resp = self._request(
            "GET",
            API_QUERY_RESULT,
            params={"model_id": 7, "task_id": task_id or self.task_id},
            headers=self.headers,
            timeout=timeout,
            operation="result",
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

        # Poll against a wall-clock deadline so slow requests cannot extend the wait indefinitely.
        deadline = time.monotonic() + POLLING_DEADLINE_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Bcut ASR polling exceeded the {POLLING_DEADLINE_SECONDS:g}-second deadline"
                )

            task_resp = self.result(
                timeout=self._bounded_timeout(REQUEST_TIMEOUT, remaining)
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Bcut ASR polling exceeded the {POLLING_DEADLINE_SECONDS:g}-second deadline"
                )
            if task_resp["state"] == 4:
                break
            time.sleep(min(POLLING_INTERVAL_SECONDS, remaining))

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
