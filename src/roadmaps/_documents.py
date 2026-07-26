from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from roadmaps.model import Roadmap

Format = str

TEXT_EXTENSIONS = {".roadmap", ".txt"}
JSON_EXTENSIONS = {".json"}
YAML_EXTENSIONS = {".yaml", ".yml"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
FORMATS = ("text", "json", "yaml", "markdown")
NEW_MARKDOWN_HEADING_LEVEL = 2

_MARKDOWN_HEADING_REGEX = re.compile(r"^(?P<marker>#{1,6})\s+(?P<title>.*?)\s*#*\s*$")


@dataclass
class Document:
    roadmap: Roadmap
    format: Format
    path: Path | None = None
    exists: bool = False
    markdown_heading_level: int | None = None


def detect_format(
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
    if suffix in YAML_EXTENSIONS:
        return "yaml"
    if suffix in MARKDOWN_EXTENSIONS:
        return "markdown"
    if default is not None:
        return default

    msg = f"cannot infer format from extension '{suffix or '<none>'}'; use --format"
    raise ValueError(msg)


def load_document(
    path: Path | None,
    format_override: Format | None = None,
    default: Format | None = None,
) -> Document:
    if path is None:
        return new_document(format_override=format_override, default=default or "text")

    if not path.exists():
        if default is None:
            raise FileNotFoundError(2, "No such file or directory", path)
        return new_document(path, format_override, default=default)

    source_format = detect_format(path, format_override)
    source = path.read_text()
    return Document(
        parse_roadmap(source, source_format),
        source_format,
        path=path,
        exists=True,
        markdown_heading_level=_markdown_heading_level(source)
        if source_format == "markdown"
        else None,
    )


def new_document(
    path: Path | None = None,
    format_override: Format | None = None,
    default: Format = "text",
    roadmap: Roadmap | None = None,
) -> Document:
    document_format = detect_format(path, format_override, default) if path is not None else format_override or default
    return Document(
        Roadmap() if roadmap is None else roadmap,
        document_format,
        path=path,
        exists=False,
        markdown_heading_level=NEW_MARKDOWN_HEADING_LEVEL
        if document_format == "markdown"
        else None,
    )


def save_document(document: Document, path: Path | None = None) -> None:
    target = document.path if path is None else path
    if target is None:
        msg = "cannot save unnamed roadmap without a path"
        raise ValueError(msg)

    target.write_text(render_document(document))
    document.path = target
    document.exists = True


def parse_roadmap(source: str, source_format: Format) -> Roadmap:
    if source_format == "text":
        return Roadmap.from_text(source)
    if source_format == "json":
        return Roadmap.from_json(source)
    if source_format == "yaml":
        return Roadmap.from_yaml(source)
    if source_format == "markdown":
        return Roadmap.from_markdown(source)

    msg = f"unsupported format: {source_format}"
    raise ValueError(msg)


def render_roadmap(
    roadmap: Roadmap,
    output_format: Format,
    markdown_heading_level: int | None = None,
) -> str:
    if output_format == "text":
        return roadmap.to_text()
    if output_format == "json":
        return roadmap.to_json()
    if output_format == "yaml":
        return roadmap.to_yaml()
    if output_format == "markdown":
        body = roadmap.to_markdown()
        if markdown_heading_level is None:
            return body
        heading = f"{'#' * markdown_heading_level} Roadmap"
        return f"{heading}\n\n" if not body else f"{heading}\n\n{body}"

    msg = f"unsupported format: {output_format}"
    raise ValueError(msg)


def render_document(document: Document) -> str:
    return render_roadmap(
        document.roadmap,
        document.format,
        markdown_heading_level=document.markdown_heading_level,
    )


def _markdown_heading_level(source: str) -> int | None:
    headings: list[tuple[int, int]] = []
    for index, line in enumerate(source.splitlines()):
        match = _MARKDOWN_HEADING_REGEX.match(line)
        if match is None:
            continue
        title = match.group("title").strip()
        if title.casefold() == "roadmap":
            headings.append((len(match.group("marker")), index))

    if not headings:
        return None
    return min(headings, key=lambda heading: (heading[0], heading[1]))[0]
