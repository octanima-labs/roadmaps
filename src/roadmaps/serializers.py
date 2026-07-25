from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from roadmaps._validation import (
    _normalize_datetime,
    _validate_task_dates,
    _validated_task_completion,
)
from roadmaps.constants import (
    COMPLETED,
    DEFAULT_PRIORITY,
    NO_MILESTONE,
    OPTIONAL_TASK,
    UNSORTED,
    VALID_STATUSES,
)
from roadmaps.model import (
    Roadmap,
    Task,
    TaskGroup,
)

TASK_JSON_KEYS = {
    "completion_date",
    "completion",
    "description",
    "milestone",
    "optional",
    "order",
    "priority",
    "start_date",
    "status",
}
TASK_JSON_OPTIONAL_KEYS = {"completion_date", "start_date"}
TASK_GROUP_JSON_KEYS = TASK_JSON_KEYS | {"tasks"}
ROADMAP_JSON_KEYS = {"completion", "steps"}


class JSONValidationError(ValueError):
    """Raised when roadmap JSON cannot be decoded or validated."""


class JsonSerializer:
    @staticmethod
    def task_to_dict(task: Task) -> dict[str, Any]:
        data = {
            "description": task.description,
            "order": task.order,
            "status": task.status,
            "priority": task.priority,
            "optional": task.optional,
            "milestone": task.milestone,
            "completion": task.completion,
        }
        if task.start_date is not None:
            data["start_date"] = _datetime_to_json(task.start_date)
        if task.completion_date is not None:
            data["completion_date"] = _datetime_to_json(task.completion_date)
        return data

    @staticmethod
    def task_from_dict(data: object) -> Task:
        if _is_json_group(data):
            msg = "$.tasks: unexpected field for Task"
            raise JSONValidationError(msg)
        return _task_from_mapping(_require_mapping(data, "$"), "$")

    @staticmethod
    def task_to_json(task: Task) -> str:
        return json.dumps(JsonSerializer.task_to_dict(task), indent=2)

    @staticmethod
    def task_from_json(source: str) -> Task:
        return JsonSerializer.task_from_dict(_loads_json(source))

    @staticmethod
    def task_group_to_dict(group: TaskGroup) -> dict[str, Any]:
        data = JsonSerializer.task_to_dict(group)
        data["tasks"] = [JsonSerializer.item_to_dict(task) for task in group.tasks]
        return data

    @staticmethod
    def task_group_from_dict(data: object) -> TaskGroup:
        mapping = _require_mapping(data, "$")
        return _task_group_from_mapping(mapping, "$")

    @staticmethod
    def task_group_from_json(source: str) -> TaskGroup:
        return JsonSerializer.task_group_from_dict(_loads_json(source))

    @staticmethod
    def item_to_dict(item: Task | TaskGroup) -> dict[str, Any]:
        if isinstance(item, TaskGroup):
            return JsonSerializer.task_group_to_dict(item)
        return JsonSerializer.task_to_dict(item)

    @staticmethod
    def roadmap_to_dict(roadmap: Roadmap) -> dict[str, Any]:
        return {
            "steps": [JsonSerializer.item_to_dict(step) for step in roadmap.steps],
            "completion": roadmap.completion,
        }

    @staticmethod
    def roadmap_from_dict(data: object) -> Roadmap:
        mapping = _require_mapping(data, "$")
        _validate_keys(mapping, ROADMAP_JSON_KEYS, "$")
        _validate_completion(_require_number(mapping["completion"], "$.completion"), "$.completion")
        steps = _require_list(mapping["steps"], "$.steps")
        return Roadmap(
            [
                _item_from_mapping(
                    _require_mapping(step, f"$.steps[{index}]"),
                    f"$.steps[{index}]",
                )
                for index, step in enumerate(steps)
            ]
        )

    @staticmethod
    def roadmap_to_json(roadmap: Roadmap) -> str:
        return json.dumps(JsonSerializer.roadmap_to_dict(roadmap), indent=2)

    @staticmethod
    def roadmap_from_json(source: str) -> Roadmap:
        return JsonSerializer.roadmap_from_dict(_loads_json(source))


