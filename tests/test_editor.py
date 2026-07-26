import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from roadmaps import COMPLETED, NOT_STARTED, ONGOING, Roadmap, Task, TaskGroup
from roadmaps._documents import Document, load_document
from roadmaps.editor import _top_bar_text, _tree_description, create_editor_app


class FakeTable:
    def __init__(self) -> None:
        self.columns: list[str] = []
        self.rows: list[tuple[object, ...]] = []
        self.cursor_row = 0
        self.focused = False

    def clear(self, *, columns: bool = False) -> None:
        self.rows = []
        if columns:
            self.columns = []

    def add_columns(self, *columns: str) -> None:
        self.columns.extend(columns)

    def add_row(self, *cells: object, key: str) -> None:
        self.rows.append(cells)

    def move_cursor(self, *, row: int, animate: bool = False) -> None:
        self.cursor_row = row

    def focus(self) -> None:
        self.focused = True


class FakeStatic:
    def __init__(self) -> None:
        self.value = ""

    def update(self, value: str) -> None:
        self.value = value


class FakeInput:
    def __init__(self) -> None:
        self.value = ""
        self.styles = SimpleNamespace(display="none")
        self.focused = False

    def focus(self) -> None:
        self.focused = True


def _wire_fake_widgets(app: Any) -> None:
    app.table = FakeTable()
    app.top_bar = FakeStatic()
    app.edit_input = FakeInput()
    app.message_bar = FakeStatic()


def test_create_editor_app_wraps_document_and_state() -> None:
    document = Document(
        Roadmap([TaskGroup("group", tasks=[Task("child")])]),
        "text",
        path=Path("roadmap.roadmap"),
        exists=True,
    )

    app = create_editor_app(document)

    assert app.document is document
    assert [row.description for row in app.state.rows] == ["group", "child"]


def test_top_bar_shows_path_format_and_dirty_marker() -> None:
    app = create_editor_app(Document(Roadmap([Task("task")]), "yaml"))
    app.state.dirty = True

    assert _top_bar_text(app.document, app.state) == "<UNNAMED> [yaml] *"


def test_tree_description_uses_depth_prefix() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("group", tasks=[Task("child")])]), "text")
    )

    assert _tree_description(app.state.rows[0]) == "group"
    assert _tree_description(app.state.rows[1]) == "└─ child"


