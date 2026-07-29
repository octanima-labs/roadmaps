import pytest

from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    DEFAULT_TASK_GROUP_DESCRIPTION,
    MAX_PRIORITY,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
)
from roadmaps._editor_state import (
    NEW_GROUP_DESCRIPTION,
    NEW_TASK_DESCRIPTION,
    EditorState,
    parse_completion_prompt,
    parse_confirmation_prompt,
    parse_milestone_prompt,
    parse_priority_prompt,
)
from roadmaps.model import Roadmap, Task, TaskGroup


def test_rows_expose_display_fields_and_initial_selection() -> None:
    roadmap = Roadmap(
        [
            TaskGroup(
                "group",
                order=1,
                milestone=2,
                tasks=[Task("urgent", priority=MAX_PRIORITY, status=ONGOING)],
            ),
            Task("optional", optional=True),
        ]
    )

    state = EditorState(roadmap)

    assert state.selected_path == (0,)
    assert [(row.path, row.depth, row.description) for row in state.rows] == [
        ((0,), 0, "group"),
        ((0, 0), 1, "urgent"),
        ((1,), 0, "optional"),
    ]
    assert state.rows[0].order_text == "1"
    assert state.rows[1].order_text == "1.-"
    assert state.rows[0].completion_text == "[░░░░░░░░░░] 0%"
    assert state.rows[0].milestone_text == "II"
    assert state.rows[0].group is True
    assert state.rows[1].priority_text == "!"
    assert state.rows[2].priority_text == "?"


def test_rows_can_disable_tui_order_breadcrumbs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("roadmaps._editor_state.ENABLE_TUI_ORDER_BREADCRUMBS", False)

    state = EditorState(Roadmap([TaskGroup("group", order=1, tasks=[Task("child")])]))

    assert [row.order_text for row in state.rows] == ["1.", "-"]


def test_rows_show_literal_dash_parts_in_tui_order_breadcrumbs() -> None:
    state = EditorState(
        Roadmap(
            [
                TaskGroup(
                    "first",
                    order=1,
                    tasks=[TaskGroup("nested", order=1, tasks=[Task("loose")])],
                ),
                TaskGroup("second", order=12, tasks=[TaskGroup("loose", tasks=[Task("child", order=1)])]),
                TaskGroup("loose", tasks=[Task("child", order=1)]),
            ]
        )
    )

    assert [row.order_text for row in state.rows] == [
        "1",
        "1.1",
        "1.1.-",
        "12",
        "12.-",
        "12.-.1",
        "-",
        "-.1",
    ]


def test_rows_show_progress_bars_with_ascii_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("roadmaps._editor_state.ENABLE_TUI_UNICODE_PROGRESS", False)
    state = EditorState(Roadmap([Task("task", status=ONGOING, completion=40.0)]))

    assert state.rows[0].completion_text == "[####------] 40%"


def test_rows_show_roman_milestones_with_decimal_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = EditorState(
        Roadmap([Task("small", milestone=4), Task("large", milestone=4000)])
    )

    assert [row.milestone_text for row in state.rows] == ["IV", "4000"]

    monkeypatch.setattr("roadmaps._editor_state.ENABLE_TUI_ROMAN_MILESTONES", False)
    state = EditorState(Roadmap([Task("small", milestone=4)]))
    assert state.rows[0].milestone_text == "4"


def test_rows_preserve_multiline_descriptions() -> None:
    state = EditorState(Roadmap([Task("first line\nsecond line")]))

    assert state.rows[0].description == "first line\nsecond line"


def test_move_selection_clamps_without_marking_dirty() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second")]))

    assert state.move_selection(1) is True
    assert state.selected_path == (1,)
    assert state.move_selection(1) is False
    assert state.selected_path == (1,)
    assert state.move_selection(-10) is True
    assert state.selected_path == (0,)
    assert state.dirty is False


def test_extend_selection_uses_focused_row_as_anchor() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second"), Task("third"), Task("fourth")]))
    state.select_path((1,))

    assert state.extend_selection(1) is True
    assert state.selected_path == (2,)
    assert state.range_anchor_path == (1,)
    assert state.selected_paths == {(1,), (2,)}

    assert state.extend_selection(1) is True
    assert state.selected_path == (3,)
    assert state.range_anchor_path == (1,)
    assert state.selected_paths == {(1,), (2,), (3,)}

    assert state.extend_selection(-1) is True
    assert state.selected_path == (2,)
    assert state.selected_paths == {(1,), (2,)}

    assert state.move_selection(-1) is True
    assert state.range_anchor_path is None


