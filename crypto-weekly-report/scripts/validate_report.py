#!/usr/bin/env python3
"""Validate that a generated crypto weekly Markdown report has six sections."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS: tuple[str, ...] = (
    "### 一、本周行情回顾 + 结构判断",
    "### 二、本周热点复盘（3条主线）",
    "### 三、下周展望 + 宏观日历",
    "### 四、下周操作策略",
    "### 五、Twitter热议（情绪温度计）",
    "### 六、下周行动清单",
)


def extract_section_body(markdown: str, heading: str) -> str:
    """Return body text between the selected heading and next level-3 heading."""
    escaped_heading = re.escape(heading)
    pattern = rf"{escaped_heading}\s*\n(?P<body>.*?)(?=\n###\s|\Z)"
    match = re.search(pattern, markdown, flags=re.DOTALL)
    if match is None:
        return ""
    return match.group("body").strip()


def validate_report(markdown_path: Path) -> dict[str, Any]:
    """Validate section presence and non-empty bodies for a Markdown report."""
    result: dict[str, Any] = {
        "path": str(markdown_path),
        "exists": markdown_path.exists(),
        "is_valid": False,
        "sections": [],
        "missing_sections": [],
        "empty_sections": [],
        "error": "",
    }
    if not markdown_path.exists():
        result["error"] = "Markdown file does not exist."
        return result

    markdown = markdown_path.read_text(encoding="utf-8")
    for heading in REQUIRED_SECTIONS:
        body = extract_section_body(markdown, heading)
        section_result = {
            "heading": heading,
            "present": heading in markdown,
            "non_empty": bool(body),
            "body_chars": len(body),
        }
        result["sections"].append(section_result)
        if not section_result["present"]:
            result["missing_sections"].append(heading)
        elif not section_result["non_empty"]:
            result["empty_sections"].append(heading)

    result["is_valid"] = not result["missing_sections"] and not result["empty_sections"]
    return result


def main(argv: list[str]) -> int:
    """Validate a Markdown path passed as the first CLI argument."""
    if len(argv) != 2:
        print(
            json.dumps(
                {
                    "is_valid": False,
                    "error": "Usage: validate_report.py <markdown_path>",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    markdown_path = Path(argv[1]).expanduser().resolve()
    result = validate_report(markdown_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["is_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
