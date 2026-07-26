from __future__ import annotations

import re
from dataclasses import dataclass

from roadmaps._validation import _validate_description, _validated_task_completion
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
from roadmaps.model import Roadmap, Task, TaskGroup

Path = tuple[int, ...]
NEW_TASK_DESCRIPTION = "New task"


@dataclass(frozen=True)
class EditorRow:
    path: Path
    depth: int
    item: Task | TaskGroup
    order_text: str
    completion_text: str
    priority_text: str
    milestone_text: str
    description: str
    status: int
    completed: bool
    group: bool


@dataclass
class EditorState:
    roadmap: Roadmap
    selected_path: Path | None = None
    hide_completed: bool = False
    dirty: bool = False

    def __post_init__(self) -> None:
        self.repair_selection()

    @property
    def rows(self) -> list[EditorRow]:
        return _flatten_rows(self.roadmap.steps, self.hide_completed)

    @property
    def selected_row(self) -> EditorRow | None:
        if self.selected_path is None:
            return None
        for row in self.rows:
            if row.path == self.selected_path:
                return row
        return None

    def select_path(self, path: Path) -> bool:
        if self.selected_path == path:
            return False
        if path not in {row.path for row in self.rows}:
            return False
        self.selected_path = path
        return True

    def move_selection(self, delta: int) -> bool:
        rows = self.rows
        if not rows:
            if self.selected_path is None:
                return False
            self.selected_path = None
            return True
        if self.selected_path is None:
            self.selected_path = rows[0].path
            return True

        paths = [row.path for row in rows]
        try:
            index = paths.index(self.selected_path)
        except ValueError:
            self.selected_path = rows[0].path
            return True

        new_index = min(max(index + delta, 0), len(rows) - 1)
        if new_index == index:
            return False
        self.selected_path = rows[new_index].path
        return True

    def toggle_hide_completed(self) -> None:
        previous_rows = self.rows
        self.hide_completed = not self.hide_completed
        self.dirty = True
        self.repair_selection(previous_rows)

    def insert_unsorted_task(self, description: str = NEW_TASK_DESCRIPTION) -> Task:
        task = Task(description, order=UNSORTED)
        siblings, insert_index = self._insertion_location()
        siblings.insert(insert_index, task)
        self.selected_path = self._path_for_inserted_index(insert_index)
        self.dirty = True
        return task

    def insert_sorted_task(self, description: str = NEW_TASK_DESCRIPTION) -> Task:
        task = Task(description, order=1)
        siblings, insert_index = self._insertion_location()
        siblings.insert(insert_index, task)
        _renumber_sorted_siblings(siblings)
        self.selected_path = self._path_for_inserted_index(insert_index)
        self.dirty = True
        return task

    def update_selected_description(self, description: str) -> bool:
        row = self.selected_row
        if row is None:
            return False
        if row.completed:
            msg = "completed rows are read-only except status cycling"
            raise ValueError(msg)

        _validate_description(description, "description", ValueError)
        if row.item.description == description:
            return False
        row.item.description = description
        self.dirty = True
        return True

    def update_selected_milestone(self, milestone: int) -> bool:
        row = self._editable_selected_row()
        if row is None:
            return False
        if milestone < NO_MILESTONE:
            msg = "milestone must be a non-negative integer"
            raise ValueError(msg)
        if row.item.milestone == milestone:
            return False
        row.item.milestone = milestone
        self.dirty = True
        return True

    def update_selected_priority(self, priority: int) -> bool:
        row = self._editable_selected_row()
        if row is None:
            return False

        before = (row.item.priority, row.item.optional)
        if priority == OPTIONAL_TASK:
            row.item.set_optional(True)
        else:
            row.item.set_optional(False)
            row.item.set_priority(priority)
        if (row.item.priority, row.item.optional) == before:
            return False
        self.dirty = True
        return True

    def update_selected_completion(
        self,
        completion: float,
        *,
        allow_start: bool = False,
        allow_completed: bool = False,
    ) -> bool:
        row = self.selected_row
        if row is None:
            return False
        if isinstance(row.item, TaskGroup):
            msg = "completion editing is only available for leaf tasks"
            raise TypeError(msg)
        if row.status == COMPLETED and not allow_completed:
            msg = "completed rows are read-only except status cycling"
            raise ValueError(msg)
        if row.status == NOT_STARTED and not allow_start:
            msg = "not-started tasks must be started before setting completion"
            raise ValueError(msg)

        before = self.roadmap.to_dict()
        row.item.mark_ongoing(completion=completion)
        if self.roadmap.to_dict() == before:
            return False
        self.dirty = True
        self.repair_selection()
        return True

    def adjust_selected_completion(
        self,
        delta: float,
        *,
        allow_start: bool = False,
        allow_completed: bool = False,
        allow_complete: bool = False,
    ) -> bool:
        row = self.selected_row
        if row is None:
            return False
        if isinstance(row.item, TaskGroup):
            msg = "completion editing is only available for leaf tasks"
            raise TypeError(msg)
        if delta == 0.0:
            return False

        if row.status == NOT_STARTED:
            if delta < 0:
                msg = "task is not started"
                raise ValueError(msg)
            if not allow_start:
                msg = "not-started tasks must be started before setting completion"
                raise ValueError(msg)
            return self.update_selected_completion(delta, allow_start=True)

        if row.status == COMPLETED:
            if delta > 0:
                msg = "task is already completed"
                raise ValueError(msg)
            if not allow_completed:
                msg = "completed rows are read-only except status cycling"
                raise ValueError(msg)
            completion = max(0.0, 100.0 + delta)
            return self.update_selected_completion(completion, allow_completed=True)

        completion = row.item.completion + delta
        if completion >= 100.0:
            if not allow_complete:
                msg = "completion would complete task"
                raise ValueError(msg)
            before = self.roadmap.to_dict()
            row.item.mark_completed()
            if self.roadmap.to_dict() == before:
                return False
            self.dirty = True
            self.repair_selection()
            return True

        completion = max(0.0, completion)
        return self.update_selected_completion(completion)

    def cycle_selected_status(self) -> bool:
        row = self.selected_row
        if row is None:
            return False

        previous_rows = self.rows
        before = self.roadmap.to_dict()
        if row.status == NOT_STARTED:
            row.item.mark_ongoing()
        elif row.status == ONGOING:
            row.item.mark_completed()
        else:
            row.item.mark_not_started()

        changed = self.roadmap.to_dict() != before
        if changed:
            self.dirty = True
            self.repair_selection(previous_rows)
        return changed

    def repair_selection(self, previous_rows: list[EditorRow] | None = None) -> None:
        rows = self.rows
        if not rows:
            self.selected_path = None
            return

        if self.selected_path in {row.path for row in rows}:
            return

        previous_index = _row_index(previous_rows or [], self.selected_path)
        if previous_index is None:
            self.selected_path = rows[0].path
            return
        if previous_index < len(rows):
            self.selected_path = rows[previous_index].path
            return
        self.selected_path = rows[-1].path

    def _editable_selected_row(self) -> EditorRow | None:
        row = self.selected_row
        if row is None:
            return None
        if row.completed:
            msg = "completed rows are read-only except status cycling"
            raise ValueError(msg)
        return row

    def _insertion_location(self) -> tuple[list[Task | TaskGroup], int]:
        if self.selected_path is None:
            return self.roadmap.steps, len(self.roadmap.steps)

        siblings, index = _siblings_for_path(self.roadmap, self.selected_path)
        return siblings, index + 1

    def _path_for_inserted_index(self, index: int) -> Path:
        if self.selected_path is None:
            return (index,)
        return (*self.selected_path[:-1], index)


