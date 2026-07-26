from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from roadmaps._documents import (
    NEW_MARKDOWN_HEADING_LEVEL,
    Document,
    detect_format,
    save_document,
)
from roadmaps._editor_state import (
    EditorRow,
    EditorState,
    parse_completion_prompt,
    parse_confirmation_prompt,
    parse_milestone_prompt,
    parse_priority_prompt,
)
from roadmaps.constants import COMPLETED, NOT_STARTED, ONGOING


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
            ("m", "edit_milestone", "Milestone"),
            ("p", "edit_priority", "Priority"),
            ("e", "edit_completion", "Completion"),
            ("+", "increase_completion", "Completion +1"),
            ("-", "decrease_completion", "Completion -1"),
            ("]", "increase_completion_large", "Completion +10"),
            ("[", "decrease_completion_large", "Completion -10"),
            ("ctrl+k", "move_row_up", "Move row up"),
            ("ctrl+j", "move_row_down", "Move row down"),
            (">", "indent_row", "Indent row"),
            ("<", "outdent_row", "Outdent row"),
            ("space", "toggle_row_mark", "Select row"),
            ("ctrl+g", "group_rows", "Group rows"),
            ("ctrl+t", "toggle_group_collapsed", "Toggle group"),
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
            self.prompt_kind: str | None = None
            self.completion_allow_start = False
            self.completion_allow_completed = False
            self.completion_adjust_delta = 0.0
            self.save_after_prompt_quit = False
            self.pending_save_path: Path | None = None
            self.pending_save_format: str | None = None

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
            self._refresh_table()

        def action_cursor_up(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            if self.state.move_selection(-1):
                self._select_current_row()

        def action_cursor_down(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            if self.state.move_selection(1):
                self._select_current_row()

        def action_edit_description(self) -> None:
            self._cancel_prompt()
            self._sync_selection_from_table_cursor()
            self._start_description_edit()

        def action_edit_milestone(self) -> None:
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            row = self.state.selected_row
            if row is None:
                self._set_message("no row selected")
                return
            if row.completed and not self.state.selected_paths:
                self._set_message("completed rows are read-only")
                return
            self._start_prompt(
                "milestone",
                "milestone: enter N, (N), or empty to clear",
                "" if self.state.selected_paths else row.milestone_text,
            )

        def action_edit_priority(self) -> None:
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            row = self.state.selected_row
            if row is None:
                self._set_message("no row selected")
                return
            if row.completed and not self.state.selected_paths:
                self._set_message("completed rows are read-only")
                return
            self._start_prompt(
                "priority",
                "priority: enter !, ?, ^N, N, or empty to clear",
                "" if self.state.selected_paths else row.priority_text,
            )

        def action_edit_completion(self) -> None:
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            row = self.state.selected_row
            if row is None:
                self._set_message("no row selected")
                return
            if self.state.selected_paths:
                self._start_completion_prompt(allow_start=True)
                return
            if row.group:
                self._set_message("completion editing is only available for leaf tasks")
                return
            if row.status == NOT_STARTED:
                self._start_prompt("completion-start-confirm", "Start task? (Y/n)")
                return
            if row.status == COMPLETED:
                self._start_prompt(
                    "completion-remove-confirm",
                    "REMOVE COMPLETION MARK? (y/N)",
                )
                return
            self._start_completion_prompt()

        def action_increase_completion(self) -> None:
            self._adjust_completion_shortcut(1.0)

        def action_decrease_completion(self) -> None:
            self._adjust_completion_shortcut(-1.0)

        def action_increase_completion_large(self) -> None:
            self._adjust_completion_shortcut(10.0)

        def action_decrease_completion_large(self) -> None:
            self._adjust_completion_shortcut(-10.0)

        def action_toggle_row_mark(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            if self.state.toggle_selected_row_mark():
                self._refresh_table()
                self._set_message("row selection toggled")
            else:
                self._set_message("no row selected")

        def action_group_rows(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            had_marks = bool(self.state.selected_paths)
            try:
                group = self.state.group_selected_rows()
            except ValueError as exc:
                self._set_message(str(exc))
                return
            if group is None:
                self._set_message("row is already a group")
                return
            self._refresh_table()
            if had_marks:
                self._set_message("rows grouped")
                self._start_description_edit()
            else:
                self._set_message("task converted to group")

        def action_toggle_group_collapsed(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            if self.state.toggle_selected_group_collapsed():
                self._refresh_table()
                self._set_message("group toggled")
            else:
                self._set_message("selected row is not a group")

        def action_move_row_up(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            if self.state.selected_row is None:
                self._set_message("no row selected")
                return
            if self.state.move_selected_row_up():
                self._refresh_table()
                self._set_message("row moved")
            else:
                self._set_message("already at top")

        def action_move_row_down(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            if self.state.selected_row is None:
                self._set_message("no row selected")
                return
            if self.state.move_selected_row_down():
                self._refresh_table()
                self._set_message("row moved")
            else:
                self._set_message("already at bottom")

        def action_indent_row(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            if self.state.selected_row is None:
                self._set_message("no row selected")
                return
            if self.state.indent_selected_row():
                self._refresh_table()
                self._set_message("row indented")
            else:
                self._set_message("cannot indent row")

        def action_outdent_row(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            if self.state.selected_row is None:
                self._set_message("no row selected")
                return
            if self.state.outdent_selected_row():
                self._refresh_table()
                self._set_message("row outdented")
            else:
                self._set_message("already at top level")

        def action_insert_unsorted(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            self.state.insert_unsorted_task()
            self._refresh_table()
            self._start_description_edit()

        def action_insert_sorted(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            self.state.insert_sorted_task()
            self._refresh_table()
            self._start_description_edit()

        def action_cycle_status(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            if self.state.cycle_selected_status():
                self._refresh_table()
                self._set_message("status updated")

        def action_toggle_hide_completed(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            self.state.toggle_hide_completed()
            self._refresh_table()
            self._set_message(
                "completed rows hidden"
                if self.state.hide_completed
                else "completed rows visible"
            )

        def action_save(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=True)
            if self.editing:
                return
            if self.document.path is None:
                self._start_save_path_prompt(exit_after=False)
                return

            self._save_current_document(exit_after=False)

        def action_quit(self) -> None:
            if self.prompt_kind is not None:
                self._cancel_prompt()
                return
            self._exit_edit_mode(commit=True)
            if self.editing:
                return
            if not self.state.dirty:
                self._quit_app()
                return
            self._start_prompt(
                "exit-save-confirm",
                "Save changes before exit? (Y/n/c)",
            )

        def on_input_submitted(self, event: Any) -> None:
            if event.input is self.edit_input:
                if self.prompt_kind is not None:
                    self._submit_prompt()
                else:
                    self._exit_edit_mode(commit=True)

        def on_data_table_row_highlighted(self, event: Any) -> None:
            self._sync_selection_from_cursor_row(event.cursor_row)

        def on_mouse_down(self, event: Any) -> None:
            if getattr(event, "button", None) != 3:
                return
            table = self._table()
            hover_row = getattr(table, "hover_row", None)
            if hover_row is None:
                return
            self._sync_selection_from_cursor_row(hover_row)
            if self.state.toggle_selected_group_collapsed():
                self._refresh_table()
                self._set_message("group toggled")
            else:
                self._set_message("selected row is not a group")
            stop = getattr(event, "stop", None)
            if stop is not None:
                stop()

        def key_escape(self) -> None:
            if self.prompt_kind is not None:
                self._cancel_prompt()
            else:
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

        def _start_prompt(
            self,
            kind: str,
            message: str,
            value: str = "",
        ) -> None:
            self.prompt_kind = kind
            edit_input = self._edit_input()
            edit_input.value = value
            edit_input.styles.display = "block"
            edit_input.focus()
            self._set_message(message)

        def _start_completion_prompt(
            self,
            *,
            allow_start: bool = False,
            allow_completed: bool = False,
        ) -> None:
            row = self.state.selected_row
            value = "" if row is None or row.completion_text == "0%" else row.completion_text
            self.completion_allow_start = allow_start
            self.completion_allow_completed = allow_completed
            self._start_prompt(
                "completion",
                "completion: enter 0, 50, 50.0, 50%, or empty to clear",
                value,
            )

        def _submit_prompt(self) -> None:
            edit_input = self._edit_input()
            try:
                if self.prompt_kind == "milestone":
                    milestone = parse_milestone_prompt(edit_input.value)
                    changed = self.state.update_selected_milestone(milestone)
                    self._finish_prompt("milestone updated" if changed else "milestone unchanged")
                elif self.prompt_kind == "priority":
                    priority = parse_priority_prompt(edit_input.value)
                    changed = self.state.update_selected_priority(priority)
                    self._finish_prompt("priority updated" if changed else "priority unchanged")
                elif self.prompt_kind == "completion-start-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=True):
                        self._start_completion_prompt(allow_start=True)
                    else:
                        self._finish_prompt("completion edit cancelled")
                elif self.prompt_kind == "completion-remove-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=False):
                        self._start_completion_prompt(allow_completed=True)
                    else:
                        self._finish_prompt("completion edit cancelled")
                elif self.prompt_kind == "completion-adjust-start-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=True):
                        self._apply_completion_adjustment(allow_start=True)
                    else:
                        self._finish_prompt("completion edit cancelled")
                elif self.prompt_kind == "completion-adjust-remove-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=False):
                        self._apply_completion_adjustment(allow_completed=True)
                    else:
                        self._finish_prompt("completion edit cancelled")
                elif self.prompt_kind == "completion-adjust-complete-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=True):
                        self._apply_completion_adjustment(allow_complete=True)
                    else:
                        self._finish_prompt("completion edit cancelled")
                elif self.prompt_kind == "completion":
                    completion = parse_completion_prompt(edit_input.value)
                    changed = self.state.update_selected_completion(
                        completion,
                        allow_start=self.completion_allow_start or bool(self.state.selected_paths),
                        allow_completed=self.completion_allow_completed,
                    )
                    self._finish_prompt("completion updated" if changed else "completion unchanged")
                elif self.prompt_kind == "save-path":
                    self._submit_save_path(edit_input.value)
                elif self.prompt_kind == "save-format":
                    self.pending_save_format = parse_save_format_prompt(edit_input.value)
                    self._confirm_or_save_pending_path()
                elif self.prompt_kind == "save-overwrite-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=False):
                        self._save_to_pending_path()
                    else:
                        self._finish_prompt("save cancelled")
                elif self.prompt_kind == "exit-save-confirm":
                    choice = parse_exit_save_prompt(edit_input.value)
                    if choice == "save":
                        self._finish_prompt("saving")
                        self._save_for_exit()
                    elif choice == "discard":
                        self._quit_app()
                    else:
                        self._finish_prompt("exit cancelled")
                elif self.prompt_kind == "save-failure":
                    choice = parse_save_failure_prompt(edit_input.value)
                    if choice == "retry":
                        self._finish_prompt("retrying save")
                        self._retry_failed_exit_save()
                    elif choice == "change":
                        self._start_save_path_prompt(exit_after=True)
                    else:
                        self._quit_app()
            except ValueError as exc:
                self._set_message(str(exc))

        def _adjust_completion_shortcut(self, delta: float) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            row = self.state.selected_row
            if row is None:
                self._set_message("no row selected")
                return
            if row.group:
                self._set_message("completion editing is only available for leaf tasks")
                return
            if row.status == NOT_STARTED:
                if delta < 0:
                    self._set_message("task is not started")
                    return
                self.completion_adjust_delta = delta
                self._start_prompt("completion-adjust-start-confirm", "Start task? (Y/n)")
                return
            if row.status == COMPLETED:
                if delta > 0:
                    self._set_message("task is already completed")
                    return
                self.completion_adjust_delta = delta
                self._start_prompt(
                    "completion-adjust-remove-confirm",
                    "REMOVE COMPLETION MARK? (y/N)",
                )
                return
            if row.item.completion + delta >= 100.0:
                self.completion_adjust_delta = delta
                self._start_prompt("completion-adjust-complete-confirm", "Complete task? (Y/n)")
                return

            try:
                changed = self.state.adjust_selected_completion(delta)
            except (TypeError, ValueError) as exc:
                self._set_message(str(exc))
                return
            self._refresh_table()
            self._set_message("completion updated" if changed else "completion unchanged")

        def _apply_completion_adjustment(
            self,
            *,
            allow_start: bool = False,
            allow_completed: bool = False,
            allow_complete: bool = False,
        ) -> None:
            changed = self.state.adjust_selected_completion(
                self.completion_adjust_delta,
                allow_start=allow_start,
                allow_completed=allow_completed,
                allow_complete=allow_complete,
            )
            self._finish_prompt("completion updated" if changed else "completion unchanged")

        def _start_save_path_prompt(self, *, exit_after: bool) -> None:
            self.save_after_prompt_quit = exit_after
            self.pending_save_path = None
            self.pending_save_format = None
            self._start_prompt("save-path", "Save as path:")

        def _submit_save_path(self, value: str) -> None:
            path_text = value.strip()
            if not path_text:
                msg = "save path is required"
                raise ValueError(msg)

            path = Path(path_text).expanduser()
            self.pending_save_path = path
            try:
                self.pending_save_format = detect_format(path, None)
            except ValueError:
                self._start_prompt("save-format", "Format? text/json/yaml/markdown (yaml)")
                return
            self._confirm_or_save_pending_path()

        def _confirm_or_save_pending_path(self) -> None:
            path = self.pending_save_path
            if path is None:
                msg = "save path is required"
                raise ValueError(msg)
            if path.exists():
                self._start_prompt("save-overwrite-confirm", "Overwrite existing file? (y/N)")
                return
            self._save_to_pending_path()

        def _save_current_document(self, *, exit_after: bool) -> None:
            if self.document.path is None:
                self._start_save_path_prompt(exit_after=exit_after)
                return
            self.pending_save_path = self.document.path
            self.pending_save_format = self.document.format
            self._save_to_path(self.document.path, self.document.format, exit_after=exit_after)

        def _save_for_exit(self) -> None:
            self.save_after_prompt_quit = True
            self._save_current_document(exit_after=True)

        def _retry_failed_exit_save(self) -> None:
            path = self.pending_save_path
            document_format = self.pending_save_format
            if path is None or document_format is None:
                self._start_save_path_prompt(exit_after=True)
                return
            self._save_to_path(path, document_format, exit_after=True)

        def _save_to_pending_path(self) -> None:
            path = self.pending_save_path
            document_format = self.pending_save_format
            if path is None or document_format is None:
                msg = "save path and format are required"
                raise ValueError(msg)
            self._save_to_path(
                path,
                document_format,
                exit_after=self.save_after_prompt_quit,
            )

        def _save_to_path(
            self,
            path: Path,
            document_format: str,
            *,
            exit_after: bool,
        ) -> None:
            old_path = self.document.path
            old_exists = self.document.exists
            old_format = self.document.format
            old_heading_level = self.document.markdown_heading_level
            self.document.format = document_format
            self.document.markdown_heading_level = (
                old_heading_level or NEW_MARKDOWN_HEADING_LEVEL
                if document_format == "markdown"
                else None
            )
            try:
                save_document(self.document, path)
            except (OSError, ValueError) as exc:
                self.document.path = old_path
                self.document.exists = old_exists
                self.document.format = old_format
                self.document.markdown_heading_level = old_heading_level
                if exit_after:
                    self._start_prompt(
                        "save-failure",
                        f"Save failed: retry, change path, or discard? (r/c/d) {exc}",
                    )
                else:
                    self._finish_prompt(f"save failed: {exc}")
                return

            self.state.dirty = False
            self.save_after_prompt_quit = False
            self.pending_save_path = None
            self.pending_save_format = None
            self._refresh_top_bar()
            if exit_after:
                self._quit_app()
            else:
                self._finish_prompt("saved")

        def _quit_app(self) -> None:
            self.exit()

        def _finish_prompt(self, message: str) -> None:
            prompt_kind = self.prompt_kind
            edit_input = self._edit_input()
            edit_input.styles.display = "none"
            edit_input.value = ""
            self.prompt_kind = None
            self.completion_allow_start = False
            self.completion_allow_completed = False
            self.completion_adjust_delta = 0.0
            if prompt_kind != "save-failure":
                self.save_after_prompt_quit = False
            self._refresh_table()
            self._table().focus()
            self._set_message(message)

        def _cancel_prompt(self) -> None:
            if self.prompt_kind is None:
                return
            edit_input = self._edit_input()
            edit_input.styles.display = "none"
            edit_input.value = ""
            self.prompt_kind = None
            self.completion_allow_start = False
            self.completion_allow_completed = False
            self.completion_adjust_delta = 0.0
            self.save_after_prompt_quit = False
            self.pending_save_path = None
            self.pending_save_format = None
            self._table().focus()
            self._set_message("edit cancelled")

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
                    self._refresh_table()
                    self._set_message("description updated")
                else:
                    self._set_message("description unchanged")
            else:
                self._set_message("edit cancelled")

            edit_input.styles.display = "none"
            edit_input.value = ""
            self.editing = False
            self._table().focus()

        def _refresh_table(self) -> None:
            self.state.repair_selection()
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

        def _sync_selection_from_table_cursor(self) -> None:
            self._sync_selection_from_cursor_row(self._table().cursor_row)

        def _sync_selection_from_cursor_row(self, cursor_row: int) -> None:
            rows = self.state.rows
            if not rows:
                self.state.selected_path = None
                return
            if 0 <= cursor_row < len(rows):
                self.state.selected_path = rows[cursor_row].path

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
    rows = state.rows
    descriptions = _tree_descriptions(rows)
    for row in rows:
        table.add_row(
            _styled_text(row.order_text, row, text),
            _styled_text(row.completion_text, row, text),
            _styled_text(row.priority_text, row, text),
            _styled_text(row.milestone_text, row, text),
            _styled_text(descriptions[row.path], row, text),
            key=str(row.path),
        )


def _styled_text(value: str, row: EditorRow, text: Any) -> Any:
    style = ""
    if row.status == COMPLETED:
        style = "dim"
    elif row.status == ONGOING:
        style = "yellow"
    return text(value, style=style)


def _tree_description(row: EditorRow, rows: list[EditorRow] | None = None) -> str:
    if rows is None:
        if row.depth == 0:
            return row.description
        guide = "  " * (row.depth - 1)
        return f"{guide}└─ {row.description}"
    return _tree_descriptions(rows)[row.path]


def _tree_descriptions(rows: list[EditorRow]) -> dict[tuple[int, ...], str]:
    sibling_indexes = _visible_sibling_indexes(rows)
    return {row.path: _tree_description_for_row(row, sibling_indexes) for row in rows}


def _tree_description_for_row(
    row: EditorRow,
    sibling_indexes: dict[tuple[int, ...], list[int]],
) -> str:
    marker = "* " if row.selected else ""
    collapsed = "▸ " if row.collapsed else ""
    if row.depth == 0:
        return f"{marker}{collapsed}{row.description}"

    prefix = ""
    for depth in range(row.depth):
        ancestor_parent = row.path[:depth]
        ancestor_index = row.path[depth]
        if _has_later_sibling(sibling_indexes, ancestor_parent, ancestor_index):
            prefix += "│  "
        elif depth > 0:
            prefix += "   "

    parent_path = row.path[:-1]
    branch = "├─ " if _has_later_sibling(sibling_indexes, parent_path, row.path[-1]) else "└─ "
    return f"{prefix}{branch}{marker}{collapsed}{row.description}"


def _visible_sibling_indexes(rows: list[EditorRow]) -> dict[tuple[int, ...], list[int]]:
    indexes: dict[tuple[int, ...], list[int]] = {}
    for row in rows:
        indexes.setdefault(row.path[:-1], []).append(row.path[-1])
    return indexes


def _has_later_sibling(
    sibling_indexes: dict[tuple[int, ...], list[int]],
    parent_path: tuple[int, ...],
    index: int,
) -> bool:
    siblings = sibling_indexes.get(parent_path, [])
    return bool(siblings and index < siblings[-1])


def parse_save_format_prompt(value: str) -> str:
    text = value.strip().casefold()
    if not text:
        return "yaml"
    if text in {"text", "json", "yaml", "markdown"}:
        return text
    msg = "format must be text, json, yaml, or markdown"
    raise ValueError(msg)


def parse_exit_save_prompt(value: str) -> str:
    text = value.strip().casefold()
    if not text or text in {"y", "yes"}:
        return "save"
    if text in {"n", "no"}:
        return "discard"
    if text in {"c", "cancel"}:
        return "cancel"
    msg = "answer must be yes, no, or cancel"
    raise ValueError(msg)


def parse_save_failure_prompt(value: str) -> str:
    text = value.strip().casefold()
    if text in {"r", "retry"}:
        return "retry"
    if text in {"c", "change"}:
        return "change"
    if text in {"d", "discard"}:
        return "discard"
    msg = "answer must be retry, change path, or discard"
    raise ValueError(msg)
