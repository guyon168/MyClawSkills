"""
Mattermost Incoming Webhook 推送模块
使用 Mattermost 原生 Markdown 格式推送日报
支持长内容按 Markdown 结构自动分段推送，并对临时网络失败进行重试
"""
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Mattermost Incoming Webhook 文本长度限制留余量。
# 字符数负责减少分段，字节数负责保护 UTF-8/中文内容不超安全范围。
DEFAULT_MAX_CHARS_PER_MESSAGE = int(os.getenv("MATTERMOST_MAX_CHARS_PER_MESSAGE", "5000"))
DEFAULT_MAX_CONTENT_BYTES = int(os.getenv("MATTERMOST_MAX_BYTES_PER_MESSAGE", "15000"))
DEFAULT_RETRY_TIMES = int(os.getenv("MATTERMOST_RETRY_TIMES", "3"))
DEFAULT_RETRY_DELAY = float(os.getenv("MATTERMOST_RETRY_DELAY", "1.5"))
# 分段推送间隔（秒），防止频率限制
PUSH_INTERVAL = 0.5
DEFAULT_USERNAME = "Crypto Daily Bot"


def push_to_mattermost(
    webhook_url: str,
    report_text: str,
    proxies: Optional[dict] = None,
    username: str = DEFAULT_USERNAME,
    max_chars_per_message: int = DEFAULT_MAX_CHARS_PER_MESSAGE,
    retry_times: int = DEFAULT_RETRY_TIMES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> bool:
    """
    推送报告到 Mattermost Incoming Webhook（自动处理过长内容分段推送）。

    Args:
        webhook_url: Mattermost Incoming Webhook URL。
        report_text: Markdown 格式的报告文本。
        proxies: 代理配置（如启用）。
        username: 推送显示名称。
        max_chars_per_message: 单条消息最大字符数，默认 5000。
        retry_times: 每段失败后的最大尝试次数（含首次）。
        retry_delay: 首次重试等待秒数，后续指数退避。

    Returns:
        True 表示全部推送成功，False 表示有失败。
    """
    content = _convert_to_mattermost_markdown(report_text)
    total_bytes = len(content.encode("utf-8"))
    max_chars = max(1000, int(max_chars_per_message or DEFAULT_MAX_CHARS_PER_MESSAGE))
    retry_count = max(1, int(retry_times or DEFAULT_RETRY_TIMES))
    base_delay = max(0.0, float(retry_delay if retry_delay is not None else DEFAULT_RETRY_DELAY))

    logger.info(f"Mattermost 推送内容: {len(content)} 字符 / {total_bytes} 字节")

    chunks = _split_content(
        content=content,
        max_chars=max_chars,
        max_bytes=DEFAULT_MAX_CONTENT_BYTES,
        header_reserve_chars=32,
    )
    total_chunks = len(chunks)

    if total_chunks > 1:
        logger.info(f"内容过长，将分 {total_chunks} 段推送（单段上限 {max_chars} 字符）")

    success_count = 0
    failed_chunks: list[int] = []
    for index, chunk in enumerate(chunks, 1):
        message = _format_chunk_message(chunk, index, total_chunks)
        logger.info(f"正在推送第 {index}/{total_chunks} 段...")
        if _send_single_message_with_retry(
            webhook_url=webhook_url,
            content=message,
            proxies=proxies,
            username=username,
            retry_times=retry_count,
            retry_delay=base_delay,
        ):
            success_count += 1
            if index < total_chunks:
                time.sleep(PUSH_INTERVAL)
        else:
            failed_chunks.append(index)
            logger.error(f"第 {index}/{total_chunks} 段推送失败")

    if success_count == total_chunks:
        logger.info(f"Mattermost 推送成功（{success_count}/{total_chunks} 段）")
        return True

    failed_text = ", ".join(str(chunk_no) for chunk_no in failed_chunks)
    logger.warning(
        f"Mattermost 推送部分失败: {success_count}/{total_chunks} 成功，失败段: {failed_text}"
    )
    return False


def _send_single_message_with_retry(
    webhook_url: str,
    content: str,
    proxies: Optional[dict] = None,
    username: str = DEFAULT_USERNAME,
    retry_times: int = DEFAULT_RETRY_TIMES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> bool:
    """发送单条消息，失败后按指数退避重试。"""
    attempts = max(1, int(retry_times or DEFAULT_RETRY_TIMES))
    base_delay = max(0.0, float(retry_delay if retry_delay is not None else DEFAULT_RETRY_DELAY))

    for attempt in range(1, attempts + 1):
        if _send_single_message(webhook_url, content, proxies, username):
            if attempt > 1:
                logger.info(f"Mattermost 推送第 {attempt} 次尝试成功")
            return True

        if attempt < attempts:
            sleep_seconds = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"Mattermost 推送失败，将在 {sleep_seconds:.1f}s 后重试（{attempt + 1}/{attempts}）"
            )
            time.sleep(sleep_seconds)

    return False


def _send_single_message(
    webhook_url: str,
    content: str,
    proxies: Optional[dict] = None,
    username: str = DEFAULT_USERNAME,
) -> bool:
    """
    发送单条消息到 Mattermost。

    Mattermost Incoming Webhook 最基础 payload 为：
    {"text": "message"}
    成功响应通常为 HTTP 200 + body: ok。
    """
    try:
        payload = {
            "text": content,
            "username": username,
        }
        response = requests.post(
            webhook_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Connection": "close",
            },
            timeout=30,
            proxies=proxies,
        )

        if response.status_code == 200 and response.text.strip().lower() == "ok":
            return True

        try:
            result = response.json()
        except ValueError:
            result = response.text
        logger.error(f"Mattermost 推送失败: HTTP {response.status_code}, {result}")
        return False

    except requests.RequestException as exc:
        logger.error(f"Mattermost 推送请求异常: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Mattermost 推送未知错误: {exc}")
        return False