def _flatten_rows(
    items: list[Task | TaskGroup],
    hide_completed: bool,
    prefix: Path = (),
) -> list[EditorRow]:
    rows: list[EditorRow] = []
    for index, item in enumerate(items):
        path = (*prefix, index)
        if hide_completed and item.status == COMPLETED:
            continue

        rows.append(_row_from_item(item, path))
        if isinstance(item, TaskGroup):
            rows.extend(_flatten_rows(item.tasks, hide_completed, path))
    return rows


def _row_from_item(item: Task | TaskGroup, path: Path) -> EditorRow:
    return EditorRow(
        path=path,
        depth=len(path) - 1,
        item=item,
        order_text="-" if item.order == UNSORTED else f"{item.order}.",
        completion_text=item.completion_percent,
        priority_text=_priority_text(item),
        milestone_text="" if item.milestone == NO_MILESTONE else str(item.milestone),
        description=item.description,
        status=item.status,
        completed=item.status == COMPLETED,
        group=isinstance(item, TaskGroup),
    )


def _priority_text(item: Task | TaskGroup) -> str:
    if item.priority == OPTIONAL_TASK:
        return "?"
    if item.priority == MAX_PRIORITY:
        return "!"
    if item.priority > 0:
        return f"^{item.priority}"
    return ""


def parse_milestone_prompt(value: str) -> int:
    text = value.strip()
    if not text:
        return NO_MILESTONE

    parenthesized = re.fullmatch(r"\(\s*(\d+)\s*\)", text)
    if parenthesized is not None:
        text = parenthesized.group(1)

    if not re.fullmatch(r"\d+", text):
        msg = "milestone must be a non-negative integer"
        raise ValueError(msg)
    return int(text)


def parse_priority_prompt(value: str) -> int:
    text = value.strip()
    if not text:
        return DEFAULT_PRIORITY
    if text == "!":
        return MAX_PRIORITY
    if text == "?":
        return OPTIONAL_TASK
    if text.startswith("^"):
        text = text[1:].strip()
    if not re.fullmatch(r"\d+", text):
        msg = "priority must be !, ?, ^N, N, or empty"
        raise ValueError(msg)
    return int(text)


def parse_completion_prompt(value: str) -> float:
    text = value.strip()
    if not text:
        return 0.0
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        completion = float(text)
    except ValueError as exc:
        msg = "completion must be a number from 0.0 through 99.0"
        raise ValueError(msg) from exc
    return _validated_task_completion(completion, ONGOING, "completion", ValueError)


def parse_confirmation_prompt(value: str, *, default: bool) -> bool:
    text = value.strip().casefold()
    if not text:
        return default
    if text in {"y", "yes"}:
        return True
    if text in {"n", "no"}:
        return False
    msg = "answer must be yes or no"
    raise ValueError(msg)


def _siblings_for_path(roadmap: Roadmap, path: Path) -> tuple[list[Task | TaskGroup], int]:
    if not path:
        msg = "path cannot be empty"
        raise ValueError(msg)

    siblings = roadmap.steps
    for index in path[:-1]:
        parent = siblings[index]
        if not isinstance(parent, TaskGroup):
            msg = "path descends through a leaf task"
            raise TypeError(msg)
        siblings = parent.tasks
    return siblings, path[-1]


def _renumber_sorted_siblings(siblings: list[Task | TaskGroup]) -> None:
    order = 1
    for item in siblings:
        if item.order == UNSORTED:
            continue
        item.order = order
        order += 1


def _row_index(rows: list[EditorRow], path: Path | None) -> int | None:
    if path is None:
        return None
    for index, row in enumerate(rows):
        if row.path == path:
            return index
    return None
