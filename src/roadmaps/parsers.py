from __future__ import annotations

import re
from dataclasses import dataclass, field

from roadmaps._validation import _validate_description_line
from roadmaps.constants import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NO_MILESTONE,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
)
from roadmaps.model import (
    Roadmap,
    Task,
    TaskGroup,
)

TASK_LINE_REGEX = re.compile(
    r"^(?P<indent> *)(?P<order>-|[1-9]\d*\.)(?: "
    r"(?P<status>\[(?: |~[^\]]*|x|X)\])(?P<meta>\?|!|\^\d+)? "
    r"(?:(?P<milestone>\([^)]*\)) )?"
    r"(?P<description>.+))$|^(?P<omitted_indent> *)"
    r"(?P<omitted_order>-|[1-9]\d*\.|[1-9]\d*)(?P<omitted_meta>\?|!|\^\d+)? "
    r"(?:(?P<omitted_milestone>\([^)]*\)) )?"
    r"(?P<omitted_description>.+)$"
)
MARKDOWN_TASK_LINE_REGEX = re.compile(
    r"^(?P<indent> *)(?P<order>-|[1-9]\d*\.) "
    r"(?P<status>\[(?: |~[^\]]*|x|X)\])(?: (?P<meta>\([^)]*\)))? "
    r"(?P<description>.+)$"
)
MARKDOWN_HEADING_REGEX = re.compile(r"^(?P<marker>#{1,6})\s+(?P<title>.*?)\s*#*\s*$")


@dataclass
class _TextNode:
    description: str
    order: int
    status: int
    priority: int
    optional: bool
    milestone: int
    completion: float
    line_number: int
    children: list[_TextNode] = field(default_factory=list)


class TextParser:
    @staticmethod
    def parse_roadmap(source: str) -> Roadmap:
        return Roadmap(_parse_text_nodes(source))


class MarkdownParser:
    @staticmethod
    def parse_roadmap(source: str) -> Roadmap:
        return Roadmap(_parse_markdown_nodes(source))


def _parse_text_nodes(source: str) -> list[Task | TaskGroup]:
    roots: list[_TextNode] = []
    stack: list[tuple[int, _TextNode]] = []

    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        if "\t" in raw_line:
            msg = f"line {line_number}: tabs are invalid"
            raise ValueError(msg)

        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            if stripped.startswith("#") and _is_description_continuation(stack, raw_line):
                msg = f"line {line_number}: headings are not allowed in task descriptions"
                raise ValueError(msg)
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            msg = f"line {line_number}: indentation must use multiples of two spaces"
            raise ValueError(msg)
        level = indent // 2

        node = _parse_text_task_line(raw_line, line_number)
        if node is None:
            _append_text_continuation(stack, raw_line, level, line_number)
            continue

        while stack and stack[-1][0] >= level:
            stack.pop()

        if level > 0 and (not stack or stack[-1][0] != level - 1):
            msg = f"line {line_number}: task indentation cannot skip levels"
            raise ValueError(msg)

        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((level, node))

    _validate_text_order_sequence(roots)
    return [_text_node_to_item(node) for node in roots]


def _parse_text_task_line(raw_line: str, line_number: int) -> _TextNode | None:
    match = TASK_LINE_REGEX.match(raw_line)
    if match is None:
        return None

    if match.group("status") is not None:
        order_marker = match.group("order")
        status_marker = match.group("status")
        meta_marker = match.group("meta")
        milestone_marker = match.group("milestone")
        description = match.group("description")
    else:
        order_marker = match.group("omitted_order")
        status_marker = None
        meta_marker = match.group("omitted_meta")
        milestone_marker = match.group("omitted_milestone")
        description = match.group("omitted_description")
        if description.startswith("["):
            msg = f"line {line_number}: malformed status or metadata marker"
            raise ValueError(msg)
    if description.startswith("("):
        msg = f"line {line_number}: malformed milestone marker"
        raise ValueError(msg)

    order = _parse_text_order(order_marker)
    status, completion = _parse_status_marker(status_marker, line_number)
    priority, optional = _parse_text_metadata(meta_marker, line_number)
    milestone = _parse_text_milestone(milestone_marker, line_number)
    if status == COMPLETED and not optional:
        priority = DEFAULT_PRIORITY

    return _TextNode(
        description=description,
        order=order,
        status=status,
        priority=priority,
        optional=optional,
        milestone=milestone,
        completion=completion,
        line_number=line_number,
    )


def _parse_text_order(marker: str) -> int:
    if marker == "-":
        return UNSORTED
    if marker.endswith("."):
        return int(marker[:-1])
    return int(marker)


