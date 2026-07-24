from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

NOT_STARTED = 0
ONGOING = 1
COMPLETED = 2
VALID_STATUSES = {NOT_STARTED, ONGOING, COMPLETED}

DEFAULT_PRIORITY = 0
MAX_PRIORITY = 999

OPTIONAL_TASK = -1
UNSORTED = -1
NO_MILESTONE = 0


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