def test_select_path_rejects_non_visible_paths() -> None:
    state = EditorState(
        Roadmap([Task("first"), Task("done", status=COMPLETED)]),
        hide_completed=True,
    )

    assert state.select_path((1,)) is False
    assert state.selected_path == (0,)
    assert state.select_path((9,)) is False
    assert state.selected_path == (0,)


def test_hide_completed_preserves_visible_selection_and_marks_dirty() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("first"),
                Task("done", status=COMPLETED),
                Task("second"),
            ]
        )
    )
    state.select_path((2,))

    state.toggle_hide_completed()

    assert state.hide_completed is True
    assert state.dirty is True
    assert [row.description for row in state.rows] == ["first", "second"]
    assert state.selected_path == (2,)


def test_hide_completed_selects_next_visible_row_when_selected_row_is_hidden() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("done", status=COMPLETED),
                Task("pending"),
                Task("second"),
            ]
        )
    )

    state.toggle_hide_completed()

    assert [row.description for row in state.rows] == ["pending", "second"]
    assert state.selected_path == (1,)


def test_hide_completed_selects_previous_visible_row_without_next_row() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("pending"),
                Task("done", status=COMPLETED),
            ]
        )
    )
    state.select_path((1,))

    state.toggle_hide_completed()

    assert [row.description for row in state.rows] == ["pending"]
    assert state.selected_path == (0,)


def test_hide_completed_clears_selection_when_all_rows_are_hidden() -> None:
    state = EditorState(Roadmap([Task("done", status=COMPLETED)]))

    state.toggle_hide_completed()

    assert state.rows == []
    assert state.selected_path is None


def test_insert_unsorted_task_after_selected_sibling() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second")]))

    task = state.insert_unsorted_task()

    assert task.description == NEW_TASK_DESCRIPTION
    assert [step.description for step in state.roadmap.steps] == [
        "first",
        NEW_TASK_DESCRIPTION,
        "second",
    ]
    assert task.order == UNSORTED
    assert state.selected_path == (1,)
    assert state.dirty is True


def test_insert_unsorted_task_appends_top_level_without_selection() -> None:
    state = EditorState(Roadmap())

    state.insert_unsorted_task()

    assert [step.description for step in state.roadmap.steps] == [NEW_TASK_DESCRIPTION]
    assert state.selected_path == (0,)


def test_insert_sorted_task_after_selected_sibling_and_renumbers_sorted_siblings() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("first", order=1),
                Task("loose"),
                Task("second", order=2),
            ]
        )
    )
    state.select_path((1,))

    task = state.insert_sorted_task()

    assert [step.description for step in state.roadmap.steps] == [
        "first",
        "loose",
        NEW_TASK_DESCRIPTION,
        "second",
    ]
    assert task.order == 2
    assert [step.order for step in state.roadmap.steps] == [1, UNSORTED, 2, 3]
    assert state.selected_path == (2,)
    assert state.dirty is True


def test_insert_sorted_task_uses_selected_nested_sibling_level() -> None:
    group = TaskGroup("group", tasks=[Task("child", order=1)])
    state = EditorState(Roadmap([group]))
    state.select_path((0, 0))

    state.insert_sorted_task()

    assert [task.description for task in group.tasks] == ["child", NEW_TASK_DESCRIPTION]
    assert [task.order for task in group.tasks] == [1, 2]
    assert state.selected_path == (0, 1)


def test_update_selected_description_rejects_completed_rows() -> None:
    state = EditorState(Roadmap([Task("done", status=COMPLETED)]))

    with pytest.raises(ValueError, match="completed rows"):
        state.update_selected_description("new description")

    assert state.roadmap.steps[0].description == "done"
    assert state.dirty is False


def test_update_selected_description_marks_dirty_only_on_change() -> None:
    state = EditorState(Roadmap([Task("old")]))

    assert state.update_selected_description("old") is False
    assert state.dirty is False

    assert state.update_selected_description("new") is True
    assert state.roadmap.steps[0].description == "new"
    assert state.dirty is True


