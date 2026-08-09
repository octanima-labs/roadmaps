from __future__ import annotations

import argparse
import sys
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
from roadmaps._validation import _validate_description
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
        prog="roadmap",
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
    next_parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of next tasks to show. Must be at least 1.",
    )
    next_parser.set_defaults(handler=_handle_next)

    stats_parser = subparsers.add_parser(
        "stats",
        parents=[format_parent],
        help="Show roadmap completion and task counts.",
    )
    stats_parser.add_argument("file", type=Path)
    stats_parser.set_defaults(handler=_handle_stats)

    export_parser = subparsers.add_parser(
        "export",
        parents=[format_parent],
        help="Export a roadmap file to another supported format.",
    )
    export_parser.add_argument("file", type=Path)
    export_parser.add_argument("--to", choices=FORMATS, required=True)
    export_parser.set_defaults(handler=_handle_render)

    search_parser = subparsers.add_parser(
        "search",
        parents=[format_parent],
        help="Search roadmap items matching filters.",
    )
    search_parser.add_argument("file", type=Path)
    search_parser.add_argument("--to", choices=FORMATS, help="Output format.")
    search_parser.add_argument("-C", "--completed", action="store_true")
    search_parser.add_argument("-U", "--uncompleted", action="store_true")
    search_parser.add_argument("-O", "--ongoing", action="store_true")
    search_parser.add_argument("-o", "--optional", action="store_true")
    search_parser.add_argument("-A", "--all", action="store_true")
    search_parser.add_argument("-c", "--category", nargs="+", dest="categories")
    search_parser.set_defaults(handler=_handle_show)

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

    task_parser = subparsers.add_parser(
        "task",
        help="Update roadmap tasks and task groups.",
    )
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)

    add_task_parser = task_subparsers.add_parser(
        "add",
        parents=[format_parent],
        help="Append a top-level task or nested child to a roadmap file.",
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

    set_parser = task_subparsers.add_parser(
        "set",
        parents=[format_parent],
        help="Update an existing roadmap item by path.",
    )
    set_parser.add_argument("file", type=Path)
    set_parser.add_argument("path", help="1-based dotted item path.")
    set_parser.add_argument("-d", "--description")
    set_parser.add_argument("--priority", type=int)
    set_parser.add_argument("--urgent", action="store_true")
    optional_group = set_parser.add_mutually_exclusive_group()
    optional_group.add_argument("--optional", action="store_true")
    optional_group.add_argument("--not-optional", action="store_true")
    set_parser.add_argument("--milestone", type=int)
    set_parser.add_argument("--status", choices=STATUSES)
    set_parser.add_argument("--completion", type=float)
    set_parser.set_defaults(handler=_handle_set)

    delete_parser = task_subparsers.add_parser(
        "delete",
        parents=[format_parent],
        help="Delete a roadmap item subtree by path.",
    )
    delete_parser.add_argument("file", type=Path)
    delete_parser.add_argument("path", help="1-based dotted item path.")
    delete_parser.set_defaults(handler=_handle_delete)

    move_parser = task_subparsers.add_parser(
        "move",
        parents=[format_parent],
        help="Move a roadmap item by path.",
    )
    move_parser.add_argument("file", type=Path)
    move_parser.add_argument("path", help="1-based dotted item path.")
    destination_group = move_parser.add_mutually_exclusive_group(required=True)
    destination_group.add_argument("--before", help="Move before this 1-based dotted item path.")
    destination_group.add_argument("--after", help="Move after this 1-based dotted item path.")
    destination_group.add_argument("--parent", help="Move under this 1-based dotted parent path.")
    destination_group.add_argument("--top-level", action="store_true", help="Move to the top level.")
    move_parser.set_defaults(handler=_handle_move)

    group_parser = task_subparsers.add_parser(
        "group",
        parents=[format_parent],
        help="Group sibling roadmap items by path.",
    )
    group_parser.add_argument("file", type=Path)
    group_parser.add_argument("paths", nargs="+", help="1-based dotted sibling item paths.")
    group_parser.add_argument("-d", "--description", default="New group")
    group_parser.set_defaults(handler=_handle_group)

    ungroup_parser = task_subparsers.add_parser(
        "ungroup",
        parents=[format_parent],
        help="Remove a TaskGroup wrapper and promote its children.",
    )
    ungroup_parser.add_argument("file", type=Path)
    ungroup_parser.add_argument("path", help="1-based dotted TaskGroup path.")
    ungroup_parser.set_defaults(handler=_handle_ungroup)

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

    try:
        tasks = document.roadmap.next(args.count)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(render_roadmap(Roadmap(tasks), document.format))
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


def _handle_set(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    try:
        changed = _set_item_from_args(document.roadmap, args)
        if changed:
            save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    message = "updated" if changed else "unchanged"
    print(f"{message} {document.format} roadmap: {args.file}")
    return 0


def _handle_delete(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    try:
        document.roadmap.delete_item(_parse_item_path(args.path))
        save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"deleted item from {document.format} roadmap: {args.file}")
    return 0


def _handle_move(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    try:
        _move_item_from_args(document.roadmap, args)
        save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"moved item in {document.format} roadmap: {args.file}")
    return 0


def _handle_group(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    try:
        _group_items_from_args(document.roadmap, args)
        save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"grouped items in {document.format} roadmap: {args.file}")
    return 0


def _handle_ungroup(args: argparse.Namespace) -> int:
    document = _load_cli_document(args.file, args.format)
    if document is None:
        return 1

    try:
        _ungroup_item(document.roadmap, _parse_item_path(args.path))
        save_document(document)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"ungrouped item in {document.format} roadmap: {args.file}")
    return 0


def _handle_editor(args: argparse.Namespace) -> int:
    try:
        document = load_document(args.file, args.format, default="text")
        from roadmaps.editor import run_editor

        return run_editor(document)
    except ModuleNotFoundError:
        print(
            "error: Textual is required for the editor; install roadmaps[editor]",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
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


def _set_item_from_args(roadmap: Roadmap, args: argparse.Namespace) -> bool:
    if not _has_set_options(args):
        msg = "set requires at least one field option"
        raise ValueError(msg)
    if args.urgent and args.priority is not None:
        msg = "--urgent cannot be combined with --priority"
        raise ValueError(msg)
    if args.optional and (args.urgent or args.priority not in {None, DEFAULT_PRIORITY}):
        msg = "optional tasks cannot also have a positive priority"
        raise ValueError(msg)

    item = _resolve_item_path(roadmap, args.path)
    before = roadmap.to_dict()

    if args.description is not None:
        description = args.description.strip()
        if not description:
            msg = "description must be a non-empty string"
            raise ValueError(msg)
        _validate_description(description, "description", ValueError)
        item.description = description
    if args.milestone is not None:
        if args.milestone < NO_MILESTONE:
            msg = "milestone must be a non-negative integer"
            raise ValueError(msg)
        item.milestone = args.milestone
    if args.optional:
        item.set_optional(True)
    if args.not_optional:
        item.set_optional(False)
    if args.urgent:
        item.set_optional(False)
        item.set_priority(MAX_PRIORITY)
    if args.priority is not None:
        item.set_optional(False)
        item.set_priority(args.priority)
    if args.status is not None:
        _set_item_status(item, args.status, args.completion)
    elif args.completion is not None:
        if isinstance(item, TaskGroup):
            msg = "completion editing is only available for leaf tasks"
            raise TypeError(msg)
        item.mark_ongoing(completion=args.completion)

    return roadmap.to_dict() != before


def _has_set_options(args: argparse.Namespace) -> bool:
    return any(
        (
            args.description is not None,
            args.priority is not None,
            args.urgent,
            args.optional,
            args.not_optional,
            args.milestone is not None,
            args.status is not None,
            args.completion is not None,
        )
    )


def _set_item_status(
    item: Task | TaskGroup,
    status: str,
    completion: float | None,
) -> None:
    if status != "ongoing" and completion is not None:
        msg = "--completion can only be used with --status ongoing"
        raise ValueError(msg)
    if status == "not-started":
        item.mark_not_started()
    elif status == "ongoing":
        item.mark_ongoing(completion=0.0 if completion is None else completion)
    else:
        item.mark_completed()


def _move_item_from_args(roadmap: Roadmap, args: argparse.Namespace) -> None:
    source_path = _parse_item_path(args.path)
    if args.before is not None:
        _move_item_before_or_after(roadmap, source_path, _parse_item_path(args.before), after=False)
    elif args.after is not None:
        _move_item_before_or_after(roadmap, source_path, _parse_item_path(args.after), after=True)
    elif args.parent is not None:
        _move_item_under_parent(roadmap, source_path, _parse_item_path(args.parent))
    elif args.top_level:
        item = _pop_item_at_path(roadmap, source_path)
        roadmap.steps.append(item)
        _renumber_cli_siblings(roadmap.steps)


def _move_item_before_or_after(
    roadmap: Roadmap,
    source_path: tuple[int, ...],
    target_path: tuple[int, ...],
    *,
    after: bool,
) -> None:
    _validate_move_paths(source_path, target_path)
    item = _pop_item_at_path(roadmap, source_path)
    target_path = _adjust_path_after_removal(target_path, source_path)
    target_siblings = _items_at_parent_path(roadmap, target_path[:-1])
    insert_index = target_path[-1] + (1 if after else 0)
    target_siblings.insert(insert_index, item)
    _renumber_cli_siblings(target_siblings)


def _move_item_under_parent(
    roadmap: Roadmap,
    source_path: tuple[int, ...],
    parent_path: tuple[int, ...],
) -> None:
    _validate_move_paths(source_path, parent_path)
    item = _pop_item_at_path(roadmap, source_path)
    parent_path = _adjust_path_after_removal(parent_path, source_path)
    parent = _item_at_path(roadmap, parent_path)
    if not isinstance(parent, TaskGroup):
        parent = roadmap.task_to_group(parent)
    parent.tasks.append(item)
    _renumber_cli_siblings(parent.tasks)


def _validate_move_paths(source_path: tuple[int, ...], target_path: tuple[int, ...]) -> None:
    if source_path == target_path:
        msg = "source and destination paths must differ"
        raise ValueError(msg)
    if _path_is_prefix(source_path, target_path):
        msg = "cannot move an item into itself or its descendants"
        raise ValueError(msg)


def _group_items_from_args(roadmap: Roadmap, args: argparse.Namespace) -> None:
    paths = [_parse_item_path(path) for path in args.paths]
    if len(paths) < 2:
        msg = "group requires at least two item paths"
        raise ValueError(msg)
    parent_paths = {path[:-1] for path in paths}
    if len(parent_paths) != 1:
        msg = "grouped items must share the same parent"
        raise ValueError(msg)
    parent_path = parent_paths.pop()
    indexes = [path[-1] for path in paths]
    if len(set(indexes)) != len(indexes):
        msg = "grouped item paths must be unique"
        raise ValueError(msg)

    siblings = _items_at_parent_path(roadmap, parent_path)
    for index in indexes:
        if index >= len(siblings):
            msg = "path index is out of range"
            raise ValueError(msg)
    insert_index = min(indexes)
    first_item = siblings[insert_index]
    group = TaskGroup(
        args.description,
        order=first_item.order,
        tasks=[siblings[index] for index in sorted(indexes)],
    )
    for index in sorted(indexes, reverse=True):
        siblings.pop(index)
    siblings.insert(insert_index, group)
    _renumber_cli_siblings(group.tasks)
    _renumber_cli_siblings(siblings)


def _ungroup_item(roadmap: Roadmap, path: tuple[int, ...]) -> None:
    siblings = _items_at_parent_path(roadmap, path[:-1])
    index = path[-1]
    if index >= len(siblings):
        msg = "path index is out of range"
        raise ValueError(msg)
    group = siblings[index]
    if not isinstance(group, TaskGroup):
        msg = "path must identify a task group"
        raise TypeError(msg)
    siblings[index : index + 1] = group.tasks
    _renumber_cli_siblings(siblings)


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


def _resolve_item_path(roadmap: Roadmap, path: str) -> Task | TaskGroup:
    return _item_at_path(roadmap, _parse_item_path(path))


def _parse_item_path(path: str) -> tuple[int, ...]:
    return tuple(index - 1 for index in _parse_parent_path(path))


def _item_at_path(roadmap: Roadmap, path: tuple[int, ...]) -> Task | TaskGroup:
    siblings = _items_at_parent_path(roadmap, path[:-1])
    index = path[-1]
    if index >= len(siblings):
        msg = "path index is out of range"
        raise ValueError(msg)
    return siblings[index]


def _items_at_parent_path(
    roadmap: Roadmap,
    path: tuple[int, ...],
) -> list[Task | TaskGroup]:
    items = roadmap.steps
    for index in path:
        if index >= len(items):
            msg = "path index is out of range"
            raise ValueError(msg)
        item = items[index]
        if not isinstance(item, TaskGroup):
            msg = "path descends through a leaf task"
            raise ValueError(msg)  # noqa: TRY004 - CLI path errors are reported as ValueError.
        items = item.tasks
    return items


def _pop_item_at_path(roadmap: Roadmap, path: tuple[int, ...]) -> Task | TaskGroup:
    siblings = _items_at_parent_path(roadmap, path[:-1])
    index = path[-1]
    if index >= len(siblings):
        msg = "path index is out of range"
        raise ValueError(msg)
    item = siblings.pop(index)
    _repair_empty_parent_after_pop(roadmap, path[:-1])
    return item


def _repair_empty_parent_after_pop(roadmap: Roadmap, parent_path: tuple[int, ...]) -> None:
    if not parent_path:
        _renumber_cli_siblings(roadmap.steps)
        return

    grandparent = _items_at_parent_path(roadmap, parent_path[:-1])
    parent_index = parent_path[-1]
    parent = grandparent[parent_index]
    if isinstance(parent, TaskGroup) and not parent.tasks:
        grandparent[parent_index] = parent.to_task()
        _repair_empty_parent_after_pop(roadmap, parent_path[:-1])
    else:
        _renumber_cli_siblings(parent.tasks if isinstance(parent, TaskGroup) else grandparent)
        _renumber_cli_siblings(grandparent)


def _adjust_path_after_removal(
    path: tuple[int, ...],
    removed_path: tuple[int, ...],
) -> tuple[int, ...]:
    if _path_is_prefix(removed_path, path):
        msg = "destination path cannot be inside the moved item"
        raise ValueError(msg)

    adjusted = list(path)
    for depth, removed_index in enumerate(removed_path):
        if depth >= len(adjusted) or tuple(adjusted[:depth]) != removed_path[:depth]:
            break
        if removed_index < adjusted[depth]:
            adjusted[depth] -= 1
            break
        if removed_index > adjusted[depth]:
            break
    return tuple(adjusted)


def _path_is_prefix(prefix: tuple[int, ...], path: tuple[int, ...]) -> bool:
    return len(prefix) <= len(path) and path[: len(prefix)] == prefix


def _renumber_cli_siblings(siblings: list[Task | TaskGroup]) -> None:
    order = 1
    for item in siblings:
        if item.order == UNSORTED:
            continue
        item.order = order
        order += 1


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