def _split_content(
    content: str,
    max_chars: int = DEFAULT_MAX_CHARS_PER_MESSAGE,
    max_bytes: int = DEFAULT_MAX_CONTENT_BYTES,
    header_reserve_chars: int = 0,
) -> list[str]:
    """
    将过长内容按 Markdown 结构智能分段。

    优先按空行、标题、列表行等自然边界组合，避免把很小的段落逐段发送；只有单个
    段落超过限制时才按行/字符硬切，并始终保证 UTF-8 字节数不超过上限。
    """
    clean_content = content.strip()
    if not clean_content:
        return []

    safe_max_chars = max(200, int(max_chars or DEFAULT_MAX_CHARS_PER_MESSAGE) - header_reserve_chars)
    safe_max_bytes = max(1024, int(max_bytes or DEFAULT_MAX_CONTENT_BYTES))
    blocks = _split_markdown_blocks(clean_content)
    chunks: list[str] = []
    current_lines: list[str] = []

    for block in blocks:
        candidate = _join_blocks(current_lines + [block])
        if _fits_limits(candidate, safe_max_chars, safe_max_bytes):
            current_lines.append(block)
            continue

        if current_lines:
            chunks.append(_join_blocks(current_lines))
            current_lines = []

        if _fits_limits(block, safe_max_chars, safe_max_bytes):
            current_lines.append(block)
            continue

        chunks.extend(_split_oversized_block(block, safe_max_chars, safe_max_bytes))

    if current_lines:
        chunks.append(_join_blocks(current_lines))

    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _split_markdown_blocks(content: str) -> list[str]:
    """按 Markdown 自然边界切成可重新组合的块。"""
    lines = content.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block

        if not in_code_block and not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue

        if (
            not in_code_block
            and current
            and _is_markdown_boundary(stripped)
        ):
            blocks.append("\n".join(current).strip())
            current = []

        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def _is_markdown_boundary(stripped_line: str) -> bool:
    """判断当前行是否适合作为新块开始。"""
    if stripped_line.startswith(("#", "**一、", "**二、", "**三、", "**四、", "**五、")):
        return True
    if stripped_line.startswith(("**六、", "**七、", "**八、", "**九、", "**十、")):
        return True
    if stripped_line.startswith(("- ", "* ", "> ")):
        return True
    if len(stripped_line) >= 2 and stripped_line[0].isdigit() and stripped_line[1] in {".", "、"}:
        return True
    return False


def _split_oversized_block(block: str, max_chars: int, max_bytes: int) -> list[str]:
    """将超大块按行组合；单行仍超限时按字符安全切分。"""
    chunks: list[str] = []
    current_lines: list[str] = []

    for line in block.splitlines():
        if _fits_limits(line, max_chars, max_bytes):
            candidate = "\n".join(current_lines + [line]) if current_lines else line
            if _fits_limits(candidate, max_chars, max_bytes):
                current_lines.append(line)
            else:
                if current_lines:
                    chunks.append("\n".join(current_lines).strip())
                current_lines = [line]
            continue

        if current_lines:
            chunks.append("\n".join(current_lines).strip())
            current_lines = []
        chunks.extend(_hard_split_text(line, max_chars, max_bytes))

    if current_lines:
        chunks.append("\n".join(current_lines).strip())

    return [chunk for chunk in chunks if chunk]


def _hard_split_text(text: str, max_chars: int, max_bytes: int) -> list[str]:
    """按字符安全硬切超长文本，避免破坏 UTF-8 字符。"""
    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(text_length, start + max_chars)
        while end > start and not _fits_limits(text[start:end], max_chars, max_bytes):
            end -= 1
        if end == start:
            end = start + 1
        chunks.append(text[start:end].strip())
        start = end

    return [chunk for chunk in chunks if chunk]


def _fits_limits(text: str, max_chars: int, max_bytes: int) -> bool:
    """同时检查字符数和 UTF-8 字节数。"""
    return len(text) <= max_chars and len(text.encode("utf-8")) <= max_bytes


def _join_blocks(blocks: list[str]) -> str:
    """用空行连接 Markdown 块，保留段落可读性。"""
    return "\n\n".join(block.strip() for block in blocks if block.strip()).strip()


def _format_chunk_message(chunk: str, index: int, total: int) -> str:
    """为多段消息添加清晰但简短的段号头部。"""
    if total <= 1:
        return chunk
    return f"（第 {index}/{total} 段）\n{chunk}"


def _truncate_by_bytes(text: str, max_bytes: int) -> str:
    """按 UTF-8 字节数截断文本，保留兼容旧调用。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    result = text
    for index in range(len(text), 0, -1):
        if len(text[:index].encode("utf-8")) <= max_bytes:
            result = text[:index]
            break

    truncated = result + "..."
    if len(truncated.encode("utf-8")) <= max_bytes:
        return truncated
    return result


def _convert_to_mattermost_markdown(text: str) -> str:
    """
    Mattermost 原生支持 Markdown，这里只做轻量清理。
    """
    return text.strip()
