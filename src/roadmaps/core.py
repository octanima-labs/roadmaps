from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

NOT_STARTED = 0
ONGOING = 1
COMPLETED = 2
VALID_STATUSES = {NOT_STARTED, ONGOING, COMPLETED}

DEFAULT_PRIORITY = 0
MAX_PRIORITY = 999

OPTIONAL_TASK = -1
UNSORTED = -1
NO_MILESTONE = 0

TASK_JSON_KEYS = {
    "completion_date",
    "completion",
    "description",
    "milestone",
    "optional",
    "order",
    "priority",
    "start_date",
    "status",
}
TASK_JSON_OPTIONAL_KEYS = {"completion_date", "start_date"}
TASK_GROUP_JSON_KEYS = TASK_JSON_KEYS | {"tasks"}
ROADMAP_JSON_KEYS = {"completion", "steps"}
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


class JSONValidationError(ValueError):
    """Raised when roadmap JSON cannot be decoded or validated."""


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


@dataclass(init=False)
class Task:
    description: str
    order: int
    priority: int
    optional: bool
    milestone: int
    _status: int = field(repr=False)
    _completion: float = field(repr=False)
    _start_date: datetime | None = field(repr=False)
    _completion_date: datetime | None = field(repr=False)

    def __init__(
        self,
        description: str,
        order: int = UNSORTED,
        priority: int = DEFAULT_PRIORITY,
        status: int = NOT_STARTED,
        optional: bool = False,
        milestone: int = NO_MILESTONE,
        completion: float = 0.0,
        start_date: datetime | None = None,
        completion_date: datetime | None = None,
    ) -> None:
        self.description = description
        self.order = order
        self.priority = priority
        self.optional = optional
        self.milestone = milestone
        self._status = status
        self._completion = completion
        self._start_date = start_date
        self._completion_date = completion_date
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            msg = "description must be a non-empty string"
            raise ValueError(msg)
        _validate_description(self.description, "description", ValueError)
        if self.order < UNSORTED:
            msg = "order must be UNSORTED or a non-negative integer"
            raise ValueError(msg)
        if self.milestone < NO_MILESTONE:
            msg = "milestone must be a non-negative integer"
            raise ValueError(msg)
        if self._status not in VALID_STATUSES:
            msg = "status must be NOT_STARTED, ONGOING, or COMPLETED"
            raise ValueError(msg)
        self._completion = _validated_task_completion(
            self._completion,
            self._status,
            "completion",
            ValueError,
        )
        self._start_date = _normalize_datetime(
            self._start_date,
            "start_date",
            ValueError,
        )
        self._completion_date = _normalize_datetime(
            self._completion_date,
            "completion_date",
            ValueError,
        )
        _validate_task_dates(
            self._status,
            self._start_date,
            self._completion_date,
            "date",
            ValueError,
        )

        if self.priority == OPTIONAL_TASK:
            self.optional = True
        if self.optional:
            if self.priority not in {DEFAULT_PRIORITY, OPTIONAL_TASK}:
                msg = "optional tasks cannot also have a positive priority"
                raise ValueError(msg)
            self.priority = OPTIONAL_TASK
        elif self.priority < DEFAULT_PRIORITY:
            msg = "priority must be non-negative unless the task is optional"
            raise ValueError(msg)

    @property
    def status(self) -> int:
        return self._status

    @property
    def completion(self) -> float:
        if self.status == COMPLETED:
            return 100.0
        if self.status == ONGOING:
            return self._completion
        return 0.0

    @property
    def completion_percent(self) -> str:
        return _format_completion_percent(self.completion)

    @property
    def start_date(self) -> datetime | None:
        return self._start_date

    @property
    def completion_date(self) -> datetime | None:
        return self._completion_date

    def is_optional(self) -> bool:
        return self.optional

    def set_optional(self, optional: bool = True) -> None:
        self.optional = optional
        if optional:
            self.priority = OPTIONAL_TASK
        elif self.priority == OPTIONAL_TASK:
            self.priority = DEFAULT_PRIORITY

    def set_priority(self, priority: int) -> None:
        if priority < DEFAULT_PRIORITY:
            msg = "priority must be non-negative"
            raise ValueError(msg)
        if self.optional and priority > DEFAULT_PRIORITY:
            msg = "optional tasks cannot also have a positive priority"
            raise ValueError(msg)
        self.priority = priority

    def mark_not_started(self) -> None:
        self._status = NOT_STARTED
        self._completion = 0.0
        self._start_date = None
        self._completion_date = None

    def mark_ongoing(
        self,
        completion: float = 0.0,
        timestamp: datetime | None = None,
    ) -> None:
        self._status = ONGOING
        self._completion = _validated_task_completion(
            completion,
            ONGOING,
            "completion",
            ValueError,
        )
        self._completion_date = None
        if self._start_date is None:
            self._start_date = _timestamp_or_now(timestamp)

    def mark_completed(self, timestamp: datetime | None = None) -> None:
        completed_at = _timestamp_or_now(timestamp)
        self._status = COMPLETED
        self._completion = 0.0
        if self._start_date is None:
            self._start_date = completed_at
        self._completion_date = completed_at
        if not self.optional:
            self.priority = DEFAULT_PRIORITY

    def to_group(
        self,
        tasks: Iterable[Task | TaskGroup] | None = None,
    ) -> TaskGroup:
        return TaskGroup(
            self.description,
            order=self.order,
            priority=self.priority,
            optional=self.optional,
            milestone=self.milestone,
            tasks=tasks,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "description": self.description,
            "order": self.order,
            "status": self.status,
            "priority": self.priority,
            "optional": self.optional,
            "milestone": self.milestone,
            "completion": self.completion,
        }
        if self.start_date is not None:
            data["start_date"] = _datetime_to_json(self.start_date)
        if self.completion_date is not None:
            data["completion_date"] = _datetime_to_json(self.completion_date)
        return data

    @classmethod
    def from_dict(cls, data: object) -> Task:
        if cls is not Task:
            return cls.from_dict(data)
        if _is_json_group(data):
            msg = "$.tasks: unexpected field for Task"
            raise JSONValidationError(msg)
        return _task_from_mapping(_require_mapping(data, "$"), "$")

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, source: str) -> Task:
        return cls.from_dict(_loads_json(source))


