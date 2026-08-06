#!/usr/bin/env python3
"""Validate the structure of an UrbanNav experiment Markdown record."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


VERSION_RE = re.compile(r"(?m)^experiment_record_version:\s*1\s*$")
HEADING_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\n]+\}\}|\b(?:TODO|TBD)\b|待填写", re.IGNORECASE)
REQUIRED_SECTIONS = (
    "实验的目的",
    "实验的 setting",
    "记录实验结果",
    "分析实验结果，可能的原因",
    "用户讨论与决策记录",
    "接下来要做的实验",
)
SUBHEADING_RE = re.compile(r"(?m)^###\s+(.+?)\s*$")
REQUIRED_VISUAL_SUBSECTIONS = (
    "可视化与导出计划",
    "可视化与产物",
)


def validate_experiment_record(
    path: Path, *, allow_placeholders: bool = False
) -> list[str]:
    """Return structural errors for one experiment Markdown record.

    Args:
        path: Markdown document to validate.
        allow_placeholders: Whether template placeholder text is allowed.

    Returns:
        A list of human-readable validation errors. An empty list means the
        structural checks passed.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: cannot read file: {exc}"]

    errors: list[str] = []
    if not VERSION_RE.search(text):
        errors.append(f"{path}: missing experiment_record_version: 1")

    headings = [
        (match.group(1), match.start(), match.end())
        for match in HEADING_RE.finditer(text)
    ]
    positions: list[int] = []
    # 必需章节必须唯一且保持模板顺序，避免实验职责随文档写法漂移。
    for section in REQUIRED_SECTIONS:
        matches = [item for item in headings if item[0] == section]
        if len(matches) != 1:
            errors.append(f"{path}: section {section!r} occurs {len(matches)} times")
            continue
        positions.append(matches[0][1])

    if len(positions) == len(REQUIRED_SECTIONS) and positions != sorted(positions):
        errors.append(f"{path}: required sections are out of order")

    subheadings = [
        (match.group(1), match.start(), match.end())
        for match in SUBHEADING_RE.finditer(text)
    ]
    visual_positions: dict[str, int] = {}
    # 训练/评测必须在启动前声明观测与导出计划，并在结果中交付真实视觉证据。
    for section in REQUIRED_VISUAL_SUBSECTIONS:
        matches = [item for item in subheadings if item[0] == section]
        if len(matches) != 1:
            errors.append(
                f"{path}: visual subsection {section!r} occurs {len(matches)} times"
            )
            continue
        visual_positions[section] = matches[0][1]

    required_section_positions = {
        name: next((item[1] for item in headings if item[0] == name), None)
        for name in REQUIRED_SECTIONS
    }
    plan_position = visual_positions.get("可视化与导出计划")
    result_position = visual_positions.get("可视化与产物")
    setting_position = required_section_positions["实验的 setting"]
    results_position = required_section_positions["记录实验结果"]
    analysis_position = required_section_positions["分析实验结果，可能的原因"]
    if (
        plan_position is not None
        and setting_position is not None
        and results_position is not None
        and not (setting_position < plan_position < results_position)
    ):
        errors.append(f"{path}: visual plan must be inside '实验的 setting'")
    if (
        result_position is not None
        and results_position is not None
        and analysis_position is not None
        and not (results_position < result_position < analysis_position)
    ):
        errors.append(f"{path}: visual outputs must be inside '记录实验结果'")

    if not allow_placeholders and PLACEHOLDER_RE.search(text):
        errors.append(f"{path}: unresolved template placeholder found")

    discussion_header = (
        "| 时间 | 用户讨论/关注点 | 最终决定 | 对实验的影响 | 未解决问题 |"
    )
    next_experiment_header = (
        "| 优先级 | 下一实验 | 假设 | 唯一主要变量 | 所需证据 | "
        "通过/停止条件 | 依赖或授权 |"
    )
    # 两张表是讨论可恢复和负责人主动规划下一实验的最小机器检查边界。
    if discussion_header not in text:
        errors.append(f"{path}: discussion decision table is missing")
    if next_experiment_header not in text:
        errors.append(f"{path}: next-experiment table is missing")
    return errors


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        The configured argument parser.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Experiment Markdown files")
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow placeholders when validating the canonical template",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate requested files and return a shell status.

    Args:
        argv: Optional command-line arguments for tests or embedding.

    Returns:
        Zero when every file passes, otherwise one.
    """

    args = _build_parser().parse_args(argv)
    errors = [
        error
        for path in args.paths
        for error in validate_experiment_record(
            path, allow_placeholders=args.allow_placeholders
        )
    ]
    if errors:
        for error in errors:
            print(error)
        return 1
    for path in args.paths:
        print(f"PASS {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