def _datetime_to_json(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _datetime_from_json(value: object, path: str) -> datetime:
    if not isinstance(value, str):
        msg = f"{path}: must be an ISO timestamp string"
        raise JSONValidationError(msg)
    source = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(source)
    except ValueError as exc:
        msg = f"{path}: must be a valid ISO timestamp"
        raise JSONValidationError(msg) from exc
    normalized = _normalize_datetime(parsed, path, JSONValidationError)
    if normalized is None:  # pragma: no cover - parsed is known non-None here.
        msg = f"{path}: must be an ISO timestamp string"
        raise JSONValidationError(msg)
    return normalized


def _loads_json(source: str) -> object:
    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        raise JSONValidationError(msg) from exc


def _is_json_group(data: object) -> bool:
    return isinstance(data, Mapping) and "tasks" in data


def _item_from_mapping(mapping: Mapping[str, object], path: str) -> Task | TaskGroup:
    if "tasks" in mapping:
        return _task_group_from_mapping(mapping, path)
    return _task_from_mapping(mapping, path)


def _task_from_mapping(mapping: Mapping[str, object], path: str) -> Task:
    values = _task_values_from_mapping(
        mapping,
        path,
        TASK_JSON_KEYS,
        load_leaf_completion=True,
    )
    return Task(**values)


def _task_group_from_mapping(mapping: Mapping[str, object], path: str) -> TaskGroup:
    values = _task_values_from_mapping(
        mapping,
        path,
        TASK_GROUP_JSON_KEYS,
        load_leaf_completion=False,
    )
    values.pop("status")
    tasks = _require_list(mapping["tasks"], f"{path}.tasks")
    return TaskGroup(
        **values,
        tasks=[
            _item_from_mapping(
                _require_mapping(task, f"{path}.tasks[{index}]"),
                f"{path}.tasks[{index}]",
            )
            for index, task in enumerate(tasks)
        ],
    )


def _task_values_from_mapping(
    mapping: Mapping[str, object],
    path: str,
    allowed_keys: set[str],
    *,
    load_leaf_completion: bool,
) -> dict[str, Any]:
    _validate_keys(
        mapping,
        allowed_keys,
        path,
        required_keys=allowed_keys - TASK_JSON_OPTIONAL_KEYS,
    )

    description = _require_str(mapping["description"], f"{path}.description")
    order = _require_int(mapping["order"], f"{path}.order")
    status = _require_int(mapping["status"], f"{path}.status")
    priority = _require_int(mapping["priority"], f"{path}.priority")
    optional = _require_bool(mapping["optional"], f"{path}.optional")
    milestone = _require_int(mapping["milestone"], f"{path}.milestone")
    completion = _require_number(mapping["completion"], f"{path}.completion")
    start_date = _optional_datetime_from_mapping(mapping, "start_date", path)
    completion_date = _optional_datetime_from_mapping(mapping, "completion_date", path)
    _validate_completion(completion, f"{path}.completion")

    if status not in VALID_STATUSES:
        msg = f"{path}.status: must be NOT_STARTED, ONGOING, or COMPLETED"
        raise JSONValidationError(msg)
    if order < UNSORTED:
        msg = f"{path}.order: must be UNSORTED or a non-negative integer"
        raise JSONValidationError(msg)
    if milestone < NO_MILESTONE:
        msg = f"{path}.milestone: must be a non-negative integer"
        raise JSONValidationError(msg)
    if optional and priority != OPTIONAL_TASK:
        msg = f"{path}.priority: optional tasks must use priority {OPTIONAL_TASK}"
        raise JSONValidationError(msg)
    if not optional and priority < DEFAULT_PRIORITY:
        msg = f"{path}.priority: mandatory tasks must use a non-negative priority"
        raise JSONValidationError(msg)
    if status == COMPLETED and not optional and priority != DEFAULT_PRIORITY:
        msg = f"{path}.priority: completed mandatory tasks must use default priority"
        raise JSONValidationError(msg)
    _validate_task_dates(
        status,
        start_date,
        completion_date,
        f"{path}.date",
        JSONValidationError,
    )
    if load_leaf_completion:
        if status == COMPLETED and completion != 100.0:
            msg = f"{path}.completion: completed tasks must use 100.0 completion"
            raise JSONValidationError(msg)
        completion = _validated_task_completion(
            completion,
            status,
            f"{path}.completion",
            JSONValidationError,
        )

    values: dict[str, Any] = {
        "description": description,
        "order": order,
        "priority": priority,
        "status": status,
        "optional": optional,
        "milestone": milestone,
    }
    if load_leaf_completion:
        values["completion"] = completion
        values["start_date"] = start_date
        values["completion_date"] = completion_date
    return values


def _validate_keys(
    mapping: Mapping[str, object],
    allowed_keys: set[str],
    path: str,
    required_keys: set[str] | None = None,
) -> None:
    keys = set(mapping)
    required = allowed_keys if required_keys is None else required_keys
    missing = required - keys
    unknown = keys - allowed_keys
    if missing:
        fields = ", ".join(sorted(missing))
        msg = f"{path}: missing required field(s): {fields}"
        raise JSONValidationError(msg)
    if unknown:
        fields = ", ".join(sorted(unknown))
        msg = f"{path}: unknown field(s): {fields}"
        raise JSONValidationError(msg)


def _require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{path}: must be a JSON object"
        raise JSONValidationError(msg)
    return value


def _require_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        msg = f"{path}: must be a JSON array"
        raise JSONValidationError(msg)
    return value


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        msg = f"{path}: must be a string"
        raise JSONValidationError(msg)
    return value


def _require_int(value: object, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{path}: must be an integer"
        raise JSONValidationError(msg)
    return value


def _require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{path}: must be a boolean"
        raise JSONValidationError(msg)
    return value


def _optional_datetime_from_mapping(
    mapping: Mapping[str, object],
    key: str,
    path: str,
) -> datetime | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if value is None:
        return None
    return _datetime_from_json(value, f"{path}.{key}")


def _require_number(value: object, path: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{path}: must be a number"
        raise JSONValidationError(msg)
    return float(value)


def _validate_completion(value: float, path: str) -> None:
    if not 0 <= value <= 100:
        msg = f"{path}: must be between 0 and 100"
        raise JSONValidationError(msg)
