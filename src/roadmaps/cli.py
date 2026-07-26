from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import TextIO

from roadmaps._documents import (
    FORMATS,
    Document,
    Format,
    load_document,
    new_document,
    render_roadmap,
    save_document,
)
from roadmaps.constants import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NO_MILESTONE,
    ONGOING,
    UNSORTED,
)
from roadmaps.model import (
    Roadmap,
    Task,
    TaskGroup,
)

STATUSES = ("not-started", "ongoing", "completed")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roadmaps",
        description="Inspect and update roadmap files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    format_parent = argparse.ArgumentParser(add_help=False)
    format_parent.add_argument(
        "--format",
        choices=FORMATS,
        help="Input format. Defaults to extension inference.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        parents=[format_parent],
        help="Validate a roadmap file.",
    )
    validate_parser.add_argument("file", type=Path)
    validate_parser.set_defaults(handler=_handle_validate)

    next_parser = subparsers.add_parser(
        "next",
        parents=[format_parent],
        help="Show incomplete next-step tasks in the source format.",
    )
    next_parser.add_argument("file", type=Path)
    next_parser.set_defaults(handler=_handle_next)

    stats_parser = subparsers.add_parser(
        "stats",
        parents=[format_parent],
        help="Show roadmap completion and task counts.",
    )
    stats_parser.add_argument("file", type=Path)
    stats_parser.set_defaults(handler=_handle_stats)

    render_parser = subparsers.add_parser(
        "render",
        parents=[format_parent],
        help="Render a roadmap file to another supported format.",
    )
    render_parser.add_argument("file", type=Path)
    render_parser.add_argument("--to", choices=FORMATS, required=True)
    render_parser.set_defaults(handler=_handle_render)

    show_parser = subparsers.add_parser(
        "show",
        parents=[format_parent],
        help="Show roadmap items matching filters.",
    )
    show_parser.add_argument("file", type=Path)
    show_parser.add_argument("--to", choices=FORMATS, help="Output format.")
    show_parser.add_argument("-C", "--completed", action="store_true")
    show_parser.add_argument("-U", "--uncompleted", action="store_true")
    show_parser.add_argument("-O", "--ongoing", action="store_true")
    show_parser.add_argument("-o", "--optional", action="store_true")
    show_parser.add_argument("-A", "--all", action="store_true")
    show_parser.add_argument("-c", "--category", nargs="+", dest="categories")
    show_parser.set_defaults(handler=_handle_show)

    init_parser = subparsers.add_parser(
        "init",
        parents=[format_parent],
        help="Create a new empty roadmap file.",
    )
    init_parser.add_argument("file", type=Path)
    init_parser.add_argument(
        "--example",
        action="store_true",
        help="Create a feature-rich example roadmap instead of an empty one.",
    )
    init_parser.set_defaults(handler=_handle_init)

    add_task_parser = subparsers.add_parser(
        "add-task",
        parents=[format_parent],
        help="Append a top-level task to a roadmap file.",
    )
    add_task_parser.add_argument("file", type=Path)
    add_task_parser.add_argument("-d", "--description", required=True)
    add_task_parser.add_argument("--parent", help="1-based dotted path of parent item.")
    add_task_parser.add_argument("--order", type=int)
    add_task_parser.add_argument("--priority", type=int, default=0)
    add_task_parser.add_argument("--urgent", action="store_true")
    add_task_parser.add_argument("--optional", action="store_true")
    add_task_parser.add_argument("--milestone", type=int)
    add_task_parser.add_argument("--status", choices=STATUSES, default="not-started")
    add_task_parser.add_argument("--completion", type=float, default=0.0)
    add_task_parser.set_defaults(handler=_handle_add_task)

    editor_parser = subparsers.add_parser(
        "editor",
        parents=[format_parent],
        help="Launch the optional roadmap editor.",
    )
    editor_parser.add_argument("file", nargs="?", type=Path)
    editor_parser.set_defaults(handler=_handle_editor)

    return parser


