from pathlib import Path

import pytest

from roadmaps import COMPLETED, ONGOING, Roadmap, Task
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


def test_show_outputs_matching_items_in_source_format(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(
        """
- [ ] docs: parent
  - [ ] docs: child
- [ ] core: sibling
""".strip()
    )

    assert main(["show", str(path), "-c", "docs"]) == 0

    assert capsys.readouterr().out == (
        "- [ ] docs: parent\n"
        "- [ ] docs: child\n"
    )


def test_show_supports_output_format_override(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] docs: task")

    assert main(["show", str(path), "-c", "docs", "--to", "markdown"]) == 0

    assert capsys.readouterr().out == "- [ ] docs: task\n"


def test_show_status_filters_and_optional_union(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(
        """
- [x] done
- [~] ongoing
- [ ] pending
- [ ]? optional
""".strip()
    )

    assert main(["show", str(path), "--completed", "--ongoing", "--optional"]) == 0

    assert capsys.readouterr().out == (
        "- [x] done\n"
        "- [~] ongoing\n"
        "- [ ]? optional\n"
    )


def test_show_uncompleted_excludes_completed_and_optional_by_default(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [x] done\n- [~] ongoing\n- [ ] pending\n- [ ]? optional")

    assert main(["show", str(path), "--uncompleted"]) == 0

    assert capsys.readouterr().out == (
        "- [~] ongoing\n"
        "- [ ] pending\n"
    )


def test_show_all_ignores_filters(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ]? optional\n- [ ] uncategorized")

    assert main(["show", str(path), "--all", "-c", "missing"]) == 0

    assert capsys.readouterr().out == (
        "- [ ]? optional\n"
        "- [ ] uncategorized\n"
    )


def test_show_no_matches_returns_success_message(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] docs: task")

    assert main(["show", str(path), "-c", "missing"]) == 0

    assert capsys.readouterr().out == "no matching tasks\n"


def test_show_supports_json_input_and_output(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(Roadmap.from_text("- [ ] docs: task\n- [ ] core: hidden").to_json())

    assert main(["show", str(path), "-c", "docs"]) == 0

    output = capsys.readouterr().out
    assert Roadmap.from_json(output) == Roadmap([Task("docs: task")])


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


def test_init_example_creates_feature_rich_roadmap(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"

    assert main(["init", "--example", str(path)]) == 0

    roadmap = Roadmap.from_text(path.read_text())
    tasks = roadmap.leaf_tasks()

    assert len(tasks) == 4
    assert any(task.priority == 999 for task in tasks)
    assert any(task.optional for task in tasks)
    assert any(task.completion == 50.0 for task in tasks)


def test_init_example_supports_json_and_markdown(tmp_path: Path) -> None:
    json_path = tmp_path / "roadmap.json"
    markdown_path = tmp_path / "roadmap.md"

    assert main(["init", "--example", str(json_path)]) == 0
    assert main(["init", "--example", str(markdown_path)]) == 0

    assert Roadmap.from_json(json_path.read_text()).leaf_tasks()
    assert Roadmap.from_markdown(markdown_path.read_text()).leaf_tasks()


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
                "-d",
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
                "-d",
                "partial",
                "--status",
                "ongoing",
                "--completion",
                "50.0",
            ]
        )
        == 0
    )

    task = Roadmap.from_json(path.read_text()).steps[0]

    assert isinstance(task, Task)
    assert task.description == "partial"
    assert task.status == ONGOING
    assert task.completion == 50.0
    assert task.start_date is not None
    assert task.completion_date is None


def test_add_task_completed_sets_json_dates(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(Roadmap().to_json())

    assert main(["add-task", str(path), "-d", "done", "--status", "completed"]) == 0

    task = Roadmap.from_json(path.read_text()).steps[0]

    assert isinstance(task, Task)
    assert task.status == COMPLETED
    assert task.start_date is not None
    assert task.completion_date is not None


def test_add_task_preserves_markdown_format(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text("# Roadmap\n\n")

    assert main(["add-task", str(path), "-d", "docs: publish **examples**"]) == 0

    assert path.read_text() == "- [ ] docs: publish **examples**"


def test_add_task_requires_description_option(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("")

    with pytest.raises(SystemExit):
        main(["add-task", str(path), "missing option"])


def test_add_task_rejects_invalid_metadata(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("")

    assert (
        main(["add-task", str(path), "-d", "invalid", "--optional", "--priority", "1"])
        == 1
    )

    assert path.read_text() == ""
    assert "optional tasks" in capsys.readouterr().err


def test_add_task_parent_appends_under_group_with_auto_order_and_milestone(
    tmp_path: Path,
) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(
        """
- [ ] (2) parent
  1. [ ] existing child
  - [ ] loose child
""".strip()
    )

    assert main(["add-task", str(path), "--parent", "1", "-d", "new child"]) == 0

    assert path.read_text() == (
        "- [ ] (2) parent\n"
        "  1. [ ] (2) existing child\n"
        "  - [ ] (2) loose child\n"
        "  2. [ ] (2) new child"
    )


def test_add_task_parent_converts_leaf_to_group(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] (3) parent")

    assert main(["add-task", str(path), "--parent", "1", "-d", "child"]) == 0

    assert path.read_text() == (
        "- [ ] (3) parent\n"
        "  1. [ ] (3) child"
    )


def test_add_task_parent_supports_nested_path(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(
        """
- [ ] root
  - [ ] branch
""".strip()
    )

    assert main(["add-task", str(path), "--parent", "1.1", "-d", "leaf"]) == 0

    assert path.read_text() == (
        "- [ ] root\n"
        "  - [ ] branch\n"
        "    1. [ ] leaf"
    )


def test_add_task_parent_supports_json_and_markdown(tmp_path: Path) -> None:
    roadmap = Roadmap.from_text("- [ ] parent")
    json_path = tmp_path / "roadmap.json"
    markdown_path = tmp_path / "roadmap.md"
    json_path.write_text(roadmap.to_json())
    markdown_path.write_text("# Roadmap\n\n" + roadmap.to_markdown())

    assert main(["add-task", str(json_path), "--parent", "1", "-d", "json child"]) == 0
    assert main(["add-task", str(markdown_path), "--parent", "1", "-d", "md child"]) == 0

    assert Roadmap.from_json(json_path.read_text()) == Roadmap.from_text(
        "- [ ] parent\n  1. [ ] json child"
    )
    assert Roadmap.from_markdown(markdown_path.read_text()) == Roadmap.from_text(
        "- [ ] parent\n  1. [ ] md child"
    )


def test_add_task_parent_rejects_invalid_paths_and_order(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent")

    assert main(["add-task", str(path), "--parent", "0", "-d", "child"]) == 1
    assert "positive" in capsys.readouterr().err

    assert main(["add-task", str(path), "--parent", "2", "-d", "child"]) == 1
    assert "out of range" in capsys.readouterr().err

    assert (
        main(["add-task", str(path), "--parent", "1", "--order", "1", "-d", "child"])
        == 1
    )
    assert "--order" in capsys.readouterr().err


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