@dataclass(init=False)
class TaskGroup(Task):
    tasks: list[Task | TaskGroup]

    def __init__(
        self,
        description: str,
        order: int = UNSORTED,
        priority: int = DEFAULT_PRIORITY,
        optional: bool = False,
        milestone: int = NO_MILESTONE,
        tasks: Iterable[Task | TaskGroup] | None = None,
    ) -> None:
        super().__init__(
            description=description,
            order=order,
            priority=priority,
            status=NOT_STARTED,
            optional=optional,
            milestone=milestone,
        )
        self.tasks = []
        for task in tasks or []:
            self.add_task(task)

    @property
    def status(self) -> int:
        if not self.tasks:
            return NOT_STARTED

        mandatory_tasks = [task for task in self.tasks if not task.is_optional()]
        if not mandatory_tasks or all(
            task.status == COMPLETED for task in mandatory_tasks
        ):
            return COMPLETED
        if any(task.status in {ONGOING, COMPLETED} for task in self.tasks):
            return ONGOING
        return NOT_STARTED

    @property
    def completion(self) -> float:
        if not self.tasks:
            return 0.0

        mandatory_tasks = [task for task in self.tasks if not task.is_optional()]
        if not mandatory_tasks:
            return 100.0
        return sum(task.completion for task in mandatory_tasks) / len(mandatory_tasks)

    @property
    def start_date(self) -> datetime | None:
        dates = [task.start_date for task in self.leaf_tasks() if task.start_date is not None]
        if not dates:
            return None
        return min(dates)

    @property
    def completion_date(self) -> datetime | None:
        if self.status != COMPLETED:
            return None
        dates = [
            task.completion_date
            for task in _mandatory_leaf_tasks(self.tasks)
            if task.completion_date is not None
        ]
        if not dates:
            return None
        return max(dates)

    def add_task(self, task: Task | TaskGroup) -> None:
        if not isinstance(task, Task):
            msg = "task must be a Task or TaskGroup"
            raise TypeError(msg)
        self.tasks.append(task)

    def task_to_group(
        self,
        task: Task,
        tasks: Iterable[Task | TaskGroup] | None = None,
    ) -> TaskGroup:
        group = _task_to_group_in_items(self.tasks, task, tasks)
        if group is None:
            msg = "task was not found in this task group"
            raise ValueError(msg)
        return group

    def group_to_task(self, group: TaskGroup) -> Task:
        task = _group_to_task_in_items(self.tasks, group)
        if task is None:
            msg = "task group was not found in this task group"
            raise ValueError(msg)
        return task

    def leaf_tasks(self) -> list[Task]:
        return list(_leaf_tasks(self.tasks))

    def mark_not_started(self) -> None:
        for task in self.tasks:
            task.mark_not_started()

    def mark_ongoing(
        self,
        completion: float = 0.0,
        timestamp: datetime | None = None,
    ) -> None:
        if completion:
            msg = "task groups cannot define explicit completion"
            raise ValueError(msg)
        for task in self.leaf_tasks():
            if task.status != COMPLETED:
                task.mark_ongoing(timestamp=timestamp)
                return

    def mark_completed(self, timestamp: datetime | None = None) -> None:
        for task in self.tasks:
            if not task.is_optional():
                task.mark_completed(timestamp=timestamp)

    def to_task(self) -> Task:
        return Task(
            self.description,
            order=self.order,
            priority=self.priority,
            status=self.status,
            optional=self.optional,
            milestone=self.milestone,
            start_date=self.start_date,
            completion_date=self.completion_date,
        )

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["tasks"] = [task.to_dict() for task in self.tasks]
        return data

    @classmethod
    def from_dict(cls, data: object) -> TaskGroup:
        mapping = _require_mapping(data, "$")
        return _task_group_from_mapping(mapping, "$")

    @classmethod
    def from_json(cls, source: str) -> TaskGroup:
        return cls.from_dict(_loads_json(source))


