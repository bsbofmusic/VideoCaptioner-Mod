"""字幕优化模块

使用LLM优化字幕内容，支持agent loop自动验证和修正。
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
from ..utils.logger import setup_logger
from ..utils.text_utils import count_words

logger = setup_logger("subtitle_optimizer")

MAX_STEPS = 2
MAX_VALIDATION_FEEDBACK_ITEMS = 5
OPTIMIZE_LLM_CALL_TIMEOUT_SECONDS = 45
OPTIMIZE_BATCH_TIMEOUT_SECONDS = 90
OPTIMIZE_POLL_INTERVAL_SECONDS = 0.5
OPTIMIZE_MAX_IN_FLIGHT_CAP = 4
# Backward-compatible name for old tests/log messages. The optimizer now uses a
# hard per-batch process timeout instead of a ThreadPoolExecutor no-progress wait.
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
) -> None:
    """Optimize one batch in a child process so the parent can kill hard hangs."""
    try:
        optimizer = SubtitleOptimizer(
            thread_num=1,
            batch_num=max(len(subtitle_chunk), 1),
            model=model,
            custom_prompt=custom_prompt,
            update_callback=None,
        )
        result = optimizer.agent_loop(subtitle_chunk)
        conn.send(("ok", result, ""))
    except BaseException as e:  # child must never hang the parent by crashing silently
        try:
            conn.send(("error", subtitle_chunk, f"{type(e).__name__}: {e}"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


class SubtitleOptimizer:
    """字幕优化器

    使用LLM优化字幕内容，支持：
    - Agent loop自动验证和修正
    - 并发批量处理
    - 自动对齐修复
    """

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        model: str,
        custom_prompt: str,
        update_callback: Optional[Callable] = None,
    ):
        """初始化优化器

        Args:
            thread_num: 并发线程数
            batch_num: 每批处理的字幕数量
            model: LLM模型名称
            custom_prompt: 自定义优化提示词
            temperature: LLM温度参数
            update_callback: 进度更新回调函数
        """
        self.thread_num = thread_num
        self.batch_num = batch_num
        self.model = model
        self.custom_prompt = custom_prompt
        self.update_callback = update_callback

        self.is_running = True
        self._active_jobs: List[_ProcessJob] = []
        atexit.register(self.stop)

    def optimize_subtitle(self, subtitle_data: Union[str, ASRData]) -> ASRData:
        """优化字幕

        Args:
            subtitle_data: 字幕文件路径或ASRData对象

        Returns:
            优化后的ASRData对象
        """
        try:
            # 读取字幕
            if isinstance(subtitle_data, str):
                asr_data = ASRData.from_subtitle_file(subtitle_data)
            else:
                asr_data = subtitle_data

            # 转换为字典格式
            subtitle_dict = {
                str(i): seg.text for i, seg in enumerate(asr_data.segments, 1)
            }

            # 分批处理
            chunks = self._split_chunks(subtitle_dict)

            # 并行优化
            optimized_dict = self._parallel_optimize(chunks)

            # 创建新segments
            new_segments = self._create_segments(asr_data.segments, optimized_dict)

            return ASRData(new_segments)

        except Exception as e:
            logger.error(f"优化失败：{str(e)}")
            raise RuntimeError(f"优化失败：{str(e)}")

    def _split_chunks(self, subtitle_dict: Dict[str, str]) -> List[Dict[str, str]]:
        """将字幕字典分割成批次

        Args:
            subtitle_dict: 字幕字典 {index: text}

        Returns:
            批次列表
        """
        items = list(subtitle_dict.items())
        return [
            dict(items[i : i + self.batch_num])
            for i in range(0, len(items), self.batch_num)
        ]

    def _parallel_optimize(self, chunks: List[Dict[str, str]]) -> Dict[str, str]:
        """并行优化所有批次

        Args:
            chunks: 字幕批次列表

        Returns:
            优化后的字幕字典
        """
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
        consecutive_hard_failures = 0

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
                    if status == "ok":
                        consecutive_hard_failures = 0
                    else:
                        consecutive_hard_failures += 1
                        logger.error(
                            "字幕优化批次 %s 失败，保留原文：%s",
                            self._chunk_range(job.chunk),
                            error_message,
                        )

                    optimized_dict.update(result)
                    self._notify_chunk_completed(job.chunk, result)

                    if consecutive_hard_failures >= max_in_flight:
                        raise RuntimeError(
                            f"字幕优化连续 {consecutive_hard_failures} 个批次超时或崩溃，"
                            f"已停止以避免卡死。最后错误：{error_message}"
                        )

                if not made_progress:
                    time.sleep(OPTIMIZE_POLL_INTERVAL_SECONDS)

            if not self.is_running:
                raise RuntimeError("字幕优化已取消")

        finally:
            self._terminate_active_jobs()

        return optimized_dict

    def _start_process_job(self, ctx: Any, chunk: Dict[str, str]) -> _ProcessJob:
        start_idx = next(iter(chunk))
        end_idx = next(reversed(chunk))
        logger.info(f"[+]正在优化字幕：{start_idx} - {end_idx}")

        parent_conn, child_conn = ctx.Pipe(duplex=False)
        process = ctx.Process(
            target=_optimize_chunk_process,
            args=(child_conn, chunk, self.model, self.custom_prompt),
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
        except OSError as e:
            self._kill_job(job)
            return "error", job.chunk, f"子进程通信失败：{e}"

        if has_data:
            try:
                status, result, error_message = job.conn.recv()
            except EOFError:
                status, result, error_message = (
                    "error",
                    job.chunk,
                    "子进程未返回结果",
                )
            self._cleanup_job(job)
            if status == "ok" and isinstance(result, dict):
                return "ok", result, ""
            return "error", job.chunk, error_message or "子进程优化失败"

        if not job.process.is_alive():
            exit_code = job.process.exitcode
            self._cleanup_job(job)
            return "error", job.chunk, f"子进程异常退出，exit_code={exit_code}"

        elapsed = now - job.started_at
        if elapsed > OPTIMIZE_BATCH_TIMEOUT_SECONDS:
            error_message = (
                f"批次 {self._chunk_range(job.chunk)} 超过 "
                f"{OPTIMIZE_BATCH_TIMEOUT_SECONDS} 秒未完成，已强制终止"
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
        except Exception as e:
            logger.error("终止优化子进程失败：%s", str(e))
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
        """优化单个字幕批次

        Args:
            subtitle_chunk: 字幕批次字典

        Returns:
            优化后的字幕批次
        """
        start_idx = next(iter(subtitle_chunk))
        end_idx = next(reversed(subtitle_chunk))
        logger.info(f"[+]正在优化字幕：{start_idx} - {end_idx}")

        try:
            return self.agent_loop(subtitle_chunk)

        except Exception as e:
            logger.error(f"优化失败：{str(e)}")
            return subtitle_chunk

    def _notify_chunk_completed(
        self, subtitle_chunk: Dict[str, str], result: Dict[str, str]
    ) -> None:
        """Notify UI that a chunk is finished, even when it falls back to original text."""
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
        """使用agent loop优化字幕

        LLM → 验证 → 反馈 → 重试 (最多MAX_STEPS次)

        Args:
            subtitle_chunk: 字幕批次字典

        Returns:
            优化后的字幕批次

        Raises:
            ValueError: LLM返回空结果
        """
        # 构建提示词
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

        # Agent loop
        for step in range(MAX_STEPS):
            # 调用LLM
            response = call_llm(
                messages=messages,
                model=self.model,
                temperature=0.2,
                timeout=OPTIMIZE_LLM_CALL_TIMEOUT_SECONDS,
            )

            result_text = response.choices[0].message.content
            if not result_text:
                if step == 0:
                    messages.append(
                        {"role": "user", "content": "Output cannot be empty. Return JSON only."}
                    )
                    continue
                return subtitle_chunk

            # 解析结果
            try:
                parsed_result = json_repair.loads(result_text)
            except Exception as e:
                logger.warning("优化结果 JSON 解析失败：%s", str(e))
                if step == 0:
                    messages.append({"role": "assistant", "content": result_text[:1000]})
                    messages.append(
                        {"role": "user", "content": "Return ONLY a valid JSON dictionary."}
                    )
                    continue
                return subtitle_chunk

            if not isinstance(parsed_result, dict):
                logger.warning(
                    "LLM返回结果类型错误，期望dict，实际%s", type(parsed_result)
                )
                if step == 0:
                    messages.append(
                        {"role": "user", "content": "Output must be a JSON dictionary."}
                    )
                    continue
                return subtitle_chunk

            result_dict: Dict[str, str] = parsed_result
            last_result = result_dict

            normalized_result, issues, missing_or_extra = self._normalize_result(
                subtitle_chunk, result_dict
            )

            if not issues:
                return normalized_result

            error_message = self._format_issues(issues)
            logger.warning("优化结果需要修正：%s", error_message)

            # Missing/extra keys can be fixed by one compact feedback loop. Similarity
            # failures are deterministic safety checks: keep original text instead of
            # spending extra LLM calls and risking long stalls.
            if not missing_or_extra or step >= MAX_STEPS - 1:
                return normalized_result

            logger.warning("优化键不完整，开始一次反馈修正 (第%s次尝试)", step + 1)
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

        # 达到最大步数
        logger.warning(f"达到最大尝试次数({MAX_STEPS})，返回最后结果")
        if last_result:
            normalized_result, _, _ = self._normalize_result(subtitle_chunk, last_result)
            return normalized_result
        return subtitle_chunk

    def _normalize_result(
        self, original_chunk: Dict[str, str], candidate: Dict[str, Any]
    ) -> Tuple[Dict[str, str], List[str], bool]:
        """Normalize LLM output and fall back to original text for unsafe items."""
        normalized: Dict[str, str] = {}
        issues: List[str] = []
        expected_keys = set(original_chunk.keys())
        actual_keys = set(candidate.keys())
        missing_or_extra = expected_keys != actual_keys

        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        if missing:
            issues.append(f"Missing keys: {sorted(missing)}")
        if extra:
            issues.append(f"Extra keys dropped: {sorted(extra)}")

        for key in sorted(original_chunk.keys(), key=int):
            original_text = original_chunk[key]
            value = candidate.get(key, original_text)
            if not isinstance(value, str):
                value = str(value)

            if not value.strip():
                issues.append(f"Key '{key}': empty value, kept original")
                normalized[key] = original_text
                continue

            if self._is_excessive_change(original_text, value):
                issues.append(f"Key '{key}': changed too much, kept original")
                normalized[key] = original_text
                continue

            normalized[key] = value

        return normalized, issues, missing_or_extra

    @staticmethod
    def _format_issues(issues: List[str]) -> str:
        shown = issues[:MAX_VALIDATION_FEEDBACK_ITEMS]
        message = "; ".join(shown)
        if len(issues) > MAX_VALIDATION_FEEDBACK_ITEMS:
            message += f"; 等 {len(issues)} 项"
        return message

    @staticmethod
    def _is_excessive_change(original_text: str, optimized_text: str) -> bool:
        original_cleaned = re.sub(r"\s+", " ", original_text).strip()
        optimized_cleaned = re.sub(r"\s+", " ", optimized_text).strip()
        matcher = difflib.SequenceMatcher(None, original_cleaned, optimized_cleaned)
        similarity = matcher.ratio()
        similarity_threshold = 0.3 if count_words(original_text) <= 10 else 0.7
        return similarity < similarity_threshold

    def _validate_optimization_result(
        self, original_chunk: Dict[str, str], optimized_chunk: Dict[str, str]
    ) -> Tuple[bool, str]:
        """验证优化结果

        检查：
        1. 键是否完全匹配
        2. 改动是否过大（相似度 < 0.7）

        Args:
            original_chunk: 原始字幕批次
            optimized_chunk: 优化后字幕批次

        Returns:
            (是否有效, 错误反馈)
        """
        expected_keys = set(original_chunk.keys())
        actual_keys = set(optimized_chunk.keys())

        # 检查键匹配
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

        # 检查改动是否过大（逐条比较相似度）
        excessive_changes = []
        for key in expected_keys:
            original_text = original_chunk[key]
            optimized_text = optimized_chunk[key]

            # 清理文本用于比较
            original_cleaned = re.sub(r"\s+", " ", original_text).strip()
            optimized_cleaned = re.sub(r"\s+", " ", optimized_text).strip()

            # 计算相似度
            matcher = difflib.SequenceMatcher(None, original_cleaned, optimized_cleaned)
            similarity = matcher.ratio()
            similarity_threshold = 0.3 if count_words(original_text) <= 10 else 0.7

            # 相似度过低
            if similarity < similarity_threshold:
                excessive_changes.append(
                    f"Key '{key}': similarity {similarity:.1%} < {similarity_threshold:.0%}. "
                    f"Original: '{original_text}' → Optimized: '{optimized_text}' "
                )

        if excessive_changes:
            error_msg = ";\n".join(excessive_changes)
            error_msg += (
                "\n\nYour optimizations changed the text too much. "
                "Keep high similarity (≥70% for normal text) by making MINIMAL changes: "
                "only fix recognition errors and improve clarity, "
                "but preserve the original wording, length and structure as much as possible."
            )
            return False, error_msg

        return True, ""

    @staticmethod
    def _create_segments(
        original_segments: List[ASRDataSeg],
        optimized_dict: Dict[str, str],
    ) -> List[ASRDataSeg]:
        """从优化字典创建新的ASRDataSeg列表

        Args:
            original_segments: 原始字幕段列表
            optimized_dict: 优化后字幕字典

        Returns:
            新的字幕段列表
        """
        return [
            ASRDataSeg(
                text=optimized_dict.get(str(i), seg.text),
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
            for i, seg in enumerate(original_segments, 1)
        ]

    def stop(self) -> None:
        """停止优化器并清理资源"""
        if not self.is_running:
            return

        self.is_running = False

        self._terminate_active_jobs()
