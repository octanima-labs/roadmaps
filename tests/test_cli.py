import tomllib
from pathlib import Path

import pytest

from roadmaps import COMPLETED, ONGOING, Roadmap, Task
from roadmaps._documents import Document
from roadmaps.cli import main


def test_cli_help_uses_singular_program_name(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.startswith("usage: roadmap ")


@pytest.mark.parametrize(
    "command",
    ["render", "show", "add-task", "set", "delete", "move", "group", "ungroup"],
)
def test_old_top_level_command_names_are_removed(command: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([command, "roadmap.roadmap"])

    assert exc_info.value.code == 2


def test_pyproject_exposes_singular_console_script() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text())

    assert metadata["project"]["scripts"] == {
        "roadmap": "roadmaps.cli:main",
    }


def test_validate_accepts_text_json_yaml_and_markdown_files(
    tmp_path: Path,
    capsys,
) -> None:
    roadmap = Roadmap.from_text("- [ ]^900 (1) first")
    text_path = tmp_path / "roadmap.roadmap"
    json_path = tmp_path / "roadmap.json"
    yaml_path = tmp_path / "roadmap.yaml"
    markdown_path = tmp_path / "roadmap.md"
    text_path.write_text(roadmap.to_text())
    json_path.write_text(roadmap.to_json())
    yaml_path.write_text(roadmap.to_yaml())
    markdown_path.write_text("# Roadmap\n\n" + roadmap.to_markdown())

    assert main(["validate", str(text_path)]) == 0
    assert main(["validate", str(json_path)]) == 0
    assert main(["validate", str(yaml_path)]) == 0
    assert main(["validate", str(markdown_path)]) == 0

    output = capsys.readouterr().out
    assert "valid text roadmap" in output
    assert "valid json roadmap" in output
    assert "valid yaml roadmap" in output
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
    )


