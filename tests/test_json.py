import pytest

from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
    JSONValidationError,
    Roadmap,
    Task,
    TaskGroup,
)


def test_task_dict_round_trip_includes_all_fields() -> None:
    task = Task("write JSON", order=2, priority=900, status=ONGOING, milestone=1)

    data = task.to_dict()

    assert data == {
        "description": "write JSON",
        "order": 2,
        "status": ONGOING,
        "priority": 900,
        "optional": False,
        "milestone": 1,
        "completion": 0.0,
    }
    assert Task.from_dict(data) == task


def test_optional_task_serializes_with_priority_sentinel() -> None:
    task = Task("optional JSON", optional=True)

    assert task.to_dict()["priority"] == OPTIONAL_TASK
    assert task.to_dict()["optional"] is True
    assert Task.from_dict(task.to_dict()) == task


def test_task_group_dict_round_trip_uses_tasks_to_imply_group() -> None:
    child = Task("child", status=COMPLETED)
    group = TaskGroup("group", order=1, tasks=[child, Task("optional", optional=True)])

    data = group.to_dict()

    assert "tasks" in data
    assert data["status"] == COMPLETED
    assert data["completion"] == 100.0
    assert TaskGroup.from_dict(data) == group


def test_roadmap_json_round_trip_uses_stable_pretty_output() -> None:
    roadmap = Roadmap([Task("write JSON")])

    assert roadmap.to_json() == (
        '{\n'
        '  "steps": [\n'
        '    {\n'
        '      "description": "write JSON",\n'
        f'      "order": {UNSORTED},\n'
        f'      "status": {NOT_STARTED},\n'
        f'      "priority": {DEFAULT_PRIORITY},\n'
        '      "optional": false,\n'
        '      "milestone": 0,\n'
        '      "completion": 0.0\n'
        '    }\n'
        '  ],\n'
        '  "completion": 0.0\n'
        '}'
    )
    assert Roadmap.from_json(roadmap.to_json()) == roadmap


def test_roadmap_round_trip_preserves_nested_groups() -> None:
    roadmap = Roadmap(
        [
            TaskGroup(
                "group",
                tasks=[
                    Task("done", status=COMPLETED),
                    Task("pending", priority=MAX_PRIORITY, milestone=2),
                ],
            )
        ]
    )

    assert Roadmap.from_dict(roadmap.to_dict()) == roadmap


def test_from_dict_ignores_read_only_derived_values() -> None:
    data = {
        "description": "group",
        "order": UNSORTED,
        "status": NOT_STARTED,
        "priority": DEFAULT_PRIORITY,
        "optional": False,
        "milestone": 0,
        "completion": 0.0,
        "tasks": [
            {
                "description": "done",
                "order": UNSORTED,
                "status": COMPLETED,
                "priority": DEFAULT_PRIORITY,
                "optional": False,
                "milestone": 0,
                "completion": 0.0,
            }
        ],
    }

    group = TaskGroup.from_dict(data)

    assert group.status == COMPLETED
    assert group.completion == 100.0


def test_from_dict_rejects_unknown_fields() -> None:
    with pytest.raises(JSONValidationError, match=r"\$: unknown field\(s\): extra"):
        Roadmap.from_dict({"steps": [], "completion": 0.0, "extra": True})


def test_from_dict_rejects_missing_required_fields() -> None:
    with pytest.raises(JSONValidationError, match=r"\$: missing required field\(s\): completion"):
        Roadmap.from_dict({"steps": []})


def test_from_dict_rejects_nested_invalid_values_with_json_path() -> None:
    data = Roadmap([TaskGroup("group", tasks=[Task("child")])]).to_dict()
    data["steps"][0]["tasks"][0]["priority"] = OPTIONAL_TASK

    with pytest.raises(
        JSONValidationError,
        match=r"\$\.steps\[0\]\.tasks\[0\]\.priority: mandatory tasks",
    ):
        Roadmap.from_dict(data)


def test_from_dict_rejects_completed_mandatory_task_with_priority() -> None:
    data = Task("completed", status=COMPLETED).to_dict()
    data["priority"] = MAX_PRIORITY

    with pytest.raises(JSONValidationError, match=r"\$\.priority: completed mandatory"):
        Task.from_dict(data)


def test_from_json_reports_syntax_line_and_column() -> None:
    with pytest.raises(JSONValidationError, match=r"line 2, column 1"):
        Roadmap.from_json('{"steps": [\n}')