@pytest.mark.parametrize("description", ["", "   ", "\n\t"])
def test_update_selected_description_rejects_blank_input(description: str) -> None:
    state = EditorState(Roadmap([Task("old")]))

    with pytest.raises(ValueError, match="non-empty string"):
        state.update_selected_description(description)

    assert state.roadmap.steps[0].description == "old"
    assert state.dirty is False


def test_update_selected_description_without_selection_is_noop() -> None:
    state = EditorState(Roadmap())

    assert state.update_selected_description("new") is False
    assert state.dirty is False


def test_cycle_leaf_statuses_and_marks_dirty_only_on_change() -> None:
    task = Task("task")
    state = EditorState(Roadmap([task]))

    assert state.cycle_selected_status() is True
    assert task.status == ONGOING
    assert task.start_date is not None

    assert state.cycle_selected_status() is True
    assert task.status == COMPLETED
    assert task.completion_date is not None

    assert state.cycle_selected_status() is True
    assert task.status == NOT_STARTED
    assert task.start_date is None
    assert task.completion_date is None
    assert state.dirty is True


def test_cycle_group_status_uses_group_methods() -> None:
    first = Task("first")
    second = Task("second")
    optional = Task("optional", optional=True)
    group = TaskGroup("group", tasks=[first, second, optional])
    state = EditorState(Roadmap([group]))

    assert state.cycle_selected_status() is True
    assert first.status == ONGOING
    assert second.status == NOT_STARTED

    assert state.cycle_selected_status() is True
    assert first.status == COMPLETED
    assert second.status == COMPLETED
    assert optional.status == NOT_STARTED

    assert state.cycle_selected_status() is True
    assert first.status == NOT_STARTED
    assert second.status == NOT_STARTED


def test_cycle_empty_group_is_noop() -> None:
    state = EditorState(Roadmap([TaskGroup("empty")]))

    assert state.cycle_selected_status() is False
    assert state.dirty is False


def test_cycle_status_without_selection_is_noop() -> None:
    state = EditorState(Roadmap())

    assert state.cycle_selected_status() is False
    assert state.dirty is False


def test_parse_metadata_prompts_accept_friendly_forms() -> None:
    assert parse_milestone_prompt("") == 0
    assert parse_milestone_prompt("(12)") == 12
    assert parse_priority_prompt("") == DEFAULT_PRIORITY
    assert parse_priority_prompt("!") == MAX_PRIORITY
    assert parse_priority_prompt("?") == OPTIONAL_TASK
    assert parse_priority_prompt("^42") == 42
    assert parse_priority_prompt("42") == 42
    assert parse_completion_prompt("") == 0.0
    assert parse_completion_prompt("50") == 50.0
    assert parse_completion_prompt("50.0") == 50.0
    assert parse_completion_prompt("50%") == 50.0
    assert parse_confirmation_prompt("", default=True) is True
    assert parse_confirmation_prompt("", default=False) is False
    assert parse_confirmation_prompt("YES", default=False) is True
    assert parse_confirmation_prompt("n", default=True) is False


def test_parse_metadata_prompts_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="milestone"):
        parse_milestone_prompt("one")
    with pytest.raises(ValueError, match="priority"):
        parse_priority_prompt("high")
    with pytest.raises(ValueError, match="completion"):
        parse_completion_prompt("100")
    with pytest.raises(ValueError, match="yes or no"):
        parse_confirmation_prompt("maybe", default=True)


def test_update_selected_milestone_and_priority_for_tasks_and_groups() -> None:
    group = TaskGroup("group", tasks=[Task("child")])
    state = EditorState(Roadmap([group, Task("task")]))

    assert state.update_selected_milestone(3) is True
    assert group.milestone == 3
    assert state.update_selected_priority(MAX_PRIORITY) is True
    assert group.priority == MAX_PRIORITY

    state.select_path((1,))
    assert state.update_selected_priority(OPTIONAL_TASK) is True
    assert state.roadmap.steps[1].optional is True
    assert state.roadmap.steps[1].priority == OPTIONAL_TASK
    assert state.update_selected_priority(DEFAULT_PRIORITY) is True
    assert state.roadmap.steps[1].optional is False
    assert state.roadmap.steps[1].priority == DEFAULT_PRIORITY