def test_next_count_outputs_multiple_tasks(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.txt"
    path.write_text(
        """
- [ ] low priority
- [ ]! high priority
- [x] done
""".strip()
    )

    assert main(["next", str(path), "--count", "2"]) == 0

    assert capsys.readouterr().out == (
        "- [ ]! high priority\n"
        "- [ ] low priority\n"
    )


def test_next_rejects_invalid_count(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.txt"
    path.write_text("- [ ] task")

    assert main(["next", str(path), "--count", "0"]) == 1

    assert "count" in capsys.readouterr().err


def test_next_outputs_source_markdown_format(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text("# Roadmap\n\n- [ ] (!) high priority\n- [x] done")

    assert main(["next", str(path)]) == 0

    assert capsys.readouterr().out == "- [ ] (!) high priority\n"


def test_render_converts_between_formats(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ]^900 (1) serialize")

    assert main(["export", str(path), "--to", "markdown"]) == 0

    assert capsys.readouterr().out == "- [ ] (900:1) serialize\n"


def test_render_supports_yaml_output(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    roadmap = Roadmap.from_text("- [ ]^900 (1) serialize")
    path.write_text(roadmap.to_text())

    assert main(["export", str(path), "--to", "yaml"]) == 0

    assert Roadmap.from_yaml(capsys.readouterr().out) == roadmap


def test_show_outputs_matching_items_in_source_format(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(
        """
- [ ] docs: parent
  - [ ] docs: child
- [ ] core: sibling
""".strip()
    )

    assert main(["search", str(path), "-c", "docs"]) == 0

    assert capsys.readouterr().out == (
        "- [ ] docs: parent\n"
        "- [ ] docs: child\n"
    )


def test_show_supports_output_format_override(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] docs: task")

    assert main(["search", str(path), "-c", "docs", "--to", "markdown"]) == 0

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

    assert main(["search", str(path), "--completed", "--ongoing", "--optional"]) == 0

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

    assert main(["search", str(path), "--uncompleted"]) == 0

    assert capsys.readouterr().out == (
        "- [~] ongoing\n"
        "- [ ] pending\n"
    )


def test_show_all_ignores_filters(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ]? optional\n- [ ] uncategorized")

    assert main(["search", str(path), "--all", "-c", "missing"]) == 0

    assert capsys.readouterr().out == (
        "- [ ]? optional\n"
        "- [ ] uncategorized\n"
    )


def test_show_no_matches_returns_success_message(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] docs: task")

    assert main(["search", str(path), "-c", "missing"]) == 0

    assert capsys.readouterr().out == "no matching tasks\n"


def test_show_supports_json_input_and_output(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(Roadmap.from_text("- [ ] docs: task\n- [ ] core: hidden").to_json())

    assert main(["search", str(path), "-c", "docs"]) == 0

    output = capsys.readouterr().out
    assert Roadmap.from_json(output) == Roadmap([Task("docs: task")])


def test_show_supports_yaml_input_and_output(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.yml"
    path.write_text(Roadmap.from_text("- [ ] docs: task\n- [ ] core: hidden").to_yaml())

    assert main(["search", str(path), "-c", "docs"]) == 0

    output = capsys.readouterr().out
    assert Roadmap.from_yaml(output) == Roadmap([Task("docs: task")])


def test_init_creates_text_json_yaml_and_markdown_files(tmp_path: Path, capsys) -> None:
    text_path = tmp_path / "roadmap.roadmap"
    json_path = tmp_path / "roadmap.json"
    yaml_path = tmp_path / "roadmap.yaml"
    markdown_path = tmp_path / "roadmap.md"

    assert main(["init", str(text_path)]) == 0
    assert main(["init", str(json_path)]) == 0
    assert main(["init", str(yaml_path)]) == 0
    assert main(["init", str(markdown_path)]) == 0

    assert text_path.read_text() == ""
    assert Roadmap.from_json(json_path.read_text()) == Roadmap()
    assert Roadmap.from_yaml(yaml_path.read_text()) == Roadmap()
    assert markdown_path.read_text() == "## Roadmap\n\n"
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


def test_init_supports_yaml_format_override(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.data"

    assert main(["init", "--format", "yaml", str(path)]) == 0

    assert Roadmap.from_yaml(path.read_text()) == Roadmap()


def test_init_example_creates_feature_rich_roadmap(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"

    assert main(["init", "--example", str(path)]) == 0

    roadmap = Roadmap.from_text(path.read_text())
    tasks = roadmap.leaf_tasks()

    assert len(tasks) == 4
    assert any(task.priority == 999 for task in tasks)
    assert any(task.optional for task in tasks)
    assert any(task.completion == 50.0 for task in tasks)


def test_init_example_supports_json_yaml_and_markdown(tmp_path: Path) -> None:
    json_path = tmp_path / "roadmap.json"
    yaml_path = tmp_path / "roadmap.yaml"
    markdown_path = tmp_path / "roadmap.md"

    assert main(["init", "--example", str(json_path)]) == 0
    assert main(["init", "--example", str(yaml_path)]) == 0
    assert main(["init", "--example", str(markdown_path)]) == 0

    assert Roadmap.from_json(json_path.read_text()).leaf_tasks()
    assert Roadmap.from_yaml(yaml_path.read_text()).leaf_tasks()
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
                "task",
                "add",
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
                "task",
                "add",
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


def test_add_task_preserves_yaml_format(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.yaml"
    path.write_text(Roadmap().to_yaml())

    assert (
        main(
            [
                "task",
                "add",
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

    task = Roadmap.from_yaml(path.read_text()).steps[0]

    assert isinstance(task, Task)
    assert task.description == "partial"
    assert task.status == ONGOING
    assert task.completion == 50.0
    assert task.start_date is not None
    assert task.completion_date is None


def test_add_task_completed_sets_json_dates(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(Roadmap().to_json())

    assert main(["task", "add", str(path), "-d", "done", "--status", "completed"]) == 0

    task = Roadmap.from_json(path.read_text()).steps[0]

    assert isinstance(task, Task)
    assert task.status == COMPLETED
    assert task.start_date is not None
    assert task.completion_date is not None


def test_add_task_preserves_markdown_format(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text("# Roadmap\n\n")

    assert main(["task", "add", str(path), "-d", "docs: publish **examples**"]) == 0

    assert path.read_text() == "# Roadmap\n\n- [ ] docs: publish **examples**"


def test_add_task_requires_description_option(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("")

    with pytest.raises(SystemExit):
        main(["task", "add", str(path), "missing option"])


def test_add_task_rejects_invalid_metadata(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("")

    assert (
        main(["task", "add", str(path), "-d", "invalid", "--optional", "--priority", "1"])
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

    assert main(["task", "add", str(path), "--parent", "1", "-d", "new child"]) == 0

    assert path.read_text() == (
        "- [ ] (2) parent\n"
        "  1. [ ] (2) existing child\n"
        "  - [ ] (2) loose child\n"
        "  2. [ ] (2) new child"
    )


def test_add_task_parent_converts_leaf_to_group(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] (3) parent")

    assert main(["task", "add", str(path), "--parent", "1", "-d", "child"]) == 0

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

    assert main(["task", "add", str(path), "--parent", "1.1", "-d", "leaf"]) == 0

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

    assert main(["task", "add", str(json_path), "--parent", "1", "-d", "json child"]) == 0
    assert main(["task", "add", str(markdown_path), "--parent", "1", "-d", "md child"]) == 0

    assert Roadmap.from_json(json_path.read_text()) == Roadmap.from_text(
        "- [ ] parent\n  1. [ ] json child"
    )
    assert Roadmap.from_markdown(markdown_path.read_text()) == Roadmap.from_text(
        "- [ ] parent\n  1. [ ] md child"
    )


def test_add_task_parent_rejects_invalid_paths_and_order(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent")

    assert main(["task", "add", str(path), "--parent", "0", "-d", "child"]) == 1
    assert "positive" in capsys.readouterr().err

    assert main(["task", "add", str(path), "--parent", "2", "-d", "child"]) == 1
    assert "out of range" in capsys.readouterr().err

    assert (
        main(["task", "add", str(path), "--parent", "1", "--order", "1", "-d", "child"])
        == 1
    )
    assert "--order" in capsys.readouterr().err


def test_set_updates_existing_item_metadata_and_status(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(Roadmap.from_text("- [ ] old").to_json())

    assert (
        main(
            [
                "task",
                "set",
                str(path),
                "1",
                "--description",
                "new",
                "--priority",
                "5",
                "--milestone",
                "2",
                "--status",
                "ongoing",
                "--completion",
                "25",
            ]
        )
        == 0
    )

    task = Roadmap.from_json(path.read_text()).steps[0]
    assert isinstance(task, Task)
    assert task.description == "new"
    assert task.priority == 5
    assert task.milestone == 2
    assert task.status == ONGOING
    assert task.completion == 25.0
    assert task.start_date is not None
    assert "updated json roadmap" in capsys.readouterr().out


def test_set_marks_completed_and_preserves_markdown_heading(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.md"
    path.write_text("# Notes\n\n## Roadmap\n\n- [ ] task\n")

    assert main(["task", "set", str(path), "1", "--status", "completed"]) == 0

    assert path.read_text() == "## Roadmap\n\n- [x] task"


def test_set_rejects_missing_fields_and_invalid_completion(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] task")

    assert main(["task", "set", str(path), "1"]) == 1
    assert "requires" in capsys.readouterr().err

    assert main(["task", "set", str(path), "1", "--status", "completed", "--completion", "50"]) == 1
    assert "--completion" in capsys.readouterr().err

    assert main(["task", "set", str(path), "1", "--optional", "--priority", "1"]) == 1
    assert "optional tasks" in capsys.readouterr().err


def test_delete_removes_item_subtree(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent\n  - [ ] child\n- [ ] sibling")

    assert main(["task", "delete", str(path), "1"]) == 0

    assert path.read_text() == "- [ ] sibling"
    assert "deleted item" in capsys.readouterr().out


def test_delete_rejects_invalid_path(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] task")

    assert main(["task", "delete", str(path), "2"]) == 1

    assert "out of range" in capsys.readouterr().err


def test_move_reorders_items_before_and_after(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("1. [ ] first\n2. [ ] second\n3. [ ] third")

    assert main(["task", "move", str(path), "3", "--before", "1"]) == 0
    assert path.read_text() == "1. [ ] third\n2. [ ] first\n3. [ ] second"

    assert main(["task", "move", str(path), "1", "--after", "3"]) == 0
    assert path.read_text() == "1. [ ] first\n2. [ ] second\n3. [ ] third"


def test_move_reparents_item_and_converts_leaf_parent(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent\n- [ ] child")

    assert main(["task", "move", str(path), "2", "--parent", "1"]) == 0

    assert path.read_text() == "- [ ] parent\n  - [ ] child"


def test_move_top_level_promotes_nested_item(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent\n  - [ ] child\n- [ ] sibling")

    assert main(["task", "move", str(path), "1.1", "--top-level"]) == 0

    assert path.read_text() == "- [ ] parent\n- [ ] sibling\n- [ ] child"


def test_move_rejects_descendant_destination(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent\n  - [ ] child")

    assert main(["task", "move", str(path), "1", "--parent", "1.1"]) == 1

    assert "descendants" in capsys.readouterr().err


def test_group_wraps_sibling_items(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("1. [ ] first\n2. [ ] second\n3. [ ] third")

    assert main(["task", "group", str(path), "1", "2", "--description", "group"]) == 0

    assert path.read_text() == (
        "1. [ ] group\n"
        "  1. [ ] first\n"
        "  2. [ ] second\n"
        "2. [ ] third"
    )
    assert "grouped items" in capsys.readouterr().out


def test_group_rejects_non_sibling_paths(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] parent\n  - [ ] child\n- [ ] sibling")

    assert main(["task", "group", str(path), "1.1", "2"]) == 1

    assert "same parent" in capsys.readouterr().err


def test_ungroup_promotes_children(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("1. [ ] group\n  1. [ ] first\n  2. [ ] second\n2. [ ] third")

    assert main(["task", "ungroup", str(path), "1"]) == 0

    assert path.read_text() == "1. [ ] first\n2. [ ] second\n3. [ ] third"
    assert "ungrouped item" in capsys.readouterr().out


def test_ungroup_rejects_leaf_path(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] task")

    assert main(["task", "ungroup", str(path), "1"]) == 1

    assert "task group" in capsys.readouterr().err


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


def test_editor_requires_textual_dependency(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def missing_textual(name: str) -> object:
        assert name in {"textual.app", "textual.widgets", "rich.text"}
        raise ModuleNotFoundError("No module named 'textual'")

    monkeypatch.setattr("roadmaps.editor.import_module", missing_textual)

    assert main(["editor"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == "error: Textual is required for the editor; install roadmaps[editor]\n"
    )


def test_editor_loads_document_and_launches_ui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    path = tmp_path / "roadmap.data"
    launched: list[object] = []

    def run_editor(document: object) -> int:
        launched.append(document)
        return 0

    monkeypatch.setattr("roadmaps.editor.run_editor", run_editor)

    assert main(["editor", "--format", "yaml", str(path)]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert len(launched) == 1


def test_editor_without_path_launches_unnamed_text_document(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    launched: list[Document] = []

    def run_editor(document: Document) -> int:
        launched.append(document)
        return 0

    monkeypatch.setattr("roadmaps.editor.run_editor", run_editor)

    assert main(["editor"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert len(launched) == 1
    document = launched[0]
    assert document.path is None
    assert document.format == "text"
    assert document.exists is False


def test_invalid_roadmap_returns_nonzero(tmp_path: Path, capsys) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text(" - [ ] invalid indentation")

    assert main(["validate", str(path)]) == 1

    assert "indentation" in capsys.readouterr().err
