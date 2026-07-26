import pytest

from roadmaps import COMPLETED, MAX_PRIORITY, NOT_STARTED, ONGOING, UNSORTED
from roadmaps._editor_state import NEW_TASK_DESCRIPTION, EditorState
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


def test_hide_completed_resets_selection_to_first_visible_and_marks_dirty() -> None:
    state = EditorState(
        Roadmap(
            [
                Task("done", status=COMPLETED),
                Task("pending"),
                Task("also done", status=COMPLETED),
            ]
        )
    )
    state.select_path((2,))

    state.toggle_hide_completed()

    assert state.hide_completed is True
    assert state.dirty is True
    assert [row.description for row in state.rows] == ["pending"]
    assert state.selected_path == (1,)


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
