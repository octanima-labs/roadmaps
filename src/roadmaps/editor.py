from __future__ import annotations

from importlib import import_module
from typing import Any

from roadmaps._documents import Document, save_document
from roadmaps._editor_state import EditorRow, EditorState
from roadmaps.constants import COMPLETED, ONGOING


def run_editor(document: Document) -> int:
    app = create_editor_app(document)
    app.run()
    return 0


def create_editor_app(document: Document) -> Any:
    textual_app = import_module("textual.app")
    textual_widgets = import_module("textual.widgets")
    rich_text = import_module("rich.text")

    app_base: Any = textual_app.App
    data_table: Any = textual_widgets.DataTable
    input_widget: Any = textual_widgets.Input
    static: Any = textual_widgets.Static
    text: Any = rich_text.Text

    class RoadmapEditorApp(app_base):  # type: ignore[misc, valid-type]
        CSS = """
        #top-bar {
            height: 1;
            padding: 0 1;
            background: $panel;
        }

        #roadmap-grid {
            height: 1fr;
        }

        #description-edit {
            display: none;
        }

        #message-bar {
            height: 1;
            padding: 0 1;
        }
        """
        BINDINGS = (
            ("up", "cursor_up", "Up"),
            ("down", "cursor_down", "Down"),
            ("enter", "edit_description", "Edit"),
            ("ctrl+u", "insert_unsorted", "New unsorted"),
            ("ctrl+o", "insert_sorted", "New sorted"),
            ("ctrl+space", "cycle_status", "Cycle status"),
            ("ctrl+h", "toggle_hide_completed", "Hide completed"),
            ("ctrl+s", "save", "Save"),
            ("q", "quit", "Quit"),
        )

        def __init__(self, document: Document) -> None:
            super().__init__()
            self.document = document
            self.state = EditorState(document.roadmap)
            self.table: Any | None = None
            self.top_bar: Any | None = None
            self.edit_input: Any | None = None
            self.message_bar: Any | None = None
            self.editing = False

        def compose(self) -> Any:
            self.top_bar = static(_top_bar_text(self.document, self.state), id="top-bar")
            yield self.top_bar
            table = data_table(id="roadmap-grid", zebra_stripes=True)
            table.cursor_type = "row"
            self.table = table
            yield table
            self.edit_input = input_widget(id="description-edit")
            yield self.edit_input
            self.message_bar = static("", id="message-bar")
            yield self.message_bar

        def on_mount(self) -> None:
            table = self.table
            if table is None:
                table = self.query_one("#roadmap-grid", data_table)
                self.table = table
            self._refresh_table(reset_selection=True)

        def action_cursor_up(self) -> None:
            self._exit_edit_mode(commit=False)
            if self.state.move_selection(-1):
                self._select_current_row()

        def action_cursor_down(self) -> None:
            self._exit_edit_mode(commit=False)
            if self.state.move_selection(1):
                self._select_current_row()

        def action_edit_description(self) -> None:
            self._start_description_edit()

        def action_insert_unsorted(self) -> None:
            self._exit_edit_mode(commit=False)
            self.state.insert_unsorted_task()
            self._refresh_table(reset_selection=False)
            self._start_description_edit()

        def action_insert_sorted(self) -> None:
            self._exit_edit_mode(commit=False)
            self.state.insert_sorted_task()
            self._refresh_table(reset_selection=False)
            self._start_description_edit()

        def action_cycle_status(self) -> None:
            self._exit_edit_mode(commit=False)
            if self.state.cycle_selected_status():
                self._refresh_table(reset_selection=True)
                self._set_message("status updated")

        def action_toggle_hide_completed(self) -> None:
            self._exit_edit_mode(commit=False)
            self.state.toggle_hide_completed()
            self._refresh_table(reset_selection=True)
            self._set_message(
                "completed rows hidden"
                if self.state.hide_completed
                else "completed rows visible"
            )

        def action_save(self) -> None:
            self._exit_edit_mode(commit=True)
            if self.document.path is None:
                self._set_message("save path prompt is not implemented yet")
                return

            try:
                save_document(self.document)
            except OSError as exc:
                self._set_message(f"save failed: {exc}")
                return
            except ValueError as exc:
                self._set_message(f"save failed: {exc}")
                return
            self.state.dirty = False
            self._refresh_top_bar()
            self._set_message("saved")

        def on_input_submitted(self, event: Any) -> None:
            if event.input is self.edit_input:
                self._exit_edit_mode(commit=True)

        def key_escape(self) -> None:
            self._exit_edit_mode(commit=False)

        def _start_description_edit(self) -> None:
            row = self.state.selected_row
            if row is None:
                self._set_message("no row selected")
                return
            if row.completed:
                self._set_message("completed rows are read-only")
                return

            edit_input = self._edit_input()
            edit_input.value = row.description
            edit_input.styles.display = "block"
            edit_input.focus()
            self.editing = True
            self._set_message("editing description")

        def _exit_edit_mode(self, *, commit: bool) -> None:
            if not self.editing:
                return

            edit_input = self._edit_input()
            if commit:
                try:
                    changed = self.state.update_selected_description(edit_input.value)
                except ValueError as exc:
                    self._set_message(str(exc))
                    return
                if changed:
                    self._refresh_table(reset_selection=True)
                    self._set_message("description updated")
                else:
                    self._set_message("description unchanged")
            else:
                self._set_message("edit cancelled")

            edit_input.styles.display = "none"
            edit_input.value = ""
            self.editing = False
            self._table().focus()

        def _refresh_table(self, *, reset_selection: bool) -> None:
            if reset_selection:
                rows = self.state.rows
                self.state.selected_path = rows[0].path if rows else None
            _populate_table(self._table(), self.state, text)
            self._select_current_row()
            self._refresh_top_bar()

        def _select_current_row(self) -> None:
            table = self._table()
            rows = self.state.rows
            if self.state.selected_path is None or not rows:
                return
            for index, row in enumerate(rows):
                if row.path == self.state.selected_path:
                    table.move_cursor(row=index, animate=False)
                    return

        def _refresh_top_bar(self) -> None:
            top_bar = self.top_bar or self.query_one("#top-bar", static)
            self.top_bar = top_bar
            top_bar.update(_top_bar_text(self.document, self.state))

        def _set_message(self, message: str) -> None:
            message_bar = self.message_bar or self.query_one("#message-bar", static)
            self.message_bar = message_bar
            message_bar.update(message)

        def _table(self) -> Any:
            if self.table is None:
                self.table = self.query_one("#roadmap-grid", data_table)
            return self.table

        def _edit_input(self) -> Any:
            if self.edit_input is None:
                self.edit_input = self.query_one("#description-edit", input_widget)
            return self.edit_input

    return RoadmapEditorApp(document)


def _top_bar_text(document: Document, state: EditorState) -> str:
    path_text = str(document.path) if document.path is not None else "<UNNAMED>"
    dirty_marker = " *" if state.dirty else ""
    return f"{path_text} [{document.format}]{dirty_marker}"


def _populate_table(table: Any, state: EditorState, text: Any) -> None:
    table.clear(columns=True)
    table.add_columns("Order", "Completion", "Priority", "Milestone", "Description")
    for row in state.rows:
        table.add_row(
            _styled_text(row.order_text, row, text),
            _styled_text(row.completion_text, row, text),
            _styled_text(row.priority_text, row, text),
            _styled_text(row.milestone_text, row, text),
            _styled_text(_tree_description(row), row, text),
            key=str(row.path),
        )


def _styled_text(value: str, row: EditorRow, text: Any) -> Any:
    style = ""
    if row.status == COMPLETED:
        style = "dim"
    elif row.status == ONGOING:
        style = "yellow"
    return text(value, style=style)


def _tree_description(row: EditorRow) -> str:
    if row.depth == 0:
        return row.description
    guide = "  " * (row.depth - 1)
    return f"{guide}└─ {row.description}"