@dataclass
class Roadmap:
    steps: list[Task | TaskGroup] = field(default_factory=list)

    @property
    def completion(self) -> float:
        if not self.steps:
            return 0.0

        mandatory_steps = [step for step in self.steps if not step.is_optional()]
        if not mandatory_steps:
            return 100.0
        return sum(step.completion for step in mandatory_steps) / len(mandatory_steps)

    @property
    def completion_percent(self) -> str:
        return _format_completion_percent(self.completion)

    def add_step(self, task: Task | TaskGroup) -> None:
        if not isinstance(task, Task):
            msg = "task must be a Task or TaskGroup"
            raise TypeError(msg)
        self.steps.append(task)

    def task_to_group(
        self,
        task: Task,
        tasks: Iterable[Task | TaskGroup] | None = None,
    ) -> TaskGroup:
        group = _task_to_group_in_items(self.steps, task, tasks)
        if group is None:
            msg = "task was not found in this roadmap"
            raise ValueError(msg)
        return group

    def group_to_task(self, group: TaskGroup) -> Task:
        task = _group_to_task_in_items(self.steps, group)
        if task is None:
            msg = "task group was not found in this roadmap"
            raise ValueError(msg)
        return task

    def leaf_tasks(self) -> list[Task]:
        return list(_leaf_tasks(self.steps))

    def milestones(
        self,
        index: int | None = None,
        completed: bool | None = None,
    ) -> dict[int, list[Task]]:
        grouped: dict[int, list[Task]] = {}
        for task in self.leaf_tasks():
            if task.milestone == NO_MILESTONE:
                continue
            if index is not None and task.milestone != index:
                continue
            if completed is True and task.status != COMPLETED:
                continue
            if completed is False and task.status == COMPLETED:
                continue
            grouped.setdefault(task.milestone, []).append(task)
        return grouped

    def show_steps(
        self,
        completed: bool | None = None,
        optional: bool | None = None,
        description: str | None = None,
    ) -> list[Task]:
        tasks = self.leaf_tasks()
        if completed is not None:
            tasks = [task for task in tasks if (task.status == COMPLETED) is completed]
        if optional is not None:
            tasks = [task for task in tasks if task.is_optional() is optional]
        if description is not None:
            tasks = [task for task in tasks if description in task.description]
        return tasks

    def filter_items(
        self,
        *,
        completed: bool = False,
        uncompleted: bool = False,
        ongoing: bool = False,
        optional: bool = False,
        all: bool = False,
        categories: Iterable[str] | None = None,
    ) -> list[Task | TaskGroup]:
        items = list(_walk_items(self.steps))
        if all:
            return items

        category_set = {category.casefold() for category in categories or []}
        status_filter = _filter_statuses(completed, uncompleted, ongoing)
        return [
            item
            for item in items
            if _matches_filter_item(item, status_filter, optional, category_set)
        ]

    def next_step(self) -> list[Task]:
        return sorted(
            (task for task in self.leaf_tasks() if task.status != COMPLETED),
            key=_next_step_key,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "completion": self.completion,
        }

    @classmethod
    def from_dict(cls, data: object) -> Roadmap:
        mapping = _require_mapping(data, "$")
        _validate_keys(mapping, ROADMAP_JSON_KEYS, "$")
        _validate_completion(_require_number(mapping["completion"], "$.completion"), "$.completion")
        steps = _require_list(mapping["steps"], "$.steps")
        return cls(
            [_item_from_mapping(_require_mapping(step, f"$.steps[{index}]"), f"$.steps[{index}]") for index, step in enumerate(steps)]
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, source: str) -> Roadmap:
        return cls.from_dict(_loads_json(source))

    def to_text(self) -> str:
        return "\n".join(_render_text_item(step, 0) for step in self.steps)

    @classmethod
    def from_text(cls, source: str) -> Roadmap:
        return cls(_parse_text_nodes(source))

    def to_markdown(self) -> str:
        return "\n".join(_render_markdown_item(step, 0) for step in self.steps)

    @classmethod
    def from_markdown(cls, source: str) -> Roadmap:
        return cls(_parse_markdown_nodes(source))


