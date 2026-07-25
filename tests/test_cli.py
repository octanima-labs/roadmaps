from pathlib import Path

from roadmaps import Roadmap
from roadmaps.cli import main


def test_validate_accepts_text_json_and_markdown_files(tmp_path: Path, capsys) -> None:
    roadmap = Roadmap.from_text("- [ ]^900 (1) first")
    text_path = tmp_path / "roadmap.roadmap"
    json_path = tmp_path / "roadmap.json"
    markdown_path = tmp_path / "roadmap.md"
    text_path.write_text(roadmap.to_text())
    json_path.write_text(roadmap.to_json())
    markdown_path.write_text("# Roadmap\n\n" + roadmap.to_markdown())

    assert main(["validate", str(text_path)]) == 0
    assert main(["validate", str(json_path)]) == 0
    assert main(["validate", str(markdown_path)]) == 0

    output = capsys.readouterr().out
    assert "valid text roadmap" in output
    assert "valid json roadmap" in output
    assert "valid markdown roadmap" in output


def test_next_outputs_source_text_format(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.txt"
    path.write_text(
        """
- [ ] low priority
- [ ]! high priority
- [x] done
""".strip()
    )

    assert main(["next", str(path)]) == 0

    assert capsys.readouterr().out == (
        "- [ ]! high priority\n"
        "- [ ] low priority\n"
    )


def test_next_outputs_source_markdown_format(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text("# Roadmap\n\n- [ ] (!) high priority\n- [x] done")

    assert main(["next", str(path)]) == 0

    assert capsys.readouterr().out == "- [ ] (!) high priority\n"


def test_render_converts_between_formats(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ]^900 (1) serialize")

    assert main(["render", str(path), "--to", "markdown"]) == 0

    assert capsys.readouterr().out == "- [ ] (900:1) serialize\n"


def test_stats_outputs_completion_and_counts(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(
        """
- [x] (1) done
- [ ] (2) pending
- [ ]? optional
""".strip()
    )

    assert main(["stats", str(path)]) == 0

    assert capsys.readouterr().out == (
        "completion: 50%\n"
        "tasks: 3\n"
        "completed: 1\n"
        "incomplete: 2\n"
        "milestones: 2\n"
    )


def test_stats_outputs_partial_ongoing_completion(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [~50.5%] partial")

    assert main(["stats", str(path)]) == 0

    assert capsys.readouterr().out == (
        "completion: 50.5%\n"
        "tasks: 1\n"
        "completed: 0\n"
        "incomplete: 1\n"
        "milestones: 0\n"
    )


def test_format_override_allows_unknown_extension(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.data"
    path.write_text("- [ ] task")

    assert main(["validate", "--format", "text", str(path)]) == 0

    assert "valid text roadmap" in capsys.readouterr().out


def test_unknown_extension_without_format_fails(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.data"
    path.write_text("- [ ] task")

    assert main(["validate", str(path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot infer format" in captured.err


def test_invalid_roadmap_returns_nonzero(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(" - [ ] invalid indentation")

    assert main(["validate", str(path)]) == 1

    assert "indentation" in capsys.readouterr().err