def test_update_selected_metadata_marks_dirty_only_on_change() -> None:
    state = EditorState(Roadmap([Task("task", milestone=2, priority=5)]))

    assert state.update_selected_milestone(2) is False
    assert state.update_selected_priority(5) is False
    assert state.dirty is False


def test_update_selected_metadata_rejects_completed_rows() -> None:
    state = EditorState(Roadmap([Task("done", status=COMPLETED)]))

    with pytest.raises(ValueError, match="completed rows"):
        state.update_selected_milestone(1)
    with pytest.raises(ValueError, match="completed rows"):
        state.update_selected_priority(1)


def test_adjust_selected_priority_uses_focus_or_marked_rows_and_skips_completed() -> None:
    optional = Task("optional", optional=True)
    pending = Task("pending")
    high = Task("high", priority=995)
    done = Task("done", status=COMPLETED)
    state = EditorState(Roadmap([optional, pending, high, done]))

    assert state.adjust_selected_priority(1) is True
    assert optional.optional is False
    assert optional.priority == DEFAULT_PRIORITY

    assert state.adjust_selected_priority(1) is True
    assert optional.priority == 1

    assert state.adjust_selected_priority(-10) is True
    assert optional.optional is True
    assert optional.priority == OPTIONAL_TASK

    state.selected_paths = {(1,), (2,), (3,)}
    assert state.adjust_selected_priority(10) is True
    assert pending.priority == 10
    assert high.priority == MAX_PRIORITY
    assert done.priority == DEFAULT_PRIORITY
    assert state.selected_paths == {(1,), (2,), (3,)}


def test_toggle_visible_groups_collapsed_alternates_editor_state() -> None:
    inner = TaskGroup("inner", tasks=[Task("child")])
    outer = TaskGroup("outer", tasks=[inner])
    state = EditorState(Roadmap([outer]))
    state.collapsed_item_ids = {id(inner)}

    changed, expanded = state.toggle_visible_groups_collapsed()
    assert changed is True
    assert expanded is True
    assert state.collapsed_item_ids == set()
    assert [row.description for row in state.rows] == ["outer", "inner", "child"]

    changed, expanded = state.toggle_visible_groups_collapsed()
    assert changed is True
    assert expanded is False
    assert state.collapsed_item_ids == {id(outer), id(inner)}
    assert [row.description for row in state.rows] == ["outer"]


def test_update_selected_completion_requires_leaf_and_confirmation_flags() -> None:
    state = EditorState(Roadmap([TaskGroup("group", tasks=[Task("child")])]))

    with pytest.raises(TypeError, match="leaf tasks"):
        state.update_selected_completion(50.0)

    pending = Task("pending")
    done = Task("done", status=COMPLETED)
    state = EditorState(Roadmap([pending, done]))

    with pytest.raises(ValueError, match="started"):
        state.update_selected_completion(50.0)
    assert state.update_selected_completion(50.0, allow_start=True) is True
    assert pending.status == ONGOING
    assert pending.completion == 50.0

    state.select_path((1,))
    with pytest.raises(ValueError, match="completed rows"):
        state.update_selected_completion(50.0)
    assert state.update_selected_completion(0.0, allow_completed=True) is True
    assert done.status == ONGOING
    assert done.completion == 0.0


def test_adjust_selected_completion_updates_ongoing_leaf_and_clamps_to_zero() -> None:
    task = Task("task", status=ONGOING, completion=50.0)
    state = EditorState(Roadmap([task]))

    assert state.adjust_selected_completion(1.0) is True
    assert task.completion == 51.0
    assert state.adjust_selected_completion(-99.0) is True
    assert task.status == ONGOING
    assert task.completion == 0.0


def test_adjust_selected_completion_handles_not_started_rules() -> None:
    task = Task("task")
    state = EditorState(Roadmap([task]))

    with pytest.raises(ValueError, match="started"):
        state.adjust_selected_completion(1.0)
    with pytest.raises(ValueError, match="not started"):
        state.adjust_selected_completion(-1.0)

    assert state.adjust_selected_completion(10.0, allow_start=True) is True
    assert task.status == ONGOING
    assert task.completion == 10.0


