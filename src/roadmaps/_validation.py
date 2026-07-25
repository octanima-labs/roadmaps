from __future__ import annotations

import re
from datetime import UTC, datetime

from roadmaps.constants import COMPLETED, NOT_STARTED, ONGOING


def _validated_task_completion(
    value: float,
    status: int,
    path: str,
    error_type: type[ValueError],
) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"{path}: must be a number"
        raise error_type(msg)

    completion = float(value)
    if not _has_one_decimal_place(completion):
        msg = f"{path}: must use at most one decimal place"
        raise error_type(msg)

    if status == ONGOING:
        if completion == 0.0:
            return 0.0
        if 1.0 <= completion <= 99.0:
            return completion
        msg = f"{path}: ongoing completion must be between 1.0 and 99.0"
        raise error_type(msg)
    if status == NOT_STARTED:
        if completion == 0.0:
            return 0.0
        msg = f"{path}: not-started tasks must use 0.0 completion"
        raise error_type(msg)
    if completion in {0.0, 100.0}:
        return 0.0
    msg = f"{path}: completed tasks must use 100.0 completion"
    raise error_type(msg)


def _has_one_decimal_place(value: float) -> bool:
    return round(value, 1) == value


def _format_completion_percent(completion: float) -> str:
    if completion.is_integer():
        return f"{int(completion)}%"
    return f"{completion:.1f}%"


def _timestamp_or_now(timestamp: datetime | None) -> datetime:
    if timestamp is None:
        return datetime.now(UTC)
    normalized = _normalize_datetime(timestamp, "timestamp", ValueError)
    if normalized is None:  # pragma: no cover - timestamp is known non-None here.
        msg = "timestamp: must be a datetime"
        raise ValueError(msg)
    return normalized


def _normalize_datetime(
    value: datetime | None,
    path: str,
    error_type: type[ValueError],
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        msg = f"{path}: must be a datetime or None"
        raise error_type(msg)
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{path}: must be timezone-aware"
        raise error_type(msg)
    return value.astimezone(UTC)


def _validate_task_dates(
    status: int,
    start_date: datetime | None,
    completion_date: datetime | None,
    path: str,
    error_type: type[ValueError],
) -> None:
    if status == NOT_STARTED and (start_date is not None or completion_date is not None):
        msg = f"{path}: not-started tasks cannot have dates"
        raise error_type(msg)
    if status == ONGOING and completion_date is not None:
        msg = f"{path}: ongoing tasks cannot have a completion_date"
        raise error_type(msg)
    if completion_date is not None and status != COMPLETED:
        msg = f"{path}: completion_date requires completed status"
        raise error_type(msg)
    if (
        start_date is not None
        and completion_date is not None
        and completion_date < start_date
    ):
        msg = f"{path}: completion_date cannot be earlier than start_date"
        raise error_type(msg)


def _validate_description(
    description: str,
    path: str,
    error_type: type[ValueError],
) -> None:
    for line in description.splitlines():
        _validate_description_line(line, path, error_type)


def _validate_description_line(
    line: str,
    path: str,
    error_type: type[ValueError],
) -> None:
    stripped = line.strip()
    if not stripped:
        return
    if stripped.startswith("#"):
        msg = f"{path}: headings are not allowed in task descriptions"
        raise error_type(msg)
    if stripped.startswith((">", "```", "~~~")):
        msg = f"{path}: block Markdown is not allowed in task descriptions"
        raise error_type(msg)
    if _is_markdown_table_separator(stripped):
        msg = f"{path}: Markdown tables are not allowed in task descriptions"
        raise error_type(msg)


def _is_markdown_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell)
