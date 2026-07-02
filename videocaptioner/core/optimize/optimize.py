"""字幕优化模块

使用 LLM 优化字幕内容，支持 agent loop 自动验证和进程隔离防卡死。
"""

import atexit
import difflib
import multiprocessing as mp
import re
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import json_repair

from ..asr.asr_data import ASRData, ASRDataSeg
from ..entities import SubtitleProcessData
from ..llm import call_llm
from ..prompts import get_prompt
from ..split.alignment import SubtitleAligner
from ..utils.cache import disable_cache, enable_cache, is_cache_enabled
from ..utils.logger import setup_logger
from ..utils.text_utils import count_words

logger = setup_logger("subtitle_optimizer")

OPTIMIZE_RETRY_MIN = 3
OPTIMIZE_RETRY_MAX = 50
OPTIMIZE_DEFAULT_RETRY_COUNT = 3
MAX_STEPS = OPTIMIZE_DEFAULT_RETRY_COUNT
OPTIMIZE_BATCH_TIMEOUT_SECONDS = 300
OPTIMIZE_POLL_INTERVAL_SECONDS = 0.5
OPTIMIZE_MAX_IN_FLIGHT_CAP = 20
OPTIMIZE_NO_PROGRESS_TIMEOUT_SECONDS = OPTIMIZE_BATCH_TIMEOUT_SECONDS


@dataclass
class _ProcessJob:
    chunk: Dict[str, str]
    process: mp.Process
    conn: Connection
    started_at: float


