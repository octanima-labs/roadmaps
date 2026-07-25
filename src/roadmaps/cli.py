from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from roadmaps.core import COMPLETED, MAX_PRIORITY, ONGOING, UNSORTED, Roadmap, Task

Format = str

TEXT_EXTENSIONS = {".roadmap", ".txt"}
JSON_EXTENSIONS = {".json"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
FORMATS = ("text", "json", "markdown")
STATUSES = ("not-started", "ongoing", "completed")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roadmaps",
        description="Inspect roadmap files without modifying them.",
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

    init_parser = subparsers.add_parser(
        "init",
        parents=[format_parent],
        help="Create a new empty roadmap file.",
    )
    init_parser.add_argument("file", type=Path)
    init_parser.set_defaults(handler=_handle_init)

    add_task_parser = subparsers.add_parser(
        "add-task",
        parents=[format_parent],
        help="Append a top-level task to a roadmap file.",
    )
    add_task_parser.add_argument("file", type=Path)
    add_task_parser.add_argument("description")
    add_task_parser.add_argument("--order", type=int, default=UNSORTED)
    add_task_parser.add_argument("--priority", type=int, default=0)
    add_task_parser.add_argument("--urgent", action="store_true")
    add_task_parser.add_argument("--optional", action="store_true")
    add_task_parser.add_argument("--milestone", type=int, default=0)
    add_task_parser.add_argument("--status", choices=STATUSES, default="not-started")
    add_task_parser.add_argument("--completion", type=float, default=0.0)
    add_task_parser.set_defaults(handler=_handle_add_task)

    return parser


def _handle_validate(args: argparse.Namespace) -> int:
    loaded = _load_roadmap(args.file, args.format)
    if loaded is None:
        return 1

    _roadmap, source_format = loaded
    print(f"valid {source_format} roadmap: {args.file}")
    return 0


def _handle_next(args: argparse.Namespace) -> int:
    loaded = _load_roadmap(args.file, args.format)
    if loaded is None:
        return 1

    roadmap, source_format = loaded
    print(_render_roadmap(Roadmap(roadmap.next_step()), source_format))
    return 0


def _handle_stats(args: argparse.Namespace) -> int:
    loaded = _load_roadmap(args.file, args.format)
    if loaded is None:
        return 1

    roadmap, _source_format = loaded
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
    loaded = _load_roadmap(args.file, args.format)
    if loaded is None:
        return 1

    roadmap, _source_format = loaded
    print(_render_roadmap(roadmap, args.to))
    return 0


def _handle_init(args: argparse.Namespace) -> int:
    if args.file.exists():
        print(f"error: file already exists: {args.file}", file=sys.stderr)
        return 1

    try:
        output_format = _detect_format(args.file, args.format, default="text")
        args.file.write_text(_render_initial_roadmap(output_format))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"created {output_format} roadmap: {args.file}")
    return 0


def _handle_add_task(args: argparse.Namespace) -> int:
    loaded = _load_roadmap(args.file, args.format)
    if loaded is None:
        return 1

    roadmap, source_format = loaded
    try:
        roadmap.add_step(_task_from_args(args))
        args.file.write_text(_render_roadmap(roadmap, source_format))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"added task to {source_format} roadmap: {args.file}")
    return 0


def _load_roadmap(
    path: Path,
    format_override: Format | None,
    stderr: TextIO | None = None,
) -> tuple[Roadmap, Format] | None:
    stderr = sys.stderr if stderr is None else stderr
    try:
        source_format = _detect_format(path, format_override)
        source = path.read_text()
        return _parse_roadmap(source, source_format), source_format
    except OSError as exc:
        print(f"error: {exc}", file=stderr)
        return None
    except ValueError as exc:
        print(f"error: {exc}", file=stderr)
        return None


def _detect_format(
    path: Path,
    format_override: Format | None,
    default: Format | None = None,
) -> Format:
    if format_override is not None:
        return format_override

    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return "text"
    if suffix in JSON_EXTENSIONS:
        return "json"
    if suffix in MARKDOWN_EXTENSIONS:
        return "markdown"
    if default is not None:
        return default

    msg = f"cannot infer format from extension '{suffix or '<none>'}'; use --format"
    raise ValueError(msg)


def _parse_roadmap(source: str, source_format: Format) -> Roadmap:
    if source_format == "text":
        return Roadmap.from_text(source)
    if source_format == "json":
        return Roadmap.from_json(source)
    if source_format == "markdown":
        return Roadmap.from_markdown(source)

    msg = f"unsupported format: {source_format}"
    raise ValueError(msg)


def _render_roadmap(roadmap: Roadmap, output_format: Format) -> str:
    if output_format == "text":
        return roadmap.to_text()
    if output_format == "json":
        return roadmap.to_json()
    if output_format == "markdown":
        return roadmap.to_markdown()

    msg = f"unsupported format: {output_format}"
    raise ValueError(msg)


def _render_initial_roadmap(output_format: Format) -> str:
    if output_format == "markdown":
        return "# Roadmap\n\n"
    return _render_roadmap(Roadmap(), output_format)


def _task_from_args(args: argparse.Namespace) -> Task:
    if args.urgent and args.priority:
        msg = "--urgent cannot be combined with --priority"
        raise ValueError(msg)
    priority = MAX_PRIORITY if args.urgent else args.priority
    status = _status_from_name(args.status)
    return Task(
        args.description,
        order=args.order,
        priority=priority,
        status=status,
        optional=args.optional,
        milestone=args.milestone,
        completion=args.completion,
    )


def _status_from_name(name: str) -> int:
    if name == "not-started":
        return 0
    if name == "ongoing":
        return ONGOING
    return COMPLETED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
