import pytest

from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
    Roadmap,
    Task,
    TaskGroup,
)


def test_task_defaults_and_completion() -> None:
    task = Task("write tests")

    assert task.order == UNSORTED
    assert task.priority == DEFAULT_PRIORITY
    assert task.status == NOT_STARTED
    assert task.completion == 0.0
    assert task.completion_percent == "0%"

    task.mark_completed()

    assert task.status == COMPLETED
    assert task.completion == 100.0
    assert task.completion_percent == "100%"


def test_task_rejects_optional_positive_priority_conflict() -> None:
    with pytest.raises(ValueError, match="optional tasks"):
        Task("conflicting metadata", priority=1, optional=True)


def test_optional_priority_marker_sets_optional_task() -> None:
    task = Task("optional task", priority=OPTIONAL_TASK)

    assert task.is_optional()
    assert task.priority == OPTIONAL_TASK


def test_mark_completed_removes_mandatory_priority() -> None:
    task = Task("urgent task", priority=MAX_PRIORITY)

    task.mark_completed()

    assert task.status == COMPLETED
    assert task.priority == DEFAULT_PRIORITY


def test_ongoing_task_accepts_custom_completion() -> None:
    task = Task("partly done", status=ONGOING, completion=50.5)

    assert task.completion == 50.5
    assert task.completion_percent == "50.5%"

    task.mark_not_started()

    assert task.status == NOT_STARTED
    assert task.completion == 0.0

    task.mark_ongoing(75.0)

    assert task.status == ONGOING
    assert task.completion == 75.0

    task.mark_completed()

    assert task.status == COMPLETED
    assert task.completion == 100.0


@pytest.mark.parametrize("completion", [0.5, 99.5, 100.0, 50.55])
def test_ongoing_task_rejects_invalid_custom_completion(completion: float) -> None:
    with pytest.raises(ValueError):
        Task("invalid completion", status=ONGOING, completion=completion)


def test_mark_completed_preserves_optionality() -> None:
    task = Task("optional task", optional=True)

    task.mark_completed()

    assert task.status == COMPLETED
    assert task.is_optional()
    assert task.priority == OPTIONAL_TASK


def test_task_group_status_is_derived_from_children() -> None:
    first = Task("first")
    second = Task("second")
    group = TaskGroup("group", tasks=[first, second])

    assert group.status == NOT_STARTED

    first.mark_ongoing()
    assert group.status == ONGOING

    first.mark_completed()
    second.mark_completed()
    assert group.status == COMPLETED


def test_task_group_rejects_explicit_ongoing_completion() -> None:
    group = TaskGroup("group", tasks=[Task("child")])

    with pytest.raises(ValueError, match="task groups"):
        group.mark_ongoing(50.0)


def test_completion_ignores_optional_tasks() -> None:
    required = Task("required", status=ONGOING, completion=50.0)
    optional = Task("optional", optional=True)
    group = TaskGroup("group", tasks=[required, optional])
    roadmap = Roadmap([group, Task("top optional", optional=True)])

    assert group.completion == 50.0
    assert roadmap.completion == 50.0

    required.mark_completed()

    assert group.completion == 100.0
    assert roadmap.completion == 100.0


def test_next_step_returns_incomplete_leaf_tasks_in_priority_order() -> None:
    roadmap = Roadmap(
        [
            Task("unordered"),
            Task("ordered later", order=2),
            Task("ordered first", order=1),
            Task("ongoing", status=ONGOING),
            Task("high priority", priority=900),
            TaskGroup("group", tasks=[Task("nested priority", priority=500)]),
            Task("done", priority=MAX_PRIORITY, status=COMPLETED),
        ]
    )

    assert [task.description for task in roadmap.next_step()] == [
        "high priority",
        "nested priority",
        "ongoing",
        "ordered first",
        "ordered later",
        "unordered",
    ]


def test_milestones_group_nested_items_and_filter_completion() -> None:
    completed = Task("completed", milestone=1, status=COMPLETED)
    pending = Task("pending", milestone=1)
    other = Task("other", milestone=2)
    roadmap = Roadmap([TaskGroup("group", milestone=1, tasks=[completed, pending]), other])

    assert [item.description for item in roadmap.milestones(index=1)[1]] == [
        "completed",
        "pending",
    ]
    assert [item.description for item in roadmap.milestones(completed=True)[1]] == [
        "completed",
    ]
    assert [item.description for item in roadmap.milestones(completed=False)[1]] == [
        "pending",
    ]


def test_add_step_accepts_top_level_tasks_only() -> None:
    roadmap = Roadmap()
    task = Task("top level")

    roadmap.add_step(task)

    assert roadmap.steps == [task]

    with pytest.raises(TypeError, match="Task or TaskGroup"):
        roadmap.add_step("not a task")  # type: ignore[arg-type]