def _leaf_tasks(items: Iterable[Task | TaskGroup]) -> Iterable[Task]:
    for item in items:
        if isinstance(item, TaskGroup):
            yield from _leaf_tasks(item.tasks)
        else:
            yield item


def _mandatory_leaf_tasks(items: Iterable[Task | TaskGroup]) -> Iterable[Task]:
    for item in items:
        if item.is_optional():
            continue
        if isinstance(item, TaskGroup):
            yield from _mandatory_leaf_tasks(item.tasks)
        else:
            yield item


def _walk_items(items: Iterable[Task | TaskGroup]) -> Iterable[Task | TaskGroup]:
    for item in items:
        yield item
        if isinstance(item, TaskGroup):
            yield from _walk_items(item.tasks)


def _filter_statuses(
    completed: bool,
    uncompleted: bool,
    ongoing: bool,
) -> set[int] | None:
    statuses: set[int] = set()
    if completed:
        statuses.add(COMPLETED)
    if uncompleted:
        statuses.update({NOT_STARTED, ONGOING})
    if ongoing:
        statuses.add(ONGOING)
    return statuses or None


def _matches_filter_item(
    item: Task | TaskGroup,
    statuses: set[int] | None,
    include_optional: bool,
    categories: set[str],
) -> bool:
    if categories and _description_category(item.description) not in categories:
        return False

    status_matches = statuses is None or item.status in statuses
    optional_matches = include_optional and item.is_optional()
    if not status_matches and not optional_matches:
        return False

    return include_optional or not item.is_optional()


