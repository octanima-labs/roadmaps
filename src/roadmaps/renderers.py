from __future__ import annotations

import re

from roadmaps.constants import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NO_MILESTONE,
    NOT_STARTED,
    ONGOING,
    UNSORTED,
)
from roadmaps.model import (
    Roadmap,
    Task,
    TaskGroup,
)


class TextRenderer:
    @staticmethod
    def render_roadmap(roadmap: Roadmap) -> str:
        return "\n".join(_render_text_item(step, 0) for step in roadmap.steps)


class MarkdownRenderer:
    @staticmethod
    def render_roadmap(roadmap: Roadmap) -> str:
        return "\n".join(_render_markdown_item(step, 0) for step in roadmap.steps)


def _render_text_item(item: Task | TaskGroup, level: int) -> str:
    indent = "  " * level
    order = "-" if item.order == UNSORTED else f"{item.order}."
    description_lines = item.description.splitlines()
    first_description = description_lines[0]
    lines = [
        (
            f"{indent}{order} {_text_status_marker(item)}"
            f"{_text_metadata_marker(item)}{_text_milestone_marker(item)} "
            f"{first_description}"
        )
    ]

    continuation_indent = f"{indent}  "
    lines.extend(
        f"{continuation_indent}{_escape_text_description_line(line)}"
        for line in description_lines[1:]
    )
    if isinstance(item, TaskGroup):
        lines.extend(_render_text_item(child, level + 1) for child in item.tasks)
    return "\n".join(lines)


def _text_status_marker(item: Task | TaskGroup) -> str:
    if item.status == NOT_STARTED:
        return "[ ]"
    if item.status == ONGOING:
        if not isinstance(item, TaskGroup) and item.completion:
            return f"[~{item.completion:.1f}%]"
        return "[~]"
    return "[x]"


def _text_metadata_marker(item: Task | TaskGroup) -> str:
    if item.is_optional():
        return "?"
    if item.status == COMPLETED or item.priority == DEFAULT_PRIORITY:
        return ""
    if item.priority == MAX_PRIORITY:
        return "!"
    return f"^{item.priority}"


def _text_milestone_marker(item: Task | TaskGroup) -> str:
    if item.milestone == NO_MILESTONE:
        return ""
    return f" ({item.milestone})"


def _escape_text_description_line(line: str) -> str:
    if _is_list_breaking_description_line(line):
        return f"\\{line}"
    return line


def _render_markdown_item(item: Task | TaskGroup, level: int) -> str:
    indent = "  " * level
    order = "-" if item.order == UNSORTED else f"{item.order}."
    description_lines = item.description.splitlines()
    first_description = _escape_markdown_description_line(description_lines[0])
    metadata = _markdown_metadata_marker(item)
    metadata_part = f" {metadata}" if metadata else ""
    lines = [
        (
            f"{indent}{order} {_markdown_status_marker(item)}{metadata_part} "
            f"{first_description}"
        )
    ]

    continuation_indent = f"{indent}  "
    lines.extend(
        f"{continuation_indent}{_escape_markdown_description_line(line)}"
        for line in description_lines[1:]
    )
    if isinstance(item, TaskGroup):
        lines.extend(_render_markdown_item(child, level + 1) for child in item.tasks)
    return "\n".join(lines)


def _markdown_status_marker(item: Task | TaskGroup) -> str:
    if item.status == NOT_STARTED:
        return "[ ]"
    if item.status == ONGOING:
        if not isinstance(item, TaskGroup) and item.completion:
            return f"[~{item.completion:.1f}%]"
        return "[~]"
    return "[x]"


def _markdown_metadata_marker(item: Task | TaskGroup) -> str:
    priority_marker = ""
    if item.is_optional():
        priority_marker = "?"
    elif item.status != COMPLETED and item.priority != DEFAULT_PRIORITY:
        priority_marker = "!" if item.priority == MAX_PRIORITY else str(item.priority)

    milestone_marker = "" if item.milestone == NO_MILESTONE else str(item.milestone)
    if not priority_marker and not milestone_marker:
        return ""
    if milestone_marker:
        return f"({priority_marker}:{milestone_marker})"
    return f"({priority_marker})"


def _escape_markdown_description_line(line: str) -> str:
    # Keep user Markdown intact except escapes that prevent accidental new lists.
    if _is_list_breaking_description_line(line):
        return f"\\{line}"
    return line


def _is_list_breaking_description_line(line: str) -> bool:
    return re.match(r"^([*+-]|\d+[.)])\s", line) is not None