def _parse_status_marker(marker: str | None, line_number: int) -> tuple[int, float]:
    if marker is None or marker == "[ ]":
        return NOT_STARTED, 0.0
    if marker == "[~]":
        return ONGOING, 0.0
    if marker in {"[x]", "[X]"}:
        return COMPLETED, 0.0

    if marker.startswith("[~") and marker.endswith("]"):
        return ONGOING, _parse_completion_marker(marker[2:-1], line_number)

    msg = f"line {line_number}: malformed status marker"
    raise ValueError(msg)


def _parse_completion_marker(marker: str, line_number: int) -> float:
    if not re.fullmatch(r"[1-9]\d?\.\d%", marker):
        msg = f"line {line_number}: ongoing completion must use one decimal percent"
        raise ValueError(msg)

    completion = float(marker[:-1])
    if not 1.0 <= completion <= 99.0:
        msg = f"line {line_number}: ongoing completion must be between 1.0 and 99.0"
        raise ValueError(msg)
    return completion


def _parse_text_metadata(marker: str | None, line_number: int) -> tuple[int, bool]:
    if marker is None:
        return DEFAULT_PRIORITY, False
    if marker == "?":
        return OPTIONAL_TASK, True
    if marker == "!":
        return MAX_PRIORITY, False
    priority = int(marker[1:])
    if priority <= DEFAULT_PRIORITY:
        msg = f"line {line_number}: priority must be a positive integer"
        raise ValueError(msg)
    return priority, False


def _parse_text_milestone(marker: str | None, line_number: int) -> int:
    if marker is None:
        return NO_MILESTONE
    raw_value = marker[1:-1]
    if not raw_value.isdecimal():
        msg = f"line {line_number}: milestone must be a positive integer"
        raise ValueError(msg)
    milestone = int(raw_value)
    if milestone <= NO_MILESTONE:
        msg = f"line {line_number}: milestone must be a positive integer"
        raise ValueError(msg)
    return milestone


def _append_text_continuation(
    stack: list[tuple[int, _TextNode]],
    raw_line: str,
    level: int,
    line_number: int,
) -> None:
    if not stack:
        msg = f"line {line_number}: continuation line has no task"
        raise ValueError(msg)

    parent_level, parent = stack[-1]
    if level <= parent_level:
        msg = f"line {line_number}: expected a task line"
        raise ValueError(msg)
    line = _unescape_text_description_line(raw_line.strip())
    _validate_description_line(line, f"line {line_number}", ValueError)
    parent.description = f"{parent.description}\n{line}"


def _is_description_continuation(
    stack: list[tuple[int, _TextNode]],
    raw_line: str,
) -> bool:
    if not stack:
        return False
    indent = len(raw_line) - len(raw_line.lstrip(" "))
    if indent % 2 != 0:
        return False
    return indent // 2 > stack[-1][0]


def _validate_text_order_sequence(nodes: list[_TextNode]) -> None:
    expected_order = 1
    for node in nodes:
        if node.order != UNSORTED:
            if node.order != expected_order:
                msg = (
                    f"line {node.line_number}: numbered items must be sequential; "
                    f"expected {expected_order}."
                )
                raise ValueError(msg)
            expected_order += 1
        _validate_text_order_sequence(node.children)


def _text_node_to_item(
    node: _TextNode,
    inherited_milestone: int = NO_MILESTONE,
) -> Task | TaskGroup:
    milestone = node.milestone or inherited_milestone
    if node.children:
        if node.completion:
            msg = f"line {node.line_number}: task groups cannot define explicit completion"
            raise ValueError(msg)
        return TaskGroup(
            node.description,
            order=node.order,
            priority=node.priority,
            optional=node.optional,
            milestone=milestone,
            tasks=[_text_node_to_item(child, milestone) for child in node.children],
        )
    return Task(
        node.description,
        order=node.order,
        priority=node.priority,
        status=node.status,
        optional=node.optional,
        milestone=milestone,
        completion=node.completion,
    )


def _unescape_text_description_line(line: str) -> str:
    if re.match(r"^\\([*+-]|\d+[.)])\s", line):
        return line[1:]
    return line


def _parse_markdown_nodes(source: str) -> list[Task | TaskGroup]:
    roadmap_source = _extract_markdown_roadmap_source(source)
    roots: list[_TextNode] = []
    stack: list[tuple[int, _TextNode]] = []

    for line_number, raw_line in roadmap_source:
        if "\t" in raw_line:
            msg = f"line {line_number}: tabs are invalid"
            raise ValueError(msg)

        if not raw_line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            msg = f"line {line_number}: indentation must use multiples of two spaces"
            raise ValueError(msg)
        level = indent // 2

        node = _parse_markdown_task_line(raw_line, line_number)
        if node is None:
            _append_markdown_continuation(stack, raw_line, level, line_number)
            continue

        while stack and stack[-1][0] >= level:
            stack.pop()

        if level > 0 and (not stack or stack[-1][0] != level - 1):
            msg = f"line {line_number}: task indentation cannot skip levels"
            raise ValueError(msg)

        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((level, node))

    _validate_text_order_sequence(roots)
    return [_text_node_to_item(node) for node in roots]


