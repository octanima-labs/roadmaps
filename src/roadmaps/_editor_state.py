from __future__ import annotations

import re
from dataclasses import dataclass, field

from roadmaps._validation import _validate_description, _validated_task_completion
from roadmaps.constants import (
    COMPLETED,
    DEFAULT_PRIORITY,
    ENABLE_TUI_ORDER_BREADCRUMBS,
    ENABLE_TUI_ROMAN_MILESTONES,
    ENABLE_TUI_UNICODE_PROGRESS,
    MAX_PRIORITY,
    NO_MILESTONE,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    TUI_PROGRESS_BAR_WIDTH,
    UNSORTED,
)
from roadmaps.model import Roadmap, Task, TaskGroup

Path = tuple[int, ...]
NEW_TASK_DESCRIPTION = "New task"
NEW_GROUP_DESCRIPTION = "New group"


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
    selected: bool
    collapsed: bool


@dataclass
class EditorState:
    roadmap: Roadmap
    selected_path: Path | None = None
    hide_completed: bool = False
    dirty: bool = False
    selected_paths: set[Path] = field(default_factory=set)
    collapsed_item_ids: set[int] = field(default_factory=set)
    range_anchor_path: Path | None = None
    expand_groups_next: bool = True

    def __post_init__(self) -> None:
        self.repair_selection()

    @property
    def rows(self) -> list[EditorRow]:
        return _flatten_rows(
            self.roadmap.steps,
            self.hide_completed,
            self.collapsed_item_ids,
            self.selected_paths,
        )

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
        self.range_anchor_path = None
        return True

    @property
    def selected_rows(self) -> list[EditorRow]:
        return [row for row in self.rows if row.path in self.selected_paths]

    def toggle_selected_row_mark(self) -> bool:
        row = self.selected_row
        if row is None:
            return False
        self.range_anchor_path = None
        if row.path in self.selected_paths:
            self.selected_paths.remove(row.path)
        else:
            self.selected_paths.add(row.path)
        return True

    def clear_row_marks(self) -> None:
        self.selected_paths.clear()
        self.range_anchor_path = None

    def move_selection(self, delta: int) -> bool:
        rows = self.rows
        if not rows:
            if self.selected_path is None:
                return False
            self.selected_path = None
            self.range_anchor_path = None
            return True
        if self.selected_path is None:
            self.selected_path = rows[0].path
            self.range_anchor_path = None
            return True

        paths = [row.path for row in rows]
        try:
            index = paths.index(self.selected_path)
        except ValueError:
            self.selected_path = rows[0].path
            self.range_anchor_path = None
            return True

        new_index = min(max(index + delta, 0), len(rows) - 1)
        if new_index == index:
            return False
        self.selected_path = rows[new_index].path
        self.range_anchor_path = None
        return True

    def extend_selection(self, delta: int) -> bool:
        rows = self.rows
        if not rows:
            return False
        if self.selected_path is None:
            self.selected_path = rows[0].path
            self.range_anchor_path = rows[0].path
            self.selected_paths = {rows[0].path}
            return True

        paths = [row.path for row in rows]
        try:
            current_index = paths.index(self.selected_path)
        except ValueError:
            current_index = 0
            self.selected_path = rows[0].path

        if self.range_anchor_path not in paths:
            self.range_anchor_path = self.selected_path
        anchor_index = paths.index(self.range_anchor_path)

        new_index = min(max(current_index + delta, 0), len(rows) - 1)
        if new_index == current_index:
            return False

        self.selected_path = rows[new_index].path
        start = min(anchor_index, new_index)
        end = max(anchor_index, new_index)
        self.selected_paths = {row.path for row in rows[start : end + 1]}
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
        self.clear_row_marks()
        self.dirty = True
        return task

    def insert_sorted_task(self, description: str = NEW_TASK_DESCRIPTION) -> Task:
        task = Task(description, order=1)
        siblings, insert_index = self._insertion_location()
        siblings.insert(insert_index, task)
        _renumber_sorted_siblings(siblings)
        self.selected_path = self._path_for_inserted_index(insert_index)
        self.clear_row_marks()
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
        if self.selected_paths:
            return self._update_marked_milestone(milestone)
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
        if self.selected_paths:
            return self._update_marked_priority(priority)
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
        if self.selected_paths:
            return self._update_marked_completion(completion, allow_start=allow_start)
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

    def group_selected_rows(self) -> TaskGroup | None:
        marked_rows = self.selected_rows
        if not marked_rows:
            return self.convert_selected_task_to_group()
        if len(marked_rows) < 2:
            msg = "select multiple rows to group"
            raise ValueError(msg)

        parent_paths = {row.path[:-1] for row in marked_rows}
        if len(parent_paths) != 1:
            msg = "selected rows must share the same parent"
            raise ValueError(msg)

        parent_path = parent_paths.pop()
        siblings = _items_at_parent_path(self.roadmap, parent_path)
        selected_indexes = [row.path[-1] for row in marked_rows]
        insert_index = min(selected_indexes)
        first_item = siblings[insert_index]
        group = TaskGroup(
            NEW_GROUP_DESCRIPTION,
            order=first_item.order,
            tasks=[siblings[index] for index in selected_indexes],
        )
        for index in sorted(selected_indexes, reverse=True):
            siblings.pop(index)
        siblings.insert(insert_index, group)
        _renumber_sorted_siblings(group.tasks)
        _renumber_sorted_siblings(siblings)
        self.clear_row_marks()
        self.selected_path = _path_for_item(self.roadmap.steps, group)
        self.dirty = True
        return group

    def convert_selected_task_to_group(self) -> TaskGroup | None:
        row = self.selected_row
        if row is None:
            return None
        if isinstance(row.item, TaskGroup):
            return None

        siblings, index = _siblings_for_path(self.roadmap, row.path)
        group = row.item.to_group()
        siblings[index] = group
        self.selected_path = _path_for_item(self.roadmap.steps, group)
        self.clear_row_marks()
        self.dirty = True
        return group

    def toggle_selected_group_collapsed(self) -> bool:
        row = self.selected_row
        if row is None or not isinstance(row.item, TaskGroup):
            return False
        item_id = id(row.item)
        if item_id in self.collapsed_item_ids:
            self.collapsed_item_ids.remove(item_id)
        else:
            self.collapsed_item_ids.add(item_id)
        self._repair_row_marks()
        self.repair_selection()
        return True

    def toggle_visible_groups_collapsed(self) -> tuple[bool, bool]:
        expand = self.expand_groups_next
        self.expand_groups_next = not self.expand_groups_next
        group_ids = {id(row.item) for row in self.rows if isinstance(row.item, TaskGroup)}
        if not group_ids:
            return False, expand

        before = set(self.collapsed_item_ids)
        if expand:
            self.collapsed_item_ids.difference_update(group_ids)
        else:
            self.collapsed_item_ids.update(group_ids)
        changed = self.collapsed_item_ids != before
        self._repair_row_marks()
        self.repair_selection()
        return changed, expand

    def adjust_selected_priority(self, delta: int) -> bool:
        rows = self.selected_rows if self.selected_paths else [self.selected_row]
        changed = False
        for row in rows:
            if row is None or row.completed:
                continue
            priority = _adjusted_priority(row.item, delta)
            before = (row.item.priority, row.item.optional)
            if priority == OPTIONAL_TASK:
                row.item.set_optional(True)
            else:
                row.item.set_optional(False)
                row.item.set_priority(priority)
            if (row.item.priority, row.item.optional) != before:
                changed = True
        if changed:
            self.dirty = True
        return changed

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

    def move_selected_row_up(self) -> bool:
        row = self.selected_row
        if row is None:
            return False

        siblings, index = _siblings_for_path(self.roadmap, row.path)
        visible_indices = _visible_sibling_indices(siblings, self.hide_completed)
        visible_position = visible_indices.index(index)
        if visible_position > 0:
            swap_index = visible_indices[visible_position - 1]
            siblings[index], siblings[swap_index] = siblings[swap_index], siblings[index]
            _renumber_sorted_siblings(siblings)
            self._finish_row_move(row.item)
            return True

        if len(row.path) == 1:
            return False

        parent_path = row.path[:-1]
        parent_siblings, parent_index = _siblings_for_path(self.roadmap, parent_path)
        parent = parent_siblings[parent_index]
        if not isinstance(parent, TaskGroup):  # pragma: no cover - paths are generated from groups.
            msg = "parent row is not a task group"
            raise TypeError(msg)

        item = siblings.pop(index)
        if not siblings:
            parent_siblings[parent_index] = parent.to_task()
        parent_siblings.insert(parent_index, item)
        _renumber_sorted_siblings(siblings)
        _renumber_sorted_siblings(parent_siblings)
        self._finish_row_move(item)
        return True

    def move_selected_row_down(self) -> bool:
        row = self.selected_row
        if row is None:
            return False

        siblings, index = _siblings_for_path(self.roadmap, row.path)
        visible_indices = _visible_sibling_indices(siblings, self.hide_completed)
        visible_position = visible_indices.index(index)
        if visible_position < len(visible_indices) - 1:
            swap_index = visible_indices[visible_position + 1]
            siblings[index], siblings[swap_index] = siblings[swap_index], siblings[index]
            _renumber_sorted_siblings(siblings)
            self._finish_row_move(row.item)
            return True

        if len(row.path) == 1:
            return False

        parent_path = row.path[:-1]
        parent_siblings, parent_index = _siblings_for_path(self.roadmap, parent_path)
        parent = parent_siblings[parent_index]
        if not isinstance(parent, TaskGroup):  # pragma: no cover - paths are generated from groups.
            msg = "parent row is not a task group"
            raise TypeError(msg)

        item = siblings.pop(index)
        if not siblings:
            parent_siblings[parent_index] = parent.to_task()
        parent_siblings.insert(parent_index + 1, item)
        _renumber_sorted_siblings(siblings)
        _renumber_sorted_siblings(parent_siblings)
        self._finish_row_move(item)
        return True

    def indent_selected_row(self) -> bool:
        row = self.selected_row
        if row is None:
            return False

        siblings, index = _siblings_for_path(self.roadmap, row.path)
        visible_indices = _visible_sibling_indices(siblings, self.hide_completed)
        visible_position = visible_indices.index(index)
        if visible_position == 0:
            return False

        parent_index = visible_indices[visible_position - 1]
        parent = siblings[parent_index]
        if isinstance(parent, TaskGroup):
            group = parent
        else:
            group = parent.to_group()
            siblings[parent_index] = group

        item = siblings.pop(index)
        if item.milestone == NO_MILESTONE and group.milestone != NO_MILESTONE:
            item.milestone = group.milestone
        group.tasks.append(item)
        _renumber_sorted_siblings(siblings)
        _renumber_sorted_siblings(group.tasks)
        self._finish_row_move(item)
        return True

    def outdent_selected_row(self) -> bool:
        row = self.selected_row
        if row is None or len(row.path) == 1:
            return False

        siblings, index = _siblings_for_path(self.roadmap, row.path)
        parent_path = row.path[:-1]
        parent_siblings, parent_index = _siblings_for_path(self.roadmap, parent_path)
        parent = parent_siblings[parent_index]
        if not isinstance(parent, TaskGroup):  # pragma: no cover - paths are generated from groups.
            msg = "parent row is not a task group"
            raise TypeError(msg)

        item = siblings.pop(index)
        if not siblings:
            parent_siblings[parent_index] = parent.to_task()
        parent_siblings.insert(parent_index + 1, item)
        _renumber_sorted_siblings(siblings)
        _renumber_sorted_siblings(parent_siblings)
        self._finish_row_move(item)
        return True

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
            self.selected_paths.clear()
            self.range_anchor_path = None
            return

        if self.selected_path in {row.path for row in rows}:
            self._repair_row_marks()
            return

        previous_index = _row_index(previous_rows or [], self.selected_path)
        if previous_index is None:
            self.selected_path = rows[0].path
            self._repair_row_marks()
            return
        if previous_index < len(rows):
            self.selected_path = rows[previous_index].path
            self._repair_row_marks()
            return
        self.selected_path = rows[-1].path
        self._repair_row_marks()

    def _finish_row_move(self, item: Task | TaskGroup) -> None:
        self.selected_path = _path_for_item(self.roadmap.steps, item)
        self.clear_row_marks()
        self.dirty = True
        self.repair_selection()

    def _update_marked_milestone(self, milestone: int) -> bool:
        if milestone < NO_MILESTONE:
            msg = "milestone must be a non-negative integer"
            raise ValueError(msg)
        changed = False
        for row in self.selected_rows:
            if row.completed:
                continue
            if row.item.milestone != milestone:
                row.item.milestone = milestone
                changed = True
        self.clear_row_marks()
        if changed:
            self.dirty = True
        return changed

    def _update_marked_priority(self, priority: int) -> bool:
        changed = False
        for row in self.selected_rows:
            if row.completed:
                continue
            before = (row.item.priority, row.item.optional)
            if priority == OPTIONAL_TASK:
                row.item.set_optional(True)
            else:
                row.item.set_optional(False)
                row.item.set_priority(priority)
            if (row.item.priority, row.item.optional) != before:
                changed = True
        self.clear_row_marks()
        if changed:
            self.dirty = True
        return changed

    def _update_marked_completion(self, completion: float, *, allow_start: bool) -> bool:
        changed = False
        for row in self.selected_rows:
            if row.completed or isinstance(row.item, TaskGroup):
                continue
            if row.status == NOT_STARTED and not allow_start:
                continue
            before = self.roadmap.to_dict()
            row.item.mark_ongoing(completion=completion)
            if self.roadmap.to_dict() != before:
                changed = True
        self.clear_row_marks()
        if changed:
            self.dirty = True
            self.repair_selection()
        return changed

    def _repair_row_marks(self) -> None:
        visible_paths = {row.path for row in self.rows}
        self.selected_paths.intersection_update(visible_paths)
        if self.range_anchor_path not in visible_paths:
            self.range_anchor_path = None

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
    collapsed_item_ids: set[int],
    selected_paths: set[Path],
    prefix: Path = (),
    order_prefix: tuple[str, ...] = (),
) -> list[EditorRow]:
    rows: list[EditorRow] = []
    for index, item in enumerate(items):
        path = (*prefix, index)
        order_path = (*order_prefix, _order_part(item))
        if hide_completed and item.status == COMPLETED:
            continue

        rows.append(_row_from_item(item, path, order_path, selected_paths, collapsed_item_ids))
        if isinstance(item, TaskGroup) and id(item) not in collapsed_item_ids:
            rows.extend(
                _flatten_rows(
                    item.tasks,
                    hide_completed,
                    collapsed_item_ids,
                    selected_paths,
                    path,
                    order_path,
                )
            )
    return rows


