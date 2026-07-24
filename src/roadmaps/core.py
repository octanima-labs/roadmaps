from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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
    "completion",
    "description",
    "milestone",
    "optional",
    "order",
    "priority",
    "status",
}
TASK_GROUP_JSON_KEYS = TASK_JSON_KEYS | {"tasks"}
ROADMAP_JSON_KEYS = {"completion", "steps"}


class JSONValidationError(ValueError):
    """Raised when roadmap JSON cannot be decoded or validated."""


@dataclass(init=False)
class Task:
    description: str
    order: int
    priority: int
    optional: bool
    milestone: int
    _status: int = field(repr=False)

    def __init__(
        self,
        description: str,
        order: int = UNSORTED,
        priority: int = DEFAULT_PRIORITY,
        status: int = NOT_STARTED,
        optional: bool = False,
        milestone: int = NO_MILESTONE,
    ) -> None:
        self.description = description
        self.order = order
        self.priority = priority
        self.optional = optional
        self.milestone = milestone
        self._status = status
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            msg = "description must be a non-empty string"
            raise ValueError(msg)
        if self.order < UNSORTED:
            msg = "order must be UNSORTED or a non-negative integer"
            raise ValueError(msg)
        if self.milestone < NO_MILESTONE:
            msg = "milestone must be a non-negative integer"
            raise ValueError(msg)
        if self._status not in VALID_STATUSES:
            msg = "status must be NOT_STARTED, ONGOING, or COMPLETED"
            raise ValueError(msg)

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
        return 100.0 if self.status == COMPLETED else 0.0

    @property
    def completion_percent(self) -> str:
        return f"{int(self.completion)}%"

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

    def mark_ongoing(self) -> None:
        self._status = ONGOING

    def mark_completed(self) -> None:
        self._status = COMPLETED
        if not self.optional:
            self.priority = DEFAULT_PRIORITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "order": self.order,
            "status": self.status,
            "priority": self.priority,
            "optional": self.optional,
            "milestone": self.milestone,
            "completion": self.completion,
        }

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

    def add_task(self, task: Task | TaskGroup) -> None:
        if not isinstance(task, Task):
            msg = "task must be a Task or TaskGroup"
            raise TypeError(msg)
        self.tasks.append(task)

    def leaf_tasks(self) -> list[Task]:
        return list(_leaf_tasks(self.tasks))

    def mark_not_started(self) -> None:
        for task in self.tasks:
            task.mark_not_started()

    def mark_ongoing(self) -> None:
        for task in self.leaf_tasks():
            if task.status != COMPLETED:
                task.mark_ongoing()
                return

    def mark_completed(self) -> None:
        for task in self.tasks:
            if not task.is_optional():
                task.mark_completed()

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
        return f"{int(self.completion)}%"

    def add_step(self, task: Task | TaskGroup) -> None:
        if not isinstance(task, Task):
            msg = "task must be a Task or TaskGroup"
            raise TypeError(msg)
        self.steps.append(task)

    def leaf_tasks(self) -> list[Task]:
        return list(_leaf_tasks(self.steps))

    def milestones(
        self,
        index: int | None = None,
        completed: bool | None = None,
    ) -> dict[int, list[Task | TaskGroup]]:
        grouped: dict[int, list[Task | TaskGroup]] = {}
        for item in _walk_items(self.steps):
            if item.milestone == NO_MILESTONE:
                continue
            if index is not None and item.milestone != index:
                continue
            if completed is True and item.status != COMPLETED:
                continue
            if completed is False and item.status == COMPLETED:
                continue
            grouped.setdefault(item.milestone, []).append(item)
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
        _validate_completion(mapping["completion"], "$.completion")
        steps = _require_list(mapping["steps"], "$.steps")
        return cls(
            [_item_from_mapping(_require_mapping(step, f"$.steps[{index}]"), f"$.steps[{index}]") for index, step in enumerate(steps)]
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, source: str) -> Roadmap:
        return cls.from_dict(_loads_json(source))


def _leaf_tasks(items: Iterable[Task | TaskGroup]) -> Iterable[Task]:
    for item in items:
        if isinstance(item, TaskGroup):
            yield from _leaf_tasks(item.tasks)
        else:
            yield item


def _walk_items(items: Iterable[Task | TaskGroup]) -> Iterable[Task | TaskGroup]:
    for item in items:
        yield item
        if isinstance(item, TaskGroup):
            yield from _walk_items(item.tasks)


def _next_step_key(task: Task) -> tuple[int, int, int, int]:
    status_rank = 0 if task.status == ONGOING else 1
    order_rank = 0 if task.order != UNSORTED else 1
    order_value = task.order if task.order != UNSORTED else 0
    return (-task.priority, status_rank, order_rank, order_value)


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
    values = _task_values_from_mapping(mapping, path, TASK_JSON_KEYS)
    return Task(**values)


def _task_group_from_mapping(mapping: Mapping[str, object], path: str) -> TaskGroup:
    values = _task_values_from_mapping(mapping, path, TASK_GROUP_JSON_KEYS)
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
) -> dict[str, Any]:
    _validate_keys(mapping, allowed_keys, path)

    description = _require_str(mapping["description"], f"{path}.description")
    order = _require_int(mapping["order"], f"{path}.order")
    status = _require_int(mapping["status"], f"{path}.status")
    priority = _require_int(mapping["priority"], f"{path}.priority")
    optional = _require_bool(mapping["optional"], f"{path}.optional")
    milestone = _require_int(mapping["milestone"], f"{path}.milestone")
    _validate_completion(mapping["completion"], f"{path}.completion")

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

    return {
        "description": description,
        "order": order,
        "priority": priority,
        "status": status,
        "optional": optional,
        "milestone": milestone,
    }


def _validate_keys(
    mapping: Mapping[str, object],
    allowed_keys: set[str],
    path: str,
) -> None:
    keys = set(mapping)
    missing = allowed_keys - keys
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


def _validate_completion(value: object, path: str) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{path}: must be a number"
        raise JSONValidationError(msg)
    if not 0 <= value <= 100:
        msg = f"{path}: must be between 0 and 100"
        raise JSONValidationError(msg)
