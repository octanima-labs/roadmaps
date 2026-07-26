import pytest

from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
)
from roadmaps._editor_state import (
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
    assert state.rows[0].order_text == "1."
    assert state.rows[0].completion_text == "0%"
    assert state.rows[0].milestone_text == "2"
    assert state.rows[0].group is True
    assert state.rows[1].priority_text == "!"
    assert state.rows[2].priority_text == "?"


def test_move_selection_clamps_without_marking_dirty() -> None:
    state = EditorState(Roadmap([Task("first"), Task("second")]))

    assert state.move_selection(1) is True
    assert state.selected_path == (1,)
    assert state.move_selection(1) is False
    assert state.selected_path == (1,)
    assert state.move_selection(-10) is True
    assert state.selected_path == (0,)
    assert state.dirty is False


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