def _description_category(description: str) -> str | None:
    first_line = description.splitlines()[0]
    match = re.match(r"^(?P<category>[A-Za-z][\w-]*(?:\([^):]+\))?):", first_line)
    if match is None:
        return None
    return match.group("category").casefold()


def _task_to_group_in_items(
    items: list[Task | TaskGroup],
    target: Task,
    tasks: Iterable[Task | TaskGroup] | None,
) -> TaskGroup | None:
    if isinstance(target, TaskGroup):
        return None

    for index, item in enumerate(items):
        if item is target:
            group = target.to_group(tasks)
            items[index] = group
            return group
        if isinstance(item, TaskGroup):
            converted = _task_to_group_in_items(item.tasks, target, tasks)
            if converted is not None:
                return converted
    return None


def _group_to_task_in_items(
    items: list[Task | TaskGroup],
    target: TaskGroup,
) -> Task | None:
    for index, item in enumerate(items):
        if item is target:
            task = target.to_task()
            items[index : index + 1] = [task, *target.tasks]
            return task
        if isinstance(item, TaskGroup):
            converted = _group_to_task_in_items(item.tasks, target)
            if converted is not None:
                return converted
    return None


def _next_step_key(task: Task) -> tuple[int, int, int, int]:
    status_rank = 0 if task.status == ONGOING else 1
    order_rank = 0 if task.order != UNSORTED else 1
    order_value = task.order if task.order != UNSORTED else 0
    return (-task.priority, status_rank, order_rank, order_value)


def _validated_task_completion(
    value: float,
    status: int,
    path: str,
    error_type: type[ValueError],
) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{path}: must be a number"
        raise error_type(msg)

    completion = float(value)
    if not _has_one_decimal_place(completion):
        msg = f"{path}: must use at most one decimal place"
        raise error_type(msg)

    if status == ONGOING:
        if completion == 0.0:
            return 0.0
        if 1.0 <= completion <= 99.0:
            return completion
        msg = f"{path}: ongoing completion must be between 1.0 and 99.0"
        raise error_type(msg)
    if status == NOT_STARTED:
        if completion == 0.0:
            return 0.0
        msg = f"{path}: not-started tasks must use 0.0 completion"
        raise error_type(msg)
    if completion in {0.0, 100.0}:
        return 0.0
    msg = f"{path}: completed tasks must use 100.0 completion"
    raise error_type(msg)


def _has_one_decimal_place(value: float) -> bool:
    return round(value, 1) == value


def _format_completion_percent(completion: float) -> str:
    if completion.is_integer():
        return f"{int(completion)}%"
    return f"{completion:.1f}%"


def _timestamp_or_now(timestamp: datetime | None) -> datetime:
    if timestamp is None:
        return datetime.now(UTC)
    normalized = _normalize_datetime(timestamp, "timestamp", ValueError)
    if normalized is None:  # pragma: no cover - timestamp is known non-None here.
        msg = "timestamp: must be a datetime"
        raise ValueError(msg)
    return normalized


