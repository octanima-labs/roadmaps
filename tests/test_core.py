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


def test_task_description_allows_inline_markdown_text() -> None:
    description = "docs: use **bold**, *italic*, `code`, $x^2$, and [links](#)"

    task = Task(description)

    assert task.description == description


@pytest.mark.parametrize(
    "description",
    [
        "# heading",
        "description\n## heading",
        "description\n```python",
        "description\n~~~",
        "description\n> quote",
        "description\n| --- | --- |",
    ],
)
def test_task_description_rejects_block_markdown(description: str) -> None:
    with pytest.raises(ValueError, match="description"):
        Task(description)


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


def test_filter_items_matches_groups_and_tasks_in_traversal_order() -> None:
    child = Task("docs: child")
    group = TaskGroup("docs: parent", tasks=[child])
    roadmap = Roadmap([group, Task("core: sibling")])

    assert roadmap.filter_items(categories=["docs"]) == [group, child]


def test_filter_items_status_filters_use_union() -> None:
    completed = Task("done", status=COMPLETED)
    ongoing = Task("ongoing", status=ONGOING)
    pending = Task("pending")
    roadmap = Roadmap([completed, ongoing, pending])

    assert roadmap.filter_items(completed=True, ongoing=True) == [completed, ongoing]
    assert roadmap.filter_items(uncompleted=True) == [ongoing, pending]


def test_filter_items_hides_optional_by_default_and_optional_is_union() -> None:
    completed = Task("done", status=COMPLETED)
    optional = Task("optional", optional=True)
    roadmap = Roadmap([completed, optional])

    assert roadmap.filter_items(completed=True) == [completed]
    assert roadmap.filter_items(completed=True, optional=True) == [completed, optional]


def test_filter_items_all_ignores_other_filters() -> None:
    optional = Task("docs: optional", optional=True)
    uncategorized = Task("uncategorized")
    roadmap = Roadmap([optional, uncategorized])

    assert roadmap.filter_items(all=True, categories=["missing"]) == [
        optional,
        uncategorized,
    ]


def test_filter_items_categories_match_conventional_prefix_case_insensitively() -> None:
    docs = Task("Docs: publish examples")
    scoped = Task("feat(parser): parse categories")
    uncategorized = Task("no category")
    roadmap = Roadmap([docs, scoped, uncategorized])

    assert roadmap.filter_items(categories=["docs", "FEAT(parser)"]) == [docs, scoped]


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


def test_task_to_group_preserves_metadata_and_drops_completion() -> None:
    child = Task("child")
    task = Task(
        "partial",
        order=2,
        priority=MAX_PRIORITY,
        status=ONGOING,
        milestone=3,
        completion=50.0,
    )

    group = task.to_group(tasks=[child])

    assert group.description == "partial"
    assert group.order == 2
    assert group.priority == MAX_PRIORITY
    assert group.milestone == 3
    assert group.status == NOT_STARTED
    assert group.completion == 0.0
    assert group.tasks == [child]


def test_group_to_task_preserves_metadata_and_uses_derived_status() -> None:
    group = TaskGroup(
        "group",
        order=1,
        priority=900,
        milestone=2,
        tasks=[Task("done", status=COMPLETED), Task("pending")],
    )

    task = group.to_task()

    assert task.description == "group"
    assert task.order == 1
    assert task.priority == 900
    assert task.status == ONGOING
    assert task.completion == 0.0
    assert task.milestone == 2


def test_roadmap_task_to_group_replaces_nested_task_by_identity() -> None:
    target = Task("target", order=1, priority=500, milestone=2)
    equal_but_not_identical = Task("target", order=1, priority=500, milestone=2)
    child = Task("child")
    parent = TaskGroup("parent", tasks=[equal_but_not_identical, target])
    roadmap = Roadmap([parent])

    group = roadmap.task_to_group(target, tasks=[child])

    assert group == TaskGroup(
        "target",
        order=1,
        priority=500,
        milestone=2,
        tasks=[child],
    )
    assert parent.tasks == [equal_but_not_identical, group]
    assert parent.tasks[0] is equal_but_not_identical


def test_roadmap_group_to_task_flattens_children_as_following_siblings() -> None:
    first = Task("first", order=1)
    second = Task("second", order=2)
    group = TaskGroup("group", order=1, milestone=4, tasks=[first, second])
    after = Task("after", order=2)
    roadmap = Roadmap([group, after])

    task = roadmap.group_to_task(group)

    assert task == Task("group", order=1, milestone=4)
    assert roadmap.steps == [task, first, second, after]


def test_task_group_conversion_helpers_work_for_nested_items() -> None:
    leaf = Task("leaf")
    nested_group = TaskGroup("nested", tasks=[leaf])
    parent = TaskGroup("parent", tasks=[nested_group])

    converted_group = parent.task_to_group(leaf, tasks=[Task("new child")])

    assert nested_group.tasks == [converted_group]

    converted_task = parent.group_to_task(converted_group)

    assert nested_group.tasks == [converted_task, Task("new child")]


def test_conversion_helpers_raise_when_target_is_not_found() -> None:
    roadmap = Roadmap([Task("existing")])

    with pytest.raises(ValueError, match="not found"):
        roadmap.task_to_group(Task("missing"))

    with pytest.raises(ValueError, match="not found"):
        roadmap.group_to_task(TaskGroup("missing"))


def test_converted_items_round_trip_through_formats() -> None:
    target = Task("target", priority=900, milestone=1)
    child = Task("child")
    roadmap = Roadmap([target])

    group = roadmap.task_to_group(target, tasks=[child])
    roadmap.group_to_task(group)

    assert Roadmap.from_text(roadmap.to_text()) == roadmap
    assert Roadmap.from_markdown(roadmap.to_markdown()) == roadmap
    assert Roadmap.from_json(roadmap.to_json()) == roadmap


def test_add_step_accepts_top_level_tasks_only() -> None:
    roadmap = Roadmap()
    task = Task("top level")

    roadmap.add_step(task)

    assert roadmap.steps == [task]

    with pytest.raises(TypeError, match="Task or TaskGroup"):
        roadmap.add_step("not a task")  # type: ignore[arg-type]