def _optimize_chunk_process(
    conn: Connection,
    subtitle_chunk: Dict[str, str],
    model: str,
    custom_prompt: str,
    timeout_seconds: int = 90,
    retry_count: int = OPTIMIZE_DEFAULT_RETRY_COUNT,
    cache_enabled: bool = True,
) -> None:
    """Optimize one batch in a child process so the parent can kill hard hangs."""
    try:
        if cache_enabled:
            enable_cache()
        else:
            disable_cache()

        optimizer = SubtitleOptimizer(
            thread_num=1,
            batch_num=max(len(subtitle_chunk), 1),
            model=model,
            custom_prompt=custom_prompt,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            update_callback=None,
        )
        result = optimizer.agent_loop(subtitle_chunk)
        conn.send(("ok", result, ""))
    except BaseException as exc:
        try:
            conn.send(("error", subtitle_chunk, f"{type(exc).__name__}: {exc}"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


class SubtitleOptimizer:
    """字幕优化器。"""

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        model: str,
        custom_prompt: str,
        update_callback: Optional[Callable] = None,
        timeout_seconds: int = 90,
        retry_count: int = OPTIMIZE_DEFAULT_RETRY_COUNT,
    ):
        self.thread_num = thread_num
        self.batch_num = batch_num
        self.model = model
        self.custom_prompt = custom_prompt
        self.timeout_seconds = max(1, int(timeout_seconds or 90))
        self.retry_count = min(
            OPTIMIZE_RETRY_MAX,
            max(OPTIMIZE_RETRY_MIN, int(retry_count or OPTIMIZE_DEFAULT_RETRY_COUNT)),
        )
        self.batch_timeout_seconds = max(
            OPTIMIZE_BATCH_TIMEOUT_SECONDS,
            self.timeout_seconds * self.retry_count + 30,
        )
        self.update_callback = update_callback

        self.is_running = True
        self._active_jobs: List[_ProcessJob] = []
        atexit.register(self.stop)

    def optimize_subtitle(self, subtitle_data: Union[str, ASRData]) -> ASRData:
        """优化字幕。"""
        try:
            if isinstance(subtitle_data, str):
                asr_data = ASRData.from_subtitle_file(subtitle_data)
            else:
                asr_data = subtitle_data

            subtitle_dict = {
                str(i): seg.text for i, seg in enumerate(asr_data.segments, 1)
            }
            chunks = self._split_chunks(subtitle_dict)
            optimized_dict = self._parallel_optimize(chunks)
            new_segments = self._create_segments(asr_data.segments, optimized_dict)
            return ASRData(new_segments)

        except Exception as exc:
            logger.error(f"Optimization failed: {str(exc)}")
            raise RuntimeError(f"Optimization failed: {str(exc)}") from exc

    def _split_chunks(self, subtitle_dict: Dict[str, str]) -> List[Dict[str, str]]:
        items = list(subtitle_dict.items())
        return [
            dict(items[i : i + self.batch_num])
            for i in range(0, len(items), self.batch_num)
        ]

    def _parallel_optimize(self, chunks: List[Dict[str, str]]) -> Dict[str, str]:
        optimized_dict: Dict[str, str] = {}
        if not chunks:
            return optimized_dict

        mp.freeze_support()
        ctx = mp.get_context("spawn")
        max_in_flight = min(
            max(1, self.thread_num),
            OPTIMIZE_MAX_IN_FLIGHT_CAP,
            len(chunks),
        )
        next_index = 0

        try:
            while self.is_running and (
                next_index < len(chunks) or self._active_jobs
            ):
                while (
                    self.is_running
                    and next_index < len(chunks)
                    and len(self._active_jobs) < max_in_flight
                ):
                    chunk = chunks[next_index]
                    self._active_jobs.append(self._start_process_job(ctx, chunk))
                    next_index += 1

                made_progress = False
                now = time.time()
                for job in list(self._active_jobs):
                    status, result, error_message = self._poll_process_job(job, now)
                    if status == "pending":
                        continue

                    made_progress = True
                    self._active_jobs.remove(job)
                    if status != "ok":
                        logger.error(
                            "Optimization batch %s failed, falling back to original: %s",
                            self._chunk_range(job.chunk),
                            error_message,
                        )
                    else:
                        logger.info("Optimization batch %s completed", self._chunk_range(job.chunk))

                    optimized_dict.update(result)
                    self._notify_chunk_completed(job.chunk, result)

                if not made_progress:
                    time.sleep(OPTIMIZE_POLL_INTERVAL_SECONDS)

            if not self.is_running:
                raise RuntimeError("Optimization stopped")

        finally:
            self._terminate_active_jobs()

        return optimized_dict

    def _start_process_job(self, ctx: Any, chunk: Dict[str, str]) -> _ProcessJob:
        logger.info("[+]Optimizing subtitles: %s", self._chunk_range(chunk))

        parent_conn, child_conn = ctx.Pipe(duplex=False)
        process = ctx.Process(
            target=_optimize_chunk_process,
            args=(
                child_conn,
                chunk,
                self.model,
                self.custom_prompt,
                self.timeout_seconds,
                self.retry_count,
                is_cache_enabled(),
            ),
        )
        process.daemon = True
        process.start()
        child_conn.close()
        return _ProcessJob(
            chunk=chunk,
            process=process,
            conn=parent_conn,
            started_at=time.time(),
        )

    def _poll_process_job(
        self, job: _ProcessJob, now: float
    ) -> Tuple[str, Dict[str, str], str]:
        try:
            has_data = job.conn.poll()
        except OSError as exc:
            self._kill_job(job)
            return "error", job.chunk, f"Child process pipe failed: {exc}"

        if has_data:
            try:
                status, result, error_message = job.conn.recv()
            except EOFError:
                status, result, error_message = "error", job.chunk, "Child process closed"
            self._cleanup_job(job)
            if status == "ok" and isinstance(result, dict):
                return "ok", result, ""
            return "error", job.chunk, error_message or "Child process failed"

        if not job.process.is_alive():
            exit_code = job.process.exitcode
            self._cleanup_job(job)
            return "error", job.chunk, f"Child process exited early: exit_code={exit_code}"

        elapsed = now - job.started_at
        if elapsed > self.batch_timeout_seconds:
            error_message = (
                f"Batch timed out after {self.batch_timeout_seconds} seconds: "
                f"{self._chunk_range(job.chunk)}"
            )
            self._kill_job(job)
            return "timeout", job.chunk, error_message

        return "pending", job.chunk, ""

    @staticmethod
    def _cleanup_job(job: _ProcessJob) -> None:
        try:
            job.conn.close()
        except Exception:
            pass
        try:
            job.process.join(timeout=1)
        except Exception:
            pass

    def _kill_job(self, job: _ProcessJob) -> None:
        try:
            if job.process.is_alive():
                job.process.terminate()
                job.process.join(timeout=2)
            if job.process.is_alive():
                job.process.kill()
                job.process.join(timeout=2)
        except Exception as exc:
            logger.error("Failed to terminate optimization child process: %s", str(exc))
        finally:
            self._cleanup_job(job)

    def _terminate_active_jobs(self) -> None:
        for job in list(self._active_jobs):
            self._kill_job(job)
        self._active_jobs.clear()

    @staticmethod
    def _chunk_range(chunk: Dict[str, str]) -> str:
        return f"{next(iter(chunk))}-{next(reversed(chunk))}"

    def _optimize_chunk(self, subtitle_chunk: Dict[str, str]) -> Dict[str, str]:
        try:
            return self.agent_loop(subtitle_chunk)
        except Exception as exc:
            logger.error(f"Optimization failed: {str(exc)}")
            return subtitle_chunk

    def _notify_chunk_completed(
        self, subtitle_chunk: Dict[str, str], result: Dict[str, str]
    ) -> None:
        if not (self.is_running and self.update_callback):
            return

        callback_data = [
            SubtitleProcessData(
                index=int(idx),
                original_text=subtitle_chunk[idx],
                optimized_text=result.get(idx, subtitle_chunk[idx]),
            )
            for idx in sorted(subtitle_chunk.keys(), key=int)
        ]
        self.update_callback(callback_data)

    def agent_loop(self, subtitle_chunk: Dict[str, str]) -> Dict[str, str]:
        """使用 agent loop 优化字幕。"""
        user_prompt = (
            f"Correct the following subtitles. Keep the original language, do not translate:\n"
            f"<input_subtitle>{str(subtitle_chunk)}</input_subtitle>"
        )

        if self.custom_prompt:
            user_prompt += (
                f"\nReference content:\n<reference>{self.custom_prompt}</reference>"
            )

        messages = [
            {"role": "system", "content": get_prompt("optimize/subtitle")},
            {"role": "user", "content": user_prompt},
        ]

        last_result: Optional[Dict[str, str]] = None

        for step in range(self.retry_count):
            response = call_llm(
                messages=messages,
                model=self.model,
                temperature=0.2,
                timeout=self.timeout_seconds,
            )

            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM returned empty result")

            parsed_result = json_repair.loads(result_text)
            if not isinstance(parsed_result, dict):
                raise ValueError(
                    f"LLM返回结果类型Error，期望dict，实际{type(parsed_result)}"
                )

            result_dict: Dict[str, str] = parsed_result
            last_result = result_dict

            is_valid, error_message = self._validate_optimization_result(
                original_chunk=subtitle_chunk, optimized_chunk=result_dict
            )

            if is_valid:
                return self._repair_subtitle(subtitle_chunk, result_dict)

            logger.warning(
                f"优化验证失败，开始反馈循环 (第{step + 1}次尝试): {error_message}"
            )
            messages.append({"role": "assistant", "content": result_text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Validation failed: {error_message}\n"
                        f"Please fix the errors and output ONLY a valid JSON dictionary."
                    ),
                }
            )

        logger.warning(f"Max attempts reached({self.retry_count})，returning last result")
        return (
            self._repair_subtitle(subtitle_chunk, last_result)
            if last_result
            else subtitle_chunk
        )

    def _validate_optimization_result(
        self, original_chunk: Dict[str, str], optimized_chunk: Dict[str, str]
    ) -> Tuple[bool, str]:
        """验证优化结果。"""
        expected_keys = set(original_chunk.keys())
        actual_keys = set(optimized_chunk.keys())

        if expected_keys != actual_keys:
            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys

            error_parts = []
            if missing:
                error_parts.append(f"Missing keys: {sorted(missing)}")
            if extra:
                error_parts.append(f"Extra keys: {sorted(extra)}")

            error_msg = (
                "\n".join(error_parts) + f"\nRequired keys: {sorted(expected_keys)}\n"
                f"Please return the COMPLETE optimized dictionary with ALL {len(expected_keys)} keys."
            )
            return False, error_msg

        excessive_changes = []
        for key in expected_keys:
            original_text = original_chunk[key]
            optimized_text = optimized_chunk[key]

            original_cleaned = re.sub(r"\s+", " ", original_text).strip()
            optimized_cleaned = re.sub(r"\s+", " ", optimized_text).strip()

            matcher = difflib.SequenceMatcher(None, original_cleaned, optimized_cleaned)
            similarity = matcher.ratio()
            similarity_threshold = 0.3 if count_words(original_text) <= 10 else 0.7

            if similarity < similarity_threshold:
                excessive_changes.append(
                    f"Key '{key}': similarity {similarity:.1%} < {similarity_threshold:.0%}. "
                    f"Original: '{original_text}' -> Optimized: '{optimized_text}' "
                )

        if excessive_changes:
            error_msg = ";\n".join(excessive_changes)
            error_msg += (
                "\n\nYour optimizations changed the text too much. "
                "Keep high similarity (>=70% for normal text) by making MINIMAL changes: "
                "only fix recognition errors and improve clarity, "
                "but preserve the original wording, length and structure as much as possible."
            )
            return False, error_msg

        return True, ""

    @staticmethod
    def _repair_subtitle(
        original: Dict[str, str], optimized: Dict[str, str]
    ) -> Dict[str, str]:
        """修复字幕对齐。"""
        try:
            aligner = SubtitleAligner()
            original_list = list(original.values())
            optimized_list = list(optimized.values())

            aligned_source, aligned_target = aligner.align_texts(
                original_list, optimized_list
            )

            if len(aligned_source) != len(aligned_target):
                logger.warning("Alignment length mismatch，returning original")
                return optimized

            start_id = next(iter(original.keys()))
            return {
                str(int(start_id) + i): text for i, text in enumerate(aligned_target)
            }

        except Exception as exc:
            logger.error(f"Alignment failed: {str(exc)}，returning original")
            return optimized

    @staticmethod
    def _create_segments(
        original_segments: List[ASRDataSeg],
        optimized_dict: Dict[str, str],
    ) -> List[ASRDataSeg]:
        """从优化字典创建新的 ASRDataSeg 列表。"""
        return [
            ASRDataSeg(
                text=optimized_dict.get(str(i), seg.text),
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
            for i, seg in enumerate(original_segments, 1)
        ]

    def stop(self) -> None:
        """停止优化器并清理子进程。"""
        if not self.is_running:
            return

        self.is_running = False
        self._terminate_active_jobs()
