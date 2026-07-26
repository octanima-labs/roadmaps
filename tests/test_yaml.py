from datetime import UTC, datetime
from importlib import import_module
from typing import Any

import pytest

from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NOT_STARTED,
    ONGOING,
    UNSORTED,
    Roadmap,
    Task,
    TaskGroup,
    YAMLValidationError,
)


def _yaml() -> Any:
    return import_module("yaml")


def test_task_yaml_round_trip_uses_json_schema_fields() -> None:
    task = Task(
        "write YAML",
        order=2,
        priority=900,
        status=ONGOING,
        milestone=1,
        completion=50.0,
        start_date=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
    )

    data = _yaml().safe_load(task.to_yaml())

    assert data == {
        "description": "write YAML",
        "order": 2,
        "status": ONGOING,
        "priority": 900,
        "optional": False,
        "milestone": 1,
        "completion": 50.0,
        "start_date": "2026-01-01T10:30:00Z",
    }
    assert Task.from_yaml(task.to_yaml()) == task


def test_task_group_yaml_round_trip_includes_child_tasks() -> None:
    group = TaskGroup(
        "group",
        tasks=[Task("done", status=COMPLETED), Task("pending", priority=MAX_PRIORITY)],
    )

    data = _yaml().safe_load(group.to_yaml())

    loaded = TaskGroup.from_yaml(group.to_yaml())

    assert "tasks" in data
    assert len(data["tasks"]) == 2
    assert loaded == group


def test_roadmap_yaml_round_trip_uses_stable_schema() -> None:
    roadmap = Roadmap([Task("write YAML")])

    assert _yaml().safe_load(roadmap.to_yaml()) == {
        "steps": [
            {
                "description": "write YAML",
                "order": UNSORTED,
                "status": NOT_STARTED,
                "priority": DEFAULT_PRIORITY,
                "optional": False,
                "milestone": 0,
                "completion": 0.0,
            }
        ],
        "completion": 0.0,
    }
    assert Roadmap.from_yaml(roadmap.to_yaml()) == roadmap


def test_from_yaml_rejects_unknown_fields_with_schema_path() -> None:
    source = """
steps: []
completion: 0.0
extra: true
""".strip()

    with pytest.raises(YAMLValidationError, match=r"\$: unknown field\(s\): extra"):
        Roadmap.from_yaml(source)


def test_from_yaml_rejects_nested_invalid_values_with_yaml_error_type() -> None:
    data = Roadmap([TaskGroup("group", tasks=[Task("child")])]).to_dict()
    data["steps"][0]["tasks"][0]["priority"] = -1

    with pytest.raises(
        YAMLValidationError,
        match=r"\$\.steps\[0\]\.tasks\[0\]\.priority: mandatory tasks",
    ):
        Roadmap.from_yaml(_yaml().safe_dump(data, sort_keys=False))


def test_from_yaml_reports_decode_line_and_column() -> None:
    with pytest.raises(YAMLValidationError, match=r"Invalid YAML at line 2, column"):
        Roadmap.from_yaml("steps:\n  - [")
