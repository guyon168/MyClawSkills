"""
企业微信机器人推送模块
使用 Markdown 格式将报告推送到企业微信群
支持长内容自动分段推送
"""
import logging
import requests
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 企业微信 Markdown 内容最大长度限制（留 96 字符余量）
MAX_CONTENT_BYTES = 4000  # 企业微信 Markdown 最大字节数（字符数限制，非字节）
# 分段推送间隔（秒），防止频率限制
PUSH_INTERVAL = 1


def push_to_wechat(
    webhook_url: str,
    report_text: str,
    proxies: Optional[dict] = None,
) -> bool:
    """
    推送报告到企业微信群（自动处理过长内容分段推送）

    Args:
        webhook_url: 企业微信机器人的 Webhook URL
        report_text: Markdown 格式的报告文本
        proxies: 代理配置（如启用）

    Returns:
        True 表示全部推送成功，False 表示有失败
    """
    # 转换为企业微信兼容格式
    content = _convert_to_wechat_markdown(report_text)
    # 注意：WeChat 按 UTF-8 字节数计算限制，非字符数
    total_bytes = len(content.encode("utf-8"))
    logger.info(f"企业微信推送内容: {len(content)} 字符 / {total_bytes} 字节")

    # 如果内容超过限制，分段推送
    if total_bytes > MAX_CONTENT_BYTES:
        chunks = _split_content(content)
        logger.info(f"内容过长，将分 {len(chunks)} 段推送")

        success_count = 0
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"正在推送第 {i}/{len(chunks)} 段...")
            if _send_single_message(webhook_url, chunk, proxies):
                success_count += 1
                # 最后一段之后不等待
                if i < len(chunks):
                    time.sleep(PUSH_INTERVAL)
            else:
                logger.error(f"第 {i}/{len(chunks)} 段推送失败")

        if success_count == len(chunks):
            logger.info(f"企业微信推送成功（{len(chunks)} 段）")
            return True
        else:
            logger.warning(f"企业微信推送部分失败: {success_count}/{len(chunks)} 成功")
            return False
    else:
        # 正常推送
        success = _send_single_message(webhook_url, content, proxies)
        return success


def _send_single_message(
    webhook_url: str,
    content: str,
    proxies: Optional[dict] = None,
) -> bool:
    """
    发送单条消息到企业微信

    Returns:
        True 成功，False 失败
    """
    try:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }

        headers = {"Content-Type": "application/json"}
        timeout = 30

        response = requests.post(
            webhook_url,
            json=payload,
            headers=headers,
            timeout=timeout,
            proxies=proxies,
        )
        result = response.json()

        if result.get("errcode") == 0:
            return True
        else:
            logger.error(f"企业微信推送失败: {result}")
            return False

    except requests.RequestException as e:
        logger.error(f"企业微信推送请求异常: {e}")
        return False
    except Exception as e:
        logger.error(f"企业微信推送未知错误: {e}")
        return False


def _split_content(content: str) -> list[str]:
    """
    将过长内容智能分段，确保每段不超过 MAX_CONTENT_BYTES（按 UTF-8 字节数）

    分段策略：
    1. 优先按一级标题（##）分段
    2. 如果单个章节仍超限，按二级标题分段
    3. 如果仍超限，按自然段落分段
    4. 最后按字节数硬截断
    """
    sections = _split_by_section(content)

    chunks = []
    current_chunk = ""

    for section in sections:
        section_bytes = len(section.encode("utf-8"))
        # 如果单个章节就超限
        if section_bytes > MAX_CONTENT_BYTES:
            # 先把当前累积的加入
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # 对超长章节继续细分
            sub_chunks = _split_by_heading(section, "### ")
            for sub in sub_chunks:
                sub_bytes = len(sub.encode("utf-8"))
                if sub_bytes > MAX_CONTENT_BYTES:
                    # 按段落拆分
                    para_chunks = _split_by_paragraph(sub)
                    for para in para_chunks:
                        para_bytes = len(para.encode("utf-8"))
                        if para_bytes > MAX_CONTENT_BYTES:
                            # 按字节数硬截断（尽量按句子截断）
                            chunks.append(_truncate_by_bytes(para, MAX_CONTENT_BYTES))
                        else:
                            chunks.append(para.strip())
                else:
                    chunks.append(sub.strip())
        else:
            # 检查加上当前章节是否会超限（按字节）
            current_bytes = len(current_chunk.encode("utf-8"))
            if current_bytes + section_bytes + 2 > MAX_CONTENT_BYTES:
                chunks.append(current_chunk.strip())
                current_chunk = section
            else:
                current_chunk += section

    # 加入最后一块
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c]


def _truncate_by_bytes(text: str, max_bytes: int) -> str:
    """
    按字节数截断字符串，确保截断后不超过 max_bytes
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    # 二分查找最大有效字节数
    result = text
    for i in range(len(text), 0, -1):
        if len(text[:i].encode("utf-8")) <= max_bytes:
            result = text[:i]
            break

    # 追加省略标记
    truncated = result + "..."
    if len(truncated.encode("utf-8")) <= max_bytes:
        return truncated
    return result


def _split_by_heading(content: str, heading_marker: str) -> list[str]:
    """
    按指定级别的标题分割内容
    """
    lines = content.split("\n")
    sections = []
    current = []

    for line in lines:
        if line.startswith(heading_marker):
            if current:
                sections.append("\n".join(current))
                current = []
        current.append(line)

    if current:
        sections.append("\n".join(current))

    return sections


# 中文章节标题标记（用于识别报告中的章节）
_CHINESE_SECTION_MARKERS = [
    "**一、", "**二、", "**三、", "**四、", "**五、",
    "**六、", "**七、", "**八、", "**九、", "**十、",
]


def _split_by_section(content: str) -> list[str]:
    """
    按中文章节标题（一、二、三...）分割内容
    """
    import re
    pattern = "|".join(re.escape(m) for m in _CHINESE_SECTION_MARKERS)
    parts = re.split(f"({pattern})", content)
    # 重新组合：标题+内容
    sections = []
    current = ""
    for part in parts:
        if not part.strip():
            continue
        is_header = any(part.startswith(m) for m in _CHINESE_SECTION_MARKERS)
        if is_header and current:
            sections.append(current)
            current = ""
        current += part
    if current:
        sections.append(current)
    return [s for s in sections if s.strip()]


def _split_by_paragraph(content: str) -> list[str]:
    """
    按空行分割段落
    """
    paragraphs = content.split("\n\n")
    return [p.replace("\n", " ").strip() for p in paragraphs if p.strip()]


def _convert_to_wechat_markdown(text: str) -> str:
    """
    将报告 Markdown 转换为企业微信兼容的 Markdown 格式

    企业微信支持的 Markdown:
    - 标题 (# ## ###)
    - 粗体 (**text**)
    - 链接 (<a href="url">text</a>)
    - 引用 (>)
    - 代码块 (```)
    注意：不支持表格，使用列表替代
    """
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()

        # 保留分隔线样式但转换为普通文本
        if stripped.startswith("━") or stripped.startswith("━━"):
            result.append("——")
            continue

        # 移除多余空行
        if not stripped:
            result.append("")
            continue

        # 标题保持不变
        if stripped.startswith("#"):
            result.append(line)
            continue

        # 粗体保持不变
        if "**" in stripped:
            result.append(line)
            continue

        # 列表项保持不变
        if stripped.startswith(("·", "-", "*")):
            result.append(line)
            continue

        # 普通文本
        result.append(stripped)

    return "\n".join(result)