def _row_from_item(
    item: Task | TaskGroup,
    path: Path,
    order_path: tuple[str, ...],
    selected_paths: set[Path],
    collapsed_item_ids: set[int],
) -> EditorRow:
    return EditorRow(
        path=path,
        depth=len(path) - 1,
        item=item,
        order_text=_order_text(item, order_path),
        completion_text=_completion_text(item),
        priority_text=_priority_text(item),
        milestone_text=_milestone_text(item),
        description=item.description,
        status=item.status,
        completed=item.status == COMPLETED,
        group=isinstance(item, TaskGroup),
        selected=path in selected_paths,
        collapsed=isinstance(item, TaskGroup) and id(item) in collapsed_item_ids,
    )


def _order_text(item: Task | TaskGroup, order_path: tuple[str, ...]) -> str:
    if ENABLE_TUI_ORDER_BREADCRUMBS:
        return ".".join(order_path)
    return _order_part(item) if item.order == UNSORTED else f"{item.order}."


def _order_part(item: Task | TaskGroup) -> str:
    return "-" if item.order == UNSORTED else str(item.order)


def _completion_text(item: Task | TaskGroup) -> str:
    completion = max(0.0, min(item.completion, 100.0))
    width = max(TUI_PROGRESS_BAR_WIDTH, 1)
    filled = width if completion >= 100.0 else int(completion * width / 100.0)
    empty = width - filled
    filled_char = "█" if ENABLE_TUI_UNICODE_PROGRESS else "#"
    empty_char = "░" if ENABLE_TUI_UNICODE_PROGRESS else "-"
    return f"[{filled_char * filled}{empty_char * empty}] {item.completion_percent}"