def _handle_validate(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    print(f"valid {document.format} roadmap: {args.file}")
    return 0


def _handle_next(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    print(render_roadmap(Roadmap(document.roadmap.next_step()), document.format))
    return 0


def _handle_stats(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    roadmap = document.roadmap
    leaf_tasks = roadmap.leaf_tasks()
    completed = [task for task in leaf_tasks if task.status == COMPLETED]
    incomplete = [task for task in leaf_tasks if task.status != COMPLETED]
    print(f"completion: {roadmap.completion_percent}")
    print(f"tasks: {len(leaf_tasks)}")
    print(f"completed: {len(completed)}")
    print(f"incomplete: {len(incomplete)}")
    print(f"milestones: {len(roadmap.milestones())}")
    return 0


def _handle_render(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    print(render_roadmap(document.roadmap, args.to))
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    matches = document.roadmap.filter_items(
        completed=args.completed,
        uncompleted=args.uncompleted,
        ongoing=args.ongoing,
        optional=args.optional,
        all=args.all,
        categories=args.categories,
    )
    if not matches:
        print("no matching tasks")
        return 0

    output_format = args.to or document.format
    print(render_roadmap(Roadmap(_flat_show_items(matches)), output_format))
    return 0


def _handle_init(args: argparse.Namespace) -> int:
    if args.file.exists():
        print(f"error: file already exists: {args.file}", file=sys.stderr)
        return 1

    try:
        roadmap = _example_roadmap() if args.example else Roadmap()
        document = new_document(
            args.file,
            format_override=args.format,
            default="text",
            roadmap=roadmap,
        )
        save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"created {document.format} roadmap: {args.file}")
    return 0


def _handle_add_task(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    try:
        _add_task_from_args(document.roadmap, args)
        save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"added task to {document.format} roadmap: {args.file}")
    return 0


def _handle_editor(args: argparse.Namespace) -> int:
    try:
        import_module("textual")
    except ModuleNotFoundError:
        print(
            "error: Textual is required for the editor; install roadmaps[editor]",
            file=sys.stderr,
        )
        return 1

    print("error: editor UI is not implemented yet", file=sys.stderr)
    return 1


def _load_cli_document(
    path: Path,
    format_override: Format | None,
    stderr: TextIO | None = None,
) -> Document | None:
    stderr = sys.stderr if stderr is None else stderr
    try:
        return load_document(path, format_override)
    except OSError as exc:
        print(f"error: {exc}", file=stderr)
        return None
    except ValueError as exc:
        print(f"error: {exc}", file=stderr)
        return None

def _flat_show_items(items: list[Task | TaskGroup]) -> list[Task]:
    return [_show_item_snapshot(item) for item in items]


def _show_item_snapshot(item: Task | TaskGroup) -> Task:
    if not isinstance(item, TaskGroup):
        return item

    priority = item.priority
    if item.status == COMPLETED and not item.optional:
        priority = DEFAULT_PRIORITY
    return Task(
        item.description,
        order=item.order,
        priority=priority,
        status=item.status,
        optional=item.optional,
        milestone=item.milestone,
    )


def _example_roadmap() -> Roadmap:
    return Roadmap(
        [
            TaskGroup(
                "core: build **roadmap** model",
                order=1,
                milestone=1,
                tasks=[
                    Task(
                        "parser: support custom text",
                        order=1,
                        status=COMPLETED,
                        milestone=1,
                    ),
                    Task(
                        "cli: add write commands",
                        order=2,
                        priority=MAX_PRIORITY,
                        status=ONGOING,
                        milestone=1,
                        completion=50.0,
                    ),
                    Task("docs: publish [examples](#)", order=3, optional=True, milestone=1),
                ],
            ),
            Task("backlog: keep unordered idea", optional=True),
        ]
    )


def _add_task_from_args(roadmap: Roadmap, args: argparse.Namespace) -> None:
    if args.parent is None:
        roadmap.add_step(
            _task_from_args(
                args,
                order=UNSORTED if args.order is None else args.order,
                milestone=NO_MILESTONE if args.milestone is None else args.milestone,
            )
        )
        return

    if args.order is not None:
        msg = "--order cannot be combined with --parent"
        raise ValueError(msg)

    parent = _resolve_parent_path(roadmap, args.parent)
    group = parent if isinstance(parent, TaskGroup) else roadmap.task_to_group(parent)
    milestone = group.milestone if args.milestone is None else args.milestone
    group.add_task(
        _task_from_args(
            args,
            order=_next_child_order(group),
            milestone=milestone,
        )
    )


def _task_from_args(args: argparse.Namespace, *, order: int, milestone: int) -> Task:
    if args.urgent and args.priority:
        msg = "--urgent cannot be combined with --priority"
        raise ValueError(msg)
    priority = MAX_PRIORITY if args.urgent else args.priority
    status = _status_from_name(args.status)
    if status != ONGOING and args.completion:
        msg = "--completion can only be used with --status ongoing"
        raise ValueError(msg)

    task = Task(
        args.description,
        order=order,
        priority=priority,
        optional=args.optional,
        milestone=milestone,
    )
    if status == ONGOING:
        task.mark_ongoing(completion=args.completion)
    elif status == COMPLETED:
        task.mark_completed()
    return task


def _resolve_parent_path(roadmap: Roadmap, path: str) -> Task | TaskGroup:
    indexes = _parse_parent_path(path)
    items = roadmap.steps
    item: Task | TaskGroup | None = None

    for depth, index in enumerate(indexes, start=1):
        if index > len(items):
            msg = f"parent path '{path}' is out of range at segment {depth}"
            raise ValueError(msg)
        item = items[index - 1]
        if depth < len(indexes):
            if not isinstance(item, TaskGroup):
                msg = f"parent path '{path}' descends through a leaf task"
                raise ValueError(msg)
            items = item.tasks

    if item is None:
        msg = "parent path cannot be empty"
        raise ValueError(msg)
    return item


def _parse_parent_path(path: str) -> list[int]:
    parts = path.split(".")
    if not parts or any(part == "" for part in parts):
        msg = "parent path must use 1-based dotted indexes"
        raise ValueError(msg)

    indexes: list[int] = []
    for part in parts:
        if not part.isdecimal():
            msg = "parent path must use 1-based dotted indexes"
            raise ValueError(msg)
        index = int(part)
        if index < 1:
            msg = "parent path indexes must be positive"
            raise ValueError(msg)
        indexes.append(index)
    return indexes


def _next_child_order(group: TaskGroup) -> int:
    numbered_orders = [task.order for task in group.tasks if task.order > 0]
    if not numbered_orders:
        return 1
    return max(numbered_orders) + 1


def _status_from_name(name: str) -> int:
    if name == "not-started":
        return 0
    if name == "ongoing":
        return ONGOING
    return COMPLETED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