def test_adjust_selected_completion_can_complete_ongoing_leaf() -> None:
    task = Task("task", status=ONGOING, completion=95.0)
    state = EditorState(Roadmap([task]))

    with pytest.raises(ValueError, match="complete task"):
        state.adjust_selected_completion(10.0)

    assert state.adjust_selected_completion(10.0, allow_complete=True) is True
    assert task.status == COMPLETED
    assert task.completion == 100.0


def test_adjust_selected_completion_handles_completed_rules() -> None:
    task = Task("done", status=COMPLETED)
    state = EditorState(Roadmap([task]))

    with pytest.raises(ValueError, match="already completed"):
        state.adjust_selected_completion(1.0)
    with pytest.raises(ValueError, match="completed rows"):
        state.adjust_selected_completion(-1.0)

    assert state.adjust_selected_completion(-10.0, allow_completed=True) is True
    assert task.status == ONGOING
    assert task.completion == 90.0


def test_adjust_selected_completion_rejects_groups() -> None:
    state = EditorState(Roadmap([TaskGroup("group", tasks=[Task("child")])]))

    with pytest.raises(TypeError, match="leaf tasks"):
        state.adjust_selected_completion(1.0)


def test_move_selected_row_swaps_visible_siblings_and_renumbers_sorted_only() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("first", order=1),
                Task("loose"),
                Task("second", order=2),
            ]
        )
    )
    state.select_path((2,))

    assert state.move_selected_row_up() is True

    assert [step.description for step in state.roadmap.steps] == [
        "first",
        "second",
        "loose",
    ]
    assert [step.order for step in state.roadmap.steps] == [1, 2, UNSORTED]
    assert state.selected_path == (1,)
    assert state.dirty is True


def test_move_selected_row_top_level_boundaries_are_noops() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second")]))

    assert state.move_selected_row_up() is False
    assert [step.description for step in state.roadmap.steps] == ["first", "second"]

    state.select_path((1,))
    assert state.move_selected_row_down() is False
    assert [step.description for step in state.roadmap.steps] == ["first", "second"]


def test_move_selected_row_outdents_first_child_before_parent() -> None:
    child = Task("child", order=1)
    group = TaskGroup("group", order=1, tasks=[child])
    state = EditorState(Roadmap([group, Task("after", order=2)]))
    state.select_path((0, 0))

    assert state.move_selected_row_up() is True

    assert [step.description for step in state.roadmap.steps] == ["child", "group", "after"]
    assert isinstance(state.roadmap.steps[1], Task)
    assert not isinstance(state.roadmap.steps[1], TaskGroup)
    assert [step.order for step in state.roadmap.steps] == [1, 2, 3]
    assert state.selected_path == (0,)


def test_move_selected_row_outdents_last_child_after_parent() -> None:
    child = Task("child", order=1)
    group = TaskGroup("group", order=1, tasks=[child])
    state = EditorState(Roadmap([Task("before", order=1), group]))
    state.select_path((1, 0))

    assert state.move_selected_row_down() is True

    assert [step.description for step in state.roadmap.steps] == ["before", "group", "child"]
    assert isinstance(state.roadmap.steps[1], Task)
    assert not isinstance(state.roadmap.steps[1], TaskGroup)
    assert [step.order for step in state.roadmap.steps] == [1, 2, 3]
    assert state.selected_path == (2,)


def test_move_selected_row_moves_groups_as_subtrees() -> None:
    group = TaskGroup("group", tasks=[Task("child")])
    state = EditorState(Roadmap([Task("first"), group]))
    state.select_path((1,))

    assert state.move_selected_row_up() is True

    assert state.roadmap.steps == [group, Task("first")]
    assert group.tasks == [Task("child")]
    assert state.selected_path == (0,)


def test_move_selected_row_allows_completed_rows() -> None:
    done = Task("done", status=COMPLETED)
    state = EditorState(Roadmap([Task("first"), done]))
    state.select_path((1,))

    assert state.move_selected_row_up() is True
    assert state.roadmap.steps == [done, Task("first")]


def test_move_selected_row_respects_visible_rows_when_completed_are_hidden() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("first"),
                Task("done", status=COMPLETED),
                Task("second"),
            ]
        ),
        hide_completed=True,
    )
    state.select_path((2,))

    assert state.move_selected_row_up() is True

    assert [step.description for step in state.roadmap.steps] == [
        "second",
        "done",
        "first",
    ]
    assert [row.description for row in state.rows] == ["second", "first"]
    assert state.selected_path == (0,)


