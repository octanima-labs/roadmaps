from pathlib import Path

from roadmaps import ONGOING, Roadmap, Task
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


def test_init_creates_text_json_and_markdown_files(tmp_path: Path, capsys) -> None:
    text_path = tmp_path / "roadmap.roadmap"
    json_path = tmp_path / "roadmap.json"
    markdown_path = tmp_path / "roadmap.md"

    assert main(["init", str(text_path)]) == 0
    assert main(["init", str(json_path)]) == 0
    assert main(["init", str(markdown_path)]) == 0

    assert text_path.read_text() == ""
    assert Roadmap.from_json(json_path.read_text()) == Roadmap()
    assert markdown_path.read_text() == "# Roadmap\n\n"
    assert "created text roadmap" in capsys.readouterr().out


def test_init_defaults_unknown_extension_to_text(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.data"

    assert main(["init", str(path)]) == 0

    assert path.read_text() == ""
    assert "created text roadmap" in capsys.readouterr().out


def test_init_supports_format_override(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.data"

    assert main(["init", "--format", "json", str(path)]) == 0

    assert Roadmap.from_json(path.read_text()) == Roadmap()


def test_init_refuses_to_overwrite_existing_file(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("existing")

    assert main(["init", str(path)]) == 1

    assert path.read_text() == "existing"
    assert "already exists" in capsys.readouterr().err


def test_add_task_appends_top_level_text_task(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] existing")

    assert (
        main(
            [
                "add-task",
                str(path),
                "new task",
                "--order",
                "1",
                "--urgent",
                "--milestone",
                "2",
            ]
        )
        == 0
    )

    assert path.read_text() == "- [ ] existing\n1. [ ]! (2) new task"
    assert "added task" in capsys.readouterr().out


def test_add_task_preserves_json_format(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(Roadmap().to_json())

    assert (
        main(
            [
                "add-task",
                str(path),
                "partial",
                "--status",
                "ongoing",
                "--completion",
                "50.0",
            ]
        )
        == 0
    )

    assert Roadmap.from_json(path.read_text()) == Roadmap(
        [Task("partial", status=ONGOING, completion=50.0)]
    )


def test_add_task_preserves_markdown_format(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text("# Roadmap\n\n")

    assert main(["add-task", str(path), "docs: publish **examples**"]) == 0

    assert path.read_text() == "- [ ] docs: publish **examples**"


def test_add_task_rejects_invalid_metadata(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("")

    assert main(["add-task", str(path), "invalid", "--optional", "--priority", "1"]) == 1

    assert path.read_text() == ""
    assert "optional tasks" in capsys.readouterr().err


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