def _normalize_datetime(
    value: datetime | None,
    path: str,
    error_type: type[ValueError],
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        msg = f"{path}: must be a datetime or None"
        raise error_type(msg)
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{path}: must be timezone-aware"
        raise error_type(msg)
    return value.astimezone(UTC)


def _validate_task_dates(
    status: int,
    start_date: datetime | None,
    completion_date: datetime | None,
    path: str,
    error_type: type[ValueError],
) -> None:
    if status == NOT_STARTED and (start_date is not None or completion_date is not None):
        msg = f"{path}: not-started tasks cannot have dates"
        raise error_type(msg)
    if status == ONGOING and completion_date is not None:
        msg = f"{path}: ongoing tasks cannot have a completion_date"
        raise error_type(msg)
    if completion_date is not None and status != COMPLETED:
        msg = f"{path}: completion_date requires completed status"
        raise error_type(msg)
    if (
        start_date is not None
        and completion_date is not None
        and completion_date < start_date
    ):
        msg = f"{path}: completion_date cannot be earlier than start_date"
        raise error_type(msg)


def _datetime_to_json(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _datetime_from_json(value: object, path: str) -> datetime:
    if not isinstance(value, str):
        msg = f"{path}: must be an ISO timestamp string"
        raise JSONValidationError(msg)
    source = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(source)
    except ValueError as exc:
        msg = f"{path}: must be a valid ISO timestamp"
        raise JSONValidationError(msg) from exc
    normalized = _normalize_datetime(parsed, path, JSONValidationError)
    if normalized is None:  # pragma: no cover - parsed is known non-None here.
        msg = f"{path}: must be an ISO timestamp string"
        raise JSONValidationError(msg)
    return normalized


def _validate_description(
    description: str,
    path: str,
    error_type: type[ValueError],
) -> None:
    for line in description.splitlines():
        _validate_description_line(line, path, error_type)


def _validate_description_line(
    line: str,
    path: str,
    error_type: type[ValueError],
) -> None:
    stripped = line.strip()
    if not stripped:
        return
    if stripped.startswith("#"):
        msg = f"{path}: headings are not allowed in task descriptions"
        raise error_type(msg)
    if stripped.startswith((">", "```", "~~~")):
        msg = f"{path}: block Markdown is not allowed in task descriptions"
        raise error_type(msg)
    if _is_markdown_table_separator(stripped):
        msg = f"{path}: Markdown tables are not allowed in task descriptions"
        raise error_type(msg)


def _is_markdown_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell)


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
    parent.description = (
        f"{parent.description}\n{line}"
    )


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


def _unescape_markdown_description_line(line: str) -> str:
    if re.match(r"^\\([*+-]|\d+[.)])\s", line):
        return line[1:]
    return line


def _is_list_breaking_description_line(line: str) -> bool:
    return re.match(r"^([*+-]|\d+[.)])\s", line) is not None


def _loads_json(source: str) -> object:
    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        raise JSONValidationError(msg) from exc


def _is_json_group(data: object) -> bool:
    return isinstance(data, Mapping) and "tasks" in data


def _item_from_mapping(mapping: Mapping[str, object], path: str) -> Task | TaskGroup:
    if "tasks" in mapping:
        return _task_group_from_mapping(mapping, path)
    return _task_from_mapping(mapping, path)


def _task_from_mapping(mapping: Mapping[str, object], path: str) -> Task:
    values = _task_values_from_mapping(
        mapping,
        path,
        TASK_JSON_KEYS,
        load_leaf_completion=True,
    )
    return Task(**values)


def _task_group_from_mapping(mapping: Mapping[str, object], path: str) -> TaskGroup:
    values = _task_values_from_mapping(
        mapping,
        path,
        TASK_GROUP_JSON_KEYS,
        load_leaf_completion=False,
    )
    values.pop("status")
    tasks = _require_list(mapping["tasks"], f"{path}.tasks")
    return TaskGroup(
        **values,
        tasks=[
            _item_from_mapping(
                _require_mapping(task, f"{path}.tasks[{index}]"),
                f"{path}.tasks[{index}]",
            )
            for index, task in enumerate(tasks)
        ],
    )


def _task_values_from_mapping(
    mapping: Mapping[str, object],
    path: str,
    allowed_keys: set[str],
    *,
    load_leaf_completion: bool,
) -> dict[str, Any]:
    _validate_keys(mapping, allowed_keys, path, required_keys=allowed_keys - TASK_JSON_OPTIONAL_KEYS)

    description = _require_str(mapping["description"], f"{path}.description")
    order = _require_int(mapping["order"], f"{path}.order")
    status = _require_int(mapping["status"], f"{path}.status")
    priority = _require_int(mapping["priority"], f"{path}.priority")
    optional = _require_bool(mapping["optional"], f"{path}.optional")
    milestone = _require_int(mapping["milestone"], f"{path}.milestone")
    completion = _require_number(mapping["completion"], f"{path}.completion")
    start_date = _optional_datetime_from_mapping(mapping, "start_date", path)
    completion_date = _optional_datetime_from_mapping(mapping, "completion_date", path)
    _validate_completion(completion, f"{path}.completion")

    if status not in VALID_STATUSES:
        msg = f"{path}.status: must be NOT_STARTED, ONGOING, or COMPLETED"
        raise JSONValidationError(msg)
    if order < UNSORTED:
        msg = f"{path}.order: must be UNSORTED or a non-negative integer"
        raise JSONValidationError(msg)
    if milestone < NO_MILESTONE:
        msg = f"{path}.milestone: must be a non-negative integer"
        raise JSONValidationError(msg)
    if optional and priority != OPTIONAL_TASK:
        msg = f"{path}.priority: optional tasks must use priority {OPTIONAL_TASK}"
        raise JSONValidationError(msg)
    if not optional and priority < DEFAULT_PRIORITY:
        msg = f"{path}.priority: mandatory tasks must use a non-negative priority"
        raise JSONValidationError(msg)
    if status == COMPLETED and not optional and priority != DEFAULT_PRIORITY:
        msg = f"{path}.priority: completed mandatory tasks must use default priority"
        raise JSONValidationError(msg)
    _validate_task_dates(
        status,
        start_date,
        completion_date,
        f"{path}.date",
        JSONValidationError,
    )
    if load_leaf_completion:
        if status == COMPLETED and completion != 100.0:
            msg = f"{path}.completion: completed tasks must use 100.0 completion"
            raise JSONValidationError(msg)
        completion = _validated_task_completion(
            completion,
            status,
            f"{path}.completion",
            JSONValidationError,
        )

    values: dict[str, Any] = {
        "description": description,
        "order": order,
        "priority": priority,
        "status": status,
        "optional": optional,
        "milestone": milestone,
    }
    if load_leaf_completion:
        values["completion"] = completion
        values["start_date"] = start_date
        values["completion_date"] = completion_date
    return values


def _validate_keys(
    mapping: Mapping[str, object],
    allowed_keys: set[str],
    path: str,
    required_keys: set[str] | None = None,
) -> None:
    keys = set(mapping)
    required = allowed_keys if required_keys is None else required_keys
    missing = required - keys
    unknown = keys - allowed_keys
    if missing:
        fields = ", ".join(sorted(missing))
        msg = f"{path}: missing required field(s): {fields}"
        raise JSONValidationError(msg)
    if unknown:
        fields = ", ".join(sorted(unknown))
        msg = f"{path}: unknown field(s): {fields}"
        raise JSONValidationError(msg)


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{path}: must be a JSON object"
        raise JSONValidationError(msg)
    return value


def _require_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        msg = f"{path}: must be a JSON array"
        raise JSONValidationError(msg)
    return value


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        msg = f"{path}: must be a string"
        raise JSONValidationError(msg)
    return value


def _require_int(value: object, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{path}: must be an integer"
        raise JSONValidationError(msg)
    return value


def _require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{path}: must be a boolean"
        raise JSONValidationError(msg)
    return value


def _optional_datetime_from_mapping(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> datetime | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if value is None:
        return None
    return _datetime_from_json(value, f"{path}.{key}")


def _require_number(value: object, path: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{path}: must be a number"
        raise JSONValidationError(msg)
    return float(value)


def _validate_completion(value: float, path: str) -> None:
    if not 0 <= value <= 100:
        msg = f"{path}: must be between 0 and 100"
        raise JSONValidationError(msg)
