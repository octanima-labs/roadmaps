from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from roadmaps._validation import (
    _format_completion_percent,
    _normalize_datetime,
    _timestamp_or_now,
    _validate_description,
    _validate_task_dates,
    _validated_task_completion,
)
from roadmaps.constants import (
    COMPLETED,
    DEFAULT_PRIORITY,
    DEFAULT_TASK_DESCRIPTION,
    DEFAULT_TASK_GROUP_DESCRIPTION,
    NO_MILESTONE,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
    VALID_STATUSES,
)

ItemPath = tuple[int, ...]


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
            _description_or_default_group(self.description),
            order=self.order,
            priority=self.priority,
            optional=self.optional,
            milestone=self.milestone,
            tasks=tasks,
        )

    def to_dict(self) -> dict[str, Any]:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_to_dict(self)

    @classmethod
    def from_dict(cls, data: object) -> Task:
        if cls is not Task:
            return cls.from_dict(data)
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_from_dict(data)

    def to_json(self) -> str:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_to_json(self)

    @classmethod
    def from_json(cls, source: str) -> Task:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_from_json(source)

    def to_yaml(self) -> str:
        from roadmaps.serializers import YamlSerializer

        return YamlSerializer.task_to_yaml(self)

    @classmethod
    def from_yaml(cls, source: str) -> Task:
        from roadmaps.serializers import YamlSerializer

        return YamlSerializer.task_from_yaml(source)


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

    def next(self, count: int = 1) -> list[Task]:
        return _next_tasks(self.leaf_tasks(), count)

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
            _description_or_default_task(self.description),
            order=self.order,
            priority=self.priority,
            status=self.status,
            optional=self.optional,
            milestone=self.milestone,
            start_date=self.start_date,
            completion_date=self.completion_date,
        )

    def to_dict(self) -> dict[str, Any]:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_group_to_dict(self)

    @classmethod
    def from_dict(cls, data: object) -> TaskGroup:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_group_from_dict(data)

    @classmethod
    def from_json(cls, source: str) -> TaskGroup:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_group_from_json(source)

    def to_json(self) -> str:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.task_group_to_json(self)

    def to_yaml(self) -> str:
        from roadmaps.serializers import YamlSerializer

        return YamlSerializer.task_group_to_yaml(self)

    @classmethod
    def from_yaml(cls, source: str) -> TaskGroup:
        from roadmaps.serializers import YamlSerializer

        return YamlSerializer.task_group_from_yaml(source)


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

    def delete_item(self, path: ItemPath) -> Task | TaskGroup:
        _validate_item_path(path)
        deleted = _delete_item_at_path(self.steps, path)
        _renumber_sorted_siblings(self.steps)
        return deleted

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

    def next(self, count: int = 1) -> list[Task]:
        return _next_tasks(self.leaf_tasks(), count)

    def next_step(self) -> list[Task]:
        return self.next()

    def to_dict(self) -> dict[str, Any]:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.roadmap_to_dict(self)

    @classmethod
    def from_dict(cls, data: object) -> Roadmap:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.roadmap_from_dict(data)

    def to_json(self) -> str:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.roadmap_to_json(self)

    @classmethod
    def from_json(cls, source: str) -> Roadmap:
        from roadmaps.serializers import JsonSerializer

        return JsonSerializer.roadmap_from_json(source)

    def to_yaml(self) -> str:
        from roadmaps.serializers import YamlSerializer

        return YamlSerializer.roadmap_to_yaml(self)

    @classmethod
    def from_yaml(cls, source: str) -> Roadmap:
        from roadmaps.serializers import YamlSerializer

        return YamlSerializer.roadmap_from_yaml(source)

    def to_text(self) -> str:
        from roadmaps.renderers import TextRenderer

        return TextRenderer.render_roadmap(self)

    @classmethod
    def from_text(cls, source: str) -> Roadmap:
        from roadmaps.parsers import TextParser

        return TextParser.parse_roadmap(source)

    def to_markdown(self) -> str:
        from roadmaps.renderers import MarkdownRenderer

        return MarkdownRenderer.render_roadmap(self)

    @classmethod
    def from_markdown(cls, source: str) -> Roadmap:
        from roadmaps.parsers import MarkdownParser

        return MarkdownParser.parse_roadmap(source)


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


def _delete_item_at_path(
    items: list[Task | TaskGroup],
    path: ItemPath,
) -> Task | TaskGroup:
    index = path[0]
    if index >= len(items):
        msg = "path index is out of range"
        raise ValueError(msg)
    if len(path) == 1:
        return items.pop(index)

    parent = items[index]
    if not isinstance(parent, TaskGroup):
        msg = "path descends through a leaf task"
        raise ValueError(msg)  # noqa: TRY004 - public path API reports invalid paths as ValueError.

    deleted = _delete_item_at_path(parent.tasks, path[1:])
    if not parent.tasks:
        items[index] = parent.to_task()
    else:
        _renumber_sorted_siblings(parent.tasks)
    _renumber_sorted_siblings(items)
    return deleted


def _validate_item_path(path: ItemPath) -> None:
    if not isinstance(path, tuple) or not path:
        msg = "path must be a non-empty tuple of zero-based indexes"
        raise ValueError(msg)
    if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in path):
        msg = "path must be a non-empty tuple of zero-based indexes"
        raise ValueError(msg)


def _renumber_sorted_siblings(siblings: list[Task | TaskGroup]) -> None:
    order = 1
    for item in siblings:
        if item.order == UNSORTED:
            continue
        item.order = order
        order += 1


def _next_tasks(tasks: Iterable[Task], count: int) -> list[Task]:
    count = _validated_next_count(count)
    ranked = sorted(
        (task for task in tasks if task.status != COMPLETED),
        key=_next_step_key,
    )
    return ranked[:count]


def _description_or_default_group(description: object) -> str:
    if isinstance(description, str) and description.strip():
        return description
    return DEFAULT_TASK_GROUP_DESCRIPTION


def _description_or_default_task(description: object) -> str:
    if isinstance(description, str) and description.strip():
        return description
    return DEFAULT_TASK_DESCRIPTION


def _validated_next_count(count: int) -> int:
    if isinstance(count, bool) or not isinstance(count, int):
        msg = "count must be an integer greater than or equal to 1"
        raise ValueError(msg)  # noqa: TRY004 - public API uses ValueError for all invalid counts.
    if count < 1:
        msg = "count must be an integer greater than or equal to 1"
        raise ValueError(msg)
    return count


def _next_step_key(task: Task) -> tuple[int, int, int, int, int]:
    optional_rank = 1 if task.is_optional() else 0
    status_rank = 0 if task.status == ONGOING else 1
    order_rank = 0 if task.order != UNSORTED else 1
    order_value = task.order if task.order != UNSORTED else 0
    return (-task.priority, optional_rank, status_rank, order_rank, order_value)