def test_editor_actions_move_selection_and_toggle_completed_visibility() -> None:
    app = create_editor_app(
        Document(Roadmap([Task("first"), Task("done", status=COMPLETED)]), "text")
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_cursor_down()
    assert app.state.selected_path == (1,)
    assert app.table.cursor_row == 1

    app.action_toggle_hide_completed()
    assert app.state.hide_completed is True
    assert app.state.selected_path == (0,)
    assert app.table.cursor_row == 0
    assert app.message_bar.value == "completed rows hidden"


def test_editor_insert_enters_description_edit_mode() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_insert_unsorted()

    assert [task.description for task in app.document.roadmap.steps] == [
        "first",
        "New task",
    ]
    assert app.state.selected_path == (1,)
    assert app.editing is True
    assert app.edit_input.value == "New task"
    assert app.edit_input.styles.display == "block"


def test_editor_insert_uses_visual_table_cursor_when_state_is_stale() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.table.cursor_row = 1
    app.state.selected_path = (0,)

    app.action_insert_unsorted()

    assert [task.description for task in app.document.roadmap.steps] == [
        "first",
        "second",
        "New task",
    ]
    assert app.state.selected_path == (2,)


def test_editor_description_edit_commit_and_cancel() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_description()
    app.edit_input.value = "updated"
    app._exit_edit_mode(commit=True)

    assert app.document.roadmap.steps[0].description == "updated"
    assert app.state.dirty is True
    assert app.editing is False
    assert app.edit_input.styles.display == "none"

    app.action_edit_description()
    app.edit_input.value = "cancelled"
    app._exit_edit_mode(commit=False)

    assert app.document.roadmap.steps[0].description == "updated"
    assert app.message_bar.value == "edit cancelled"


def test_editor_milestone_prompt_updates_selected_item() -> None:
    app = create_editor_app(Document(Roadmap([Task("task")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_milestone()
    assert app.prompt_kind == "milestone"
    assert app.edit_input.styles.display == "block"
    assert app.message_bar.value == "milestone: enter N, (N), or empty to clear"

    app.edit_input.value = "(3)"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.document.roadmap.steps[0].milestone == 3
    assert app.state.dirty is True
    assert app.prompt_kind is None
    assert app.edit_input.styles.display == "none"
    assert app.message_bar.value == "milestone updated"


def test_editor_priority_prompt_sets_optional_and_clears_priority() -> None:
    app = create_editor_app(Document(Roadmap([Task("task", priority=5)]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_priority()
    app.edit_input.value = "?"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.document.roadmap.steps[0].optional is True
    assert app.table.rows[0][2].plain == "?"

    app.action_edit_priority()
    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.document.roadmap.steps[0].optional is False
    assert app.document.roadmap.steps[0].priority == 0
    assert app.message_bar.value == "priority updated"


def test_editor_completion_prompt_starts_pending_task_by_default() -> None:
    app = create_editor_app(Document(Roadmap([Task("task")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_completion()
    assert app.prompt_kind == "completion-start-confirm"
    assert app.message_bar.value == "Start task? (Y/n)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "completion"

    app.edit_input.value = "75%"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    task = app.document.roadmap.steps[0]
    assert isinstance(task, Task)
    assert task.status == ONGOING
    assert task.completion == 75.0
    assert app.message_bar.value == "completion updated"


def test_editor_completion_prompt_keeps_completed_task_by_default() -> None:
    task = Task("done", status=COMPLETED)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_completion()
    assert app.prompt_kind == "completion-remove-confirm"
    assert app.message_bar.value == "REMOVE COMPLETION MARK? (y/N)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert task.status == COMPLETED
    assert app.prompt_kind is None
    assert app.message_bar.value == "completion edit cancelled"


def test_editor_completion_prompt_can_remove_completed_mark() -> None:
    task = Task("done", status=COMPLETED)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_completion()
    app.edit_input.value = "YES"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "completion"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert task.status == ONGOING
    assert task.completion == 0.0
    assert app.message_bar.value == "completion updated"


def test_editor_completion_shortcuts_adjust_ongoing_task() -> None:
    task = Task("task", status=ONGOING, completion=50.0)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_increase_completion()
    assert task.completion == 51.0
    assert app.message_bar.value == "completion updated"

    app.action_decrease_completion_large()
    assert task.completion == 41.0

    app.action_decrease_completion_large()
    app.action_decrease_completion_large()
    app.action_decrease_completion_large()
    app.action_decrease_completion_large()
    app.action_decrease_completion_large()
    assert task.status == ONGOING
    assert task.completion == 0.0


def test_editor_increment_shortcut_starts_pending_task_by_default() -> None:
    task = Task("task")
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_increase_completion_large()
    assert app.prompt_kind == "completion-adjust-start-confirm"
    assert app.message_bar.value == "Start task? (Y/n)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert task.status == ONGOING
    assert task.completion == 10.0
    assert app.message_bar.value == "completion updated"


def test_editor_completion_shortcut_can_complete_ongoing_task_by_default() -> None:
    task = Task("task", status=ONGOING, completion=99.0)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_increase_completion()
    assert app.prompt_kind == "completion-adjust-complete-confirm"
    assert app.message_bar.value == "Complete task? (Y/n)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert task.status == COMPLETED
    assert task.completion == 100.0
    assert app.message_bar.value == "completion updated"


def test_editor_completed_decrement_shortcut_defaults_to_cancel() -> None:
    task = Task("done", status=COMPLETED)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_decrease_completion()
    assert app.prompt_kind == "completion-adjust-remove-confirm"
    assert app.message_bar.value == "REMOVE COMPLETION MARK? (y/N)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert task.status == COMPLETED
    assert app.message_bar.value == "completion edit cancelled"


def test_editor_completed_decrement_shortcut_applies_delta_after_confirmation() -> None:
    task = Task("done", status=COMPLETED)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_decrease_completion_large()
    app.edit_input.value = "y"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert task.status == ONGOING
    assert task.completion == 90.0
    assert app.message_bar.value == "completion updated"


def test_editor_completion_shortcut_noop_messages() -> None:
    app = create_editor_app(
        Document(Roadmap([Task("pending"), TaskGroup("group", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_decrease_completion()
    assert app.message_bar.value == "task is not started"

    app.action_cursor_down()
    app.action_decrease_completion()
    assert app.message_bar.value == "completion editing is only available for leaf tasks"


def test_editor_metadata_prompts_reject_completed_rows_and_groups() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    Task("done", status=COMPLETED),
                    TaskGroup("group", tasks=[Task("child")]),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_milestone()
    assert app.message_bar.value == "completed rows are read-only"
    app.action_edit_priority()
    assert app.message_bar.value == "completed rows are read-only"

    app.action_cursor_down()
    app.action_edit_completion()
    assert app.message_bar.value == "completion editing is only available for leaf tasks"


def test_editor_invalid_prompt_input_stays_open() -> None:
    app = create_editor_app(Document(Roadmap([Task("task")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_priority()
    app.edit_input.value = "high"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.prompt_kind == "priority"
    assert app.edit_input.styles.display == "block"
    assert "priority" in app.message_bar.value


def test_editor_rejects_completed_description_edit() -> None:
    app = create_editor_app(Document(Roadmap([Task("done", status=COMPLETED)]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_description()

    assert app.editing is False
    assert app.message_bar.value == "completed rows are read-only"


def test_editor_cycle_status_refreshes_and_preserves_visible_selection() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_cursor_down()

    app.action_cycle_status()

    assert app.document.roadmap.steps[1].status != 0
    assert app.state.selected_path == (1,)
    assert app.table.cursor_row == 1
    assert app.message_bar.value == "status updated"


def test_editor_cycle_status_uses_visual_table_cursor_when_state_is_stale() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.table.cursor_row = 1
    app.state.selected_path = (0,)

    app.action_cycle_status()

    assert app.document.roadmap.steps[0].status == NOT_STARTED
    assert app.document.roadmap.steps[1].status != 0
    assert app.state.selected_path == (1,)


def test_editor_move_row_actions_refresh_selection_and_show_messages() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_cursor_down()

    app.action_move_row_up()

    assert [step.description for step in app.document.roadmap.steps] == [
        "second",
        "first",
    ]
    assert app.state.selected_path == (0,)
    assert app.table.cursor_row == 0
    assert app.message_bar.value == "row moved"

    app.action_move_row_up()
    assert app.message_bar.value == "already at top"

    app.action_move_row_down()
    assert [step.description for step in app.document.roadmap.steps] == [
        "first",
        "second",
    ]
    assert app.state.selected_path == (1,)
    assert app.message_bar.value == "row moved"


def test_editor_highlight_event_updates_internal_selection() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.on_data_table_row_highlighted(SimpleNamespace(cursor_row=1))

    assert app.state.selected_path == (1,)


def test_editor_save_named_document_and_defer_unnamed_save(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text", path=path))
    _wire_fake_widgets(app)
    app.state.dirty = True

    app.action_save()

    assert path.read_text() == "- [ ] first"
    assert app.state.dirty is False
    assert app.message_bar.value == "saved"

    unnamed = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(unnamed)
    unnamed.action_save()

    assert unnamed.message_bar.value == "save path prompt is not implemented yet"


def test_editor_save_after_edit_updates_document(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] old")
    app = create_editor_app(load_document(path))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_edit_description()
    app.edit_input.value = "new"

    app.action_save()

    assert path.read_text() == "- [ ] new"
    assert app.editing is False


def test_textual_pilot_drives_editor_keybindings(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    path = tmp_path / "roadmap.roadmap"
    document = Document(
        Roadmap([Task("first"), Task("done", status=COMPLETED)]),
        "text",
        path=path,
    )
    app = create_editor_app(document)

    async def run_pilot() -> None:
        async with app.run_test() as pilot:
            await pilot.press("down")
            assert app.state.selected_path == (1,)

            await pilot.press("ctrl+h")
            assert app.state.hide_completed is True
            assert app.state.selected_path == (0,)

            await pilot.press("ctrl+space")
            assert document.roadmap.steps[0].status != NOT_STARTED

            await pilot.press("ctrl+u")
            assert app.editing is True
            assert app.state.selected_path == (1,)

            app.edit_input.value = "inserted"
            await pilot.press("enter")
            assert app.editing is False
            assert document.roadmap.steps[1].description == "inserted"

            await pilot.press("m")
            app.edit_input.value = "2"
            await pilot.press("enter")
            assert document.roadmap.steps[1].milestone == 2

            await pilot.press("+")
            await pilot.press("enter")
            assert document.roadmap.steps[1].status == ONGOING
            assert document.roadmap.steps[1].completion == 1.0

            await pilot.press("ctrl+k")
            assert document.roadmap.steps[0].description == "inserted"

            await pilot.press("ctrl+s")
            assert app.state.dirty is False

    asyncio.run(run_pilot())
    assert path.read_text().splitlines() == [
        "- [~1.0%] (2) inserted",
        "- [~] first",
        "- [x] done",
    ]