def test_indent_selected_row_converts_previous_leaf_to_group_and_inherits_milestone() -> None:
    parent = Task("parent", order=1, milestone=2)
    child = Task("child", order=2)
    state = EditorState(Roadmap([parent, child, Task("loose")]))
    state.select_path((1,))

    assert state.indent_selected_row() is True

    group = state.roadmap.steps[0]
    assert isinstance(group, TaskGroup)
    assert group.description == "parent"
    assert group.milestone == 2
    assert group.tasks == [child]
    assert child.milestone == 2
    assert [step.description for step in state.roadmap.steps] == ["parent", "loose"]
    assert [step.order for step in state.roadmap.steps] == [1, UNSORTED]
    assert state.selected_path == (0, 0)
    assert state.dirty is True


def test_indent_selected_row_appends_to_existing_group_and_preserves_milestone() -> None:
    group = TaskGroup("group", tasks=[Task("existing")], milestone=3)
    child = Task("child", milestone=5)
    state = EditorState(Roadmap([group, child]))
    state.select_path((1,))

    assert state.indent_selected_row() is True

    assert group.tasks == [Task("existing"), child]
    assert child.milestone == 5
    assert state.selected_path == (0, 1)


def test_indent_selected_row_first_visible_sibling_is_noop() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second")]))

    assert state.indent_selected_row() is False
    assert [step.description for step in state.roadmap.steps] == ["first", "second"]
    assert state.dirty is False


def test_outdent_selected_row_moves_after_parent_and_converts_empty_parent() -> None:
    child = Task("child", order=1)
    group = TaskGroup("group", order=1, tasks=[child])
    state = EditorState(Roadmap([Task("before", order=1), group]))
    state.select_path((1, 0))

    assert state.outdent_selected_row() is True

    assert [step.description for step in state.roadmap.steps] == ["before", "group", "child"]
    assert isinstance(state.roadmap.steps[1], Task)
    assert not isinstance(state.roadmap.steps[1], TaskGroup)
    assert [step.order for step in state.roadmap.steps] == [1, 2, 3]
    assert state.selected_path == (2,)


def test_outdent_selected_row_top_level_is_noop() -> None:
    state = EditorState(Roadmap([Task("top")]))

    assert state.outdent_selected_row() is False
    assert state.dirty is False


def test_indent_and_outdent_move_groups_as_subtrees() -> None:
    parent = Task("parent")
    group = TaskGroup("group", tasks=[Task("child")])
    state = EditorState(Roadmap([parent, group]))
    state.select_path((1,))

    assert state.indent_selected_row() is True
    new_parent = state.roadmap.steps[0]
    assert isinstance(new_parent, TaskGroup)
    assert new_parent.tasks == [group]
    assert group.tasks == [Task("child")]

    assert state.outdent_selected_row() is True
    assert [step.description for step in state.roadmap.steps] == ["parent", "group"]
    assert group.tasks == [Task("child")]


def test_indent_and_outdent_allow_completed_rows() -> None:
    parent = Task("parent")
    done = Task("done", status=COMPLETED)
    state = EditorState(Roadmap([parent, done]))
    state.select_path((1,))

    assert state.indent_selected_row() is True
    group = state.roadmap.steps[0]
    assert isinstance(group, TaskGroup)
    assert group.tasks == [done]

    assert state.outdent_selected_row() is True
    assert state.roadmap.steps == [Task("parent"), done]


def test_indent_selected_row_uses_previous_visible_sibling_when_completed_hidden() -> None:
    first = Task("first")
    done = Task("done", status=COMPLETED)
    second = Task("second")
    state = EditorState(Roadmap([first, done, second]), hide_completed=True)
    state.select_path((2,))

    assert state.indent_selected_row() is True

    group = state.roadmap.steps[0]
    assert isinstance(group, TaskGroup)
    assert group.tasks == [second]
    assert state.roadmap.steps[1] is done
    assert state.selected_path == (0, 0)


def test_indent_outdent_renumber_sorted_only() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("parent", order=1),
                Task("child", order=2),
                Task("loose"),
            ]
        )
    )
    state.select_path((1,))

    assert state.indent_selected_row() is True

    assert [step.order for step in state.roadmap.steps] == [1, UNSORTED]
    state.outdent_selected_row()
    assert [step.order for step in state.roadmap.steps] == [1, 2, UNSORTED]