def _priority_text(item: Task | TaskGroup) -> str:
    if item.priority == OPTIONAL_TASK:
        return "?"
    if item.priority == MAX_PRIORITY:
        return "!"
    if item.priority > 0:
        return f"^{item.priority}"
    return ""


def _milestone_text(item: Task | TaskGroup) -> str:
    if item.milestone == NO_MILESTONE:
        return ""
    if ENABLE_TUI_ROMAN_MILESTONES:
        return _roman_milestone(item.milestone)
    return str(item.milestone)


def _roman_milestone(value: int) -> str:
    if value <= 0 or value > 3999:
        return str(value)
    numerals = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    result = ""
    remaining = value
    for number, numeral in numerals:
        while remaining >= number:
            result += numeral
            remaining -= number
    return result


def _adjusted_priority(item: Task | TaskGroup, delta: int) -> int:
    if delta == 0:
        return item.priority
    if item.priority == OPTIONAL_TASK:
        return DEFAULT_PRIORITY if delta > 0 else OPTIONAL_TASK
    priority = item.priority + delta
    if priority < DEFAULT_PRIORITY:
        return OPTIONAL_TASK
    return min(priority, MAX_PRIORITY)


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


def _items_at_parent_path(roadmap: Roadmap, parent_path: Path) -> list[Task | TaskGroup]:
    if not parent_path:
        return roadmap.steps
    siblings, index = _siblings_for_path(roadmap, parent_path)
    parent = siblings[index]
    if not isinstance(parent, TaskGroup):
        msg = "parent row is not a task group"
        raise TypeError(msg)
    return parent.tasks


def _renumber_sorted_siblings(siblings: list[Task | TaskGroup]) -> None:
    order = 1
    for item in siblings:
        if item.order == UNSORTED:
            continue
        item.order = order
        order += 1


def _visible_sibling_indices(
    siblings: list[Task | TaskGroup],
    hide_completed: bool,
) -> list[int]:
    return [
        index
        for index, item in enumerate(siblings)
        if not (hide_completed and item.status == COMPLETED)
    ]


def _path_for_item(
    items: list[Task | TaskGroup],
    target: Task | TaskGroup,
    prefix: Path = (),
) -> Path | None:
    for index, item in enumerate(items):
        path = (*prefix, index)
        if item is target:
            return path
        if isinstance(item, TaskGroup):
            child_path = _path_for_item(item.tasks, target, path)
            if child_path is not None:
                return child_path
    return None


def _row_index(rows: list[EditorRow], path: Path | None) -> int | None:
    if path is None:
        return None
    for index, row in enumerate(rows):
        if row.path == path:
            return index
    return None
