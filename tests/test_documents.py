from pathlib import Path

import pytest

from roadmaps import Roadmap, Task
from roadmaps._documents import (
    Document,
    detect_format,
    load_document,
    new_document,
    render_document,
    render_roadmap,
    save_document,
)


def test_detect_format_supports_known_extensions_and_overrides() -> None:
    assert detect_format(Path("roadmap.roadmap"), None) == "text"
    assert detect_format(Path("roadmap.txt"), None) == "text"
    assert detect_format(Path("roadmap.json"), None) == "json"
    assert detect_format(Path("roadmap.yaml"), None) == "yaml"
    assert detect_format(Path("roadmap.yml"), None) == "yaml"
    assert detect_format(Path("roadmap.md"), None) == "markdown"
    assert detect_format(Path("roadmap.markdown"), None) == "markdown"
    assert detect_format(Path("roadmap.data"), "json") == "json"


def test_detect_format_defaults_or_rejects_unknown_extensions() -> None:
    assert detect_format(Path("roadmap.data"), None, default="text") == "text"

    with pytest.raises(ValueError, match="cannot infer format"):
        detect_format(Path("roadmap.data"), None)


def test_load_document_reads_existing_file_with_metadata(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] task")

    document = load_document(path)

    assert document == Document(
        Roadmap([Task("task")]),
        "text",
        path=path,
        exists=True,
    )


def test_load_document_can_initialize_missing_path_with_default(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.data"

    document = load_document(path, default="text")

    assert document.roadmap == Roadmap()
    assert document.format == "text"
    assert document.path == path
    assert document.exists is False
    assert not path.exists()


def test_load_document_rejects_missing_path_without_default(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        load_document(tmp_path / "missing.roadmap")


def test_new_document_supports_unnamed_format_override() -> None:
    document = new_document(format_override="yaml")

    assert document.roadmap == Roadmap()
    assert document.format == "yaml"
    assert document.path is None
    assert document.exists is False


def test_save_document_writes_canonical_format_without_creating_parents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "roadmap.roadmap"
    document = new_document(path, roadmap=Roadmap([Task("task")]))

    with pytest.raises(OSError):
        save_document(document)


def test_markdown_document_preserves_loaded_roadmap_heading_wrapper(
    tmp_path: Path,
) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text(
        """
# Notes

ignored

## Roadmap

- [ ] task

## Other

- [ ] ignored
""".strip()
    )

    document = load_document(path)

    assert document.roadmap == Roadmap([Task("task")])
    assert document.markdown_heading_level == 2
    assert render_document(document) == "## Roadmap\n\n- [ ] task"


def test_new_markdown_document_uses_heading_two_wrapper() -> None:
    document = new_document(Path("roadmap.md"), roadmap=Roadmap([Task("task")]))

    assert render_document(document) == "## Roadmap\n\n- [ ] task"


def test_bare_markdown_rendering_stays_available_for_format_conversion() -> None:
    roadmap = Roadmap([Task("task")])

    assert render_roadmap(roadmap, "markdown") == "- [ ] task"