def _extract_markdown_roadmap_source(source: str) -> list[tuple[int, str]]:
    lines = list(enumerate(source.splitlines(), start=1))
    headings: list[tuple[int, int, int]] = []

    for index, (_line_number, line) in enumerate(lines):
        match = MARKDOWN_HEADING_REGEX.match(line)
        if match is None:
            continue
        level = len(match.group("marker"))
        title = match.group("title").strip()
        if title.casefold() == "roadmap":
            headings.append((level, index, _line_number))

    if not headings:
        if any(MARKDOWN_HEADING_REGEX.match(line) for _line_number, line in lines):
            msg = "Markdown documents must contain a Roadmap heading"
            raise ValueError(msg)
        return lines

    selected_level, selected_index, _selected_line_number = min(
        headings,
        key=lambda heading: (heading[0], heading[1]),
    )
    end_index = len(lines)
    for index in range(selected_index + 1, len(lines)):
        match = MARKDOWN_HEADING_REGEX.match(lines[index][1])
        if match is not None and len(match.group("marker")) <= selected_level:
            end_index = index
            break
    return lines[selected_index + 1 : end_index]


def _parse_markdown_task_line(raw_line: str, line_number: int) -> _TextNode | None:
    match = MARKDOWN_TASK_LINE_REGEX.match(raw_line)
    if match is None:
        return None

    order = _parse_text_order(match.group("order"))
    status, completion = _parse_status_marker(match.group("status"), line_number)
    priority, optional, milestone = _parse_markdown_metadata(
        match.group("meta"),
        line_number,
    )
    if status == COMPLETED and not optional:
        priority = DEFAULT_PRIORITY

    return _TextNode(
        description=_unescape_markdown_description_line(match.group("description")),
        order=order,
        status=status,
        priority=priority,
        optional=optional,
        milestone=milestone,
        completion=completion,
        line_number=line_number,
    )


def _parse_markdown_metadata(
    marker: str | None,
    line_number: int,
) -> tuple[int, bool, int]:
    if marker is None:
        return DEFAULT_PRIORITY, False, NO_MILESTONE

    content = marker[1:-1]
    if not content:
        msg = f"line {line_number}: metadata tuple cannot be empty"
        raise ValueError(msg)

    if ":" in content:
        priority_text, milestone_text = content.split(":", 1)
        milestone = _parse_markdown_metadata_milestone(milestone_text, line_number)
    else:
        priority_text = content
        milestone = NO_MILESTONE

    if priority_text == "":
        return DEFAULT_PRIORITY, False, milestone
    if priority_text == "?":
        return OPTIONAL_TASK, True, milestone
    if priority_text == "!":
        return MAX_PRIORITY, False, milestone
    if not priority_text.isdecimal():
        msg = f"line {line_number}: priority metadata must be !, ?, or a positive integer"
        raise ValueError(msg)
    priority = int(priority_text)
    if priority <= DEFAULT_PRIORITY:
        msg = f"line {line_number}: priority metadata must be a positive integer"
        raise ValueError(msg)
    return priority, False, milestone


def _parse_markdown_metadata_milestone(value: str, line_number: int) -> int:
    if not value.isdecimal():
        msg = f"line {line_number}: milestone metadata must be a positive integer"
        raise ValueError(msg)
    milestone = int(value)
    if milestone <= NO_MILESTONE:
        msg = f"line {line_number}: milestone metadata must be a positive integer"
        raise ValueError(msg)
    return milestone


def _append_markdown_continuation(
    stack: list[tuple[int, _TextNode]],
    raw_line: str,
    level: int,
    line_number: int,
) -> None:
    if not stack:
        msg = f"line {line_number}: expected a Markdown roadmap task line"
        raise ValueError(msg)

    parent_level, parent = stack[-1]
    if level <= parent_level:
        msg = f"line {line_number}: expected a Markdown roadmap task line"
        raise ValueError(msg)
    line = _unescape_markdown_description_line(raw_line.strip())
    _validate_description_line(line, f"line {line_number}", ValueError)
    parent.description = f"{parent.description}\n{line}"


def _unescape_markdown_description_line(line: str) -> str:
    if re.match(r"^\\([*+-]|\d+[.)])\s", line):
        return line[1:]
    return line