def test_toggle_selected_row_mark_persists_while_moving_cursor() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second")]))

    assert state.toggle_selected_row_mark() is True
    assert state.selected_paths == {(0,)}

    state.move_selection(1)
    assert state.selected_path == (1,)
    assert state.selected_paths == {(0,)}

    assert state.toggle_selected_row_mark() is True
    assert state.selected_paths == {(0,), (1,)}


def test_bulk_metadata_updates_selected_rows_and_skips_completed() -> None:
    first = Task("first")
    done = Task("done", status=COMPLETED)
    second = Task("second")
    state = EditorState(Roadmap([first, done, second]))
    state.selected_paths = {(0,), (1,), (2,)}

    assert state.update_selected_milestone(4) is True
    assert [task.milestone for task in state.roadmap.steps] == [4, 0, 4]
    assert state.selected_paths == set()

    state.selected_paths = {(0,), (1,), (2,)}
    assert state.update_selected_priority(OPTIONAL_TASK) is True
    assert first.optional is True
    assert done.optional is False
    assert second.optional is True
    assert state.selected_paths == set()


def test_bulk_completion_updates_valid_selected_rows() -> None:
    first = Task("first")
    group = TaskGroup("group", tasks=[Task("child")])
    done = Task("done", status=COMPLETED)
    state = EditorState(Roadmap([first, group, done]))
    state.selected_paths = {(0,), (1,), (2,)}

    assert state.update_selected_completion(25.0, allow_start=True) is True

    assert first.status == ONGOING
    assert first.completion == 25.0
    assert group.status == NOT_STARTED
    assert done.status == COMPLETED
    assert state.selected_paths == set()


def test_group_selected_rows_requires_same_parent() -> None:
    state = EditorState(
        Roadmap([Task("top"), TaskGroup("group", tasks=[Task("child")])])
    )
    state.selected_paths = {(0,), (1, 0)}

    with pytest.raises(ValueError, match="same parent"):
        state.group_selected_rows()


def test_group_selected_rows_replaces_siblings_with_new_group() -> None:
    first = Task("first", order=1)
    second = Task("second", order=2)
    loose = Task("loose")
    state = EditorState(Roadmap([first, second, loose]))
    state.selected_paths = {(0,), (1,)}

    group = state.group_selected_rows()

    assert group is not None
    assert group.description == NEW_GROUP_DESCRIPTION
    assert isinstance(state.roadmap.steps[0], TaskGroup)
    assert state.roadmap.steps[0].tasks == [first, second]
    assert [task.order for task in state.roadmap.steps[0].tasks] == [1, 2]
    assert [step.order for step in state.roadmap.steps] == [1, UNSORTED]
    assert state.selected_path == (0,)
    assert state.selected_paths == set()


def test_group_selected_rows_converts_single_focused_task() -> None:
    state = EditorState(Roadmap([Task("task")]))

    group = state.group_selected_rows()

    assert group == TaskGroup("task")
    assert isinstance(state.roadmap.steps[0], TaskGroup)
    assert state.selected_path == (0,)


@pytest.mark.parametrize("description", ["", None])
def test_group_selected_rows_repairs_invalid_focused_task_description(
    description: object,
) -> None:
    task = Task("task", order=10)
    task.description = description  # type: ignore[assignment]
    state = EditorState(Roadmap([task]))

    group = state.group_selected_rows()

    assert group is not None
    assert group.description == DEFAULT_TASK_GROUP_DESCRIPTION
    assert group.order == 10
    assert isinstance(state.roadmap.steps[0], TaskGroup)
    assert state.selected_path == (0,)


def test_toggle_selected_group_collapsed_hides_descendants_and_repairs_marks() -> None:
    group = TaskGroup("group", tasks=[Task("child"), Task("other")])
    state = EditorState(Roadmap([group, Task("after")]))
    state.selected_paths = {(0, 0)}

    assert state.toggle_selected_group_collapsed() is True

    assert [row.description for row in state.rows] == ["group", "after"]
    assert state.rows[0].collapsed is True
    assert state.selected_paths == set()

    assert state.toggle_selected_group_collapsed() is True
    assert [row.description for row in state.rows] == ["group", "child", "other", "after"]
