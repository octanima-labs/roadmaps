from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from roadmaps.core import COMPLETED, Roadmap

Format = str

TEXT_EXTENSIONS = {".roadmap", ".txt"}
JSON_EXTENSIONS = {".json"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
FORMATS = ("text", "json", "markdown")


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


def _detect_format(path: Path, format_override: Format | None) -> Format:
    if format_override is not None:
        return format_override

    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return "text"
    if suffix in JSON_EXTENSIONS:
        return "json"
    if suffix in MARKDOWN_EXTENSIONS:
        return "markdown"

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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
