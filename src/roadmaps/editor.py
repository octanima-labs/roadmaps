from __future__ import annotations

import textwrap
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from time import monotonic
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
from roadmaps.constants import (
    COMPLETED,
    NOT_STARTED,
    ONGOING,
    TUI_NOTIFICATION_ERROR_TIMEOUT_SECONDS,
    TUI_NOTIFICATION_INFO_TIMEOUT_SECONDS,
    TUI_NOTIFICATION_MAX_LINES,
    TUI_NOTIFICATION_MAX_VISIBLE,
    TUI_NOTIFICATION_SUCCESS_TIMEOUT_SECONDS,
    TUI_NOTIFICATION_WARNING_TIMEOUT_SECONDS,
    TUI_NOTIFICATION_WIDTH,
    TUI_TABLE_ROW_HEIGHT,
)

_PRIORITY_GRADIENT_LOW = "#22c55e"
_PRIORITY_GRADIENT_MID = "#facc15"
_PRIORITY_GRADIENT_HIGH = "#ef4444"
_TABLE_CELL_COUNT = 5
_MIN_DESCRIPTION_WIDTH = 20
_FIXED_TABLE_WIDTH = 46
_RIGHT_CLICK_DOUBLE_CLICK_SECONDS = 0.5

NotificationSeverity = str


@dataclass(frozen=True)
class _Notification:
    id: int
    message: str
    severity: NotificationSeverity


def run_editor(document: Document) -> int:
    app = create_editor_app(document)
    app.run()
    return 0


def create_editor_app(document: Document) -> Any:
    textual_app = import_module("textual.app")
    textual_containers = import_module("textual.containers")
    textual_widgets = import_module("textual.widgets")
    rich_text = import_module("rich.text")
    rich_style = import_module("rich.style")
    import_module("rich_gradient")

    app_base: Any = textual_app.App
    center_middle: Any = textual_containers.CenterMiddle
    vertical_scroll: Any = textual_containers.VerticalScroll
    data_table: Any = textual_widgets.DataTable
    input_widget: Any = textual_widgets.Input
    text_area_widget: Any = textual_widgets.TextArea
    static: Any = textual_widgets.Static
    text: Any = rich_text.Text
    style_cls: Any = rich_style.Style

    class RoadmapDataTable(data_table):  # type: ignore[misc, valid-type]
        BINDINGS = (
            ("enter", "edit_description", "Edit"),
        )

        def action_edit_description(self) -> None:
            self.app.action_edit_description()

        async def _on_click(self, event: Any) -> None:
            button = getattr(event, "button", None)
            if button == 1 and getattr(event, "chain", 1) >= 2:
                row_index = self.app._event_table_row_index(event)
                if row_index is not None:
                    self.app._cancel_prompt()
                    self.app._exit_edit_mode(commit=False)
                    self.app._sync_selection_from_cursor_row(row_index)
                    self.app._start_description_edit()
                    event.stop()
                    return
            await super()._on_click(event)

    class DescriptionTextArea(text_area_widget):  # type: ignore[misc, valid-type]
        def _on_key(self, event: Any) -> None:
            if event.key == "enter":
                self.app._exit_edit_mode(commit=True)
                event.prevent_default()
                event.stop()
            elif event.key == "alt+enter":
                self.insert("\n")
                event.prevent_default()
                event.stop()

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

        #description-area {
            display: none;
            height: 4;
        }

        #message-bar {
            height: 1;
            padding: 0 1;
        }

        .notification-toast {
            display: none;
            layer: notifications;
            width: 32;
            height: 2;
        }

        #cheatsheet-overlay {
            display: none;
            layer: overlay;
            width: 100%;
            height: 100%;
            align: center middle;
        }

        #cheatsheet-panel {
            width: 92%;
            height: 88%;
            padding: 1 2;
            border: round $accent;
            background: $surface;
            color: $text;
        }

        #cheatsheet {
            width: 100%;
            height: auto;
        }
        """
        BINDINGS = (
            ("f1", "toggle_cheatsheet", "Help"),
            ("up", "cursor_up", "Up"),
            ("down", "cursor_down", "Down"),
            ("shift+up", "select_up", "Select up"),
            ("shift+down", "select_down", "Select down"),
            ("enter", "edit_description", "Edit"),
            ("c", "copy_descriptions", "Copy"),
            ("m", "edit_milestone", "Milestone"),
            ("p", "edit_priority", "Priority"),
            ("alt+up", "increase_priority", "Priority +1"),
            ("alt+down", "decrease_priority", "Priority -1"),
            ("alt+shift+up", "increase_priority_large", "Priority +10"),
            ("alt+shift+down", "decrease_priority_large", "Priority -10"),
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
            ("ctrl+shift+t", "toggle_all_group_collapsed", "Toggle all groups"),
            ("ctrl+d", "toggle_description_expanded", "Toggle description"),
            ("ctrl+shift+d", "toggle_all_descriptions_expanded", "Toggle descriptions"),
            ("delete", "delete_rows", "Delete rows"),
            ("o", "insert_sorted", "New sorted"),
            ("u", "insert_unsorted", "New unsorted"),
            ("ctrl+u", "insert_unsorted_subtask", "New unsorted subtask"),
            ("ctrl+o", "insert_sorted_subtask", "New sorted subtask"),
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
            self.description_area: Any | None = None
            self.message_bar: Any | None = None
            self.notification_slots: list[Any] = []
            self.visible_notifications: list[_Notification] = []
            self.next_notification_id = 1
            self.expanded_description_item_ids: set[int] = set()
            self.cheatsheet: Any | None = None
            self.cheatsheet_panel: Any | None = None
            self.cheatsheet_overlay: Any | None = None
            self.cheatsheet_visible = False
            self.editing = False
            self.prompt_kind: str | None = None
            self.completion_allow_start = False
            self.completion_allow_completed = False
            self.completion_adjust_delta = 0.0
            self.save_after_prompt_quit = False
            self.pending_save_path: Path | None = None
            self.pending_save_format: str | None = None
            self._last_right_click_description_toggle_path: tuple[int, ...] | None = None
            self._last_right_click_description_toggle_item_id: int | None = None
            self._last_right_click_path: tuple[int, ...] | None = None
            self._last_right_click_time = 0.0

        def compose(self) -> Any:
            self.top_bar = static(
                _top_bar_renderable(self.document, self.state, text),
                id="top-bar",
            )
            yield self.top_bar
            table = RoadmapDataTable(id="roadmap-grid", zebra_stripes=True)
            table.cursor_type = "row"
            self.table = table
            yield table
            self.edit_input = input_widget(id="description-edit")
            yield self.edit_input
            self.description_area = DescriptionTextArea(
                id="description-area",
                show_line_numbers=False,
                soft_wrap=True,
            )
            yield self.description_area
            self.message_bar = static("", id="message-bar")
            yield self.message_bar
            self.notification_slots = [
                static("", id=f"notification-{index}", classes="notification-toast")
                for index in range(TUI_NOTIFICATION_MAX_VISIBLE)
            ]
            yield from self.notification_slots
            self.cheatsheet = static(_cheatsheet_renderable(text), id="cheatsheet")
            self.cheatsheet_panel = vertical_scroll(
                self.cheatsheet,
                id="cheatsheet-panel",
            )
            self.cheatsheet_overlay = center_middle(
                self.cheatsheet_panel,
                id="cheatsheet-overlay",
            )
            yield self.cheatsheet_overlay

        def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
            return not (self.cheatsheet_visible and action != "toggle_cheatsheet")

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

        def action_select_up(self) -> None:
            self._extend_selection(-1)

        def action_select_down(self) -> None:
            self._extend_selection(1)

        def action_toggle_cheatsheet(self) -> None:
            if self.cheatsheet_visible:
                self._hide_cheatsheet()
            else:
                self._show_cheatsheet()

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

        def action_increase_priority(self) -> None:
            self._adjust_priority_shortcut(1)

        def action_decrease_priority(self) -> None:
            self._adjust_priority_shortcut(-1)

        def action_increase_priority_large(self) -> None:
            self._adjust_priority_shortcut(10)

        def action_decrease_priority_large(self) -> None:
            self._adjust_priority_shortcut(-10)

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

        def action_copy_descriptions(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            rows = self.state.selected_rows if self.state.selected_paths else [self.state.selected_row]
            descriptions = [row.description for row in rows if row is not None]
            if not descriptions:
                self._set_message("no row selected")
                return
            self.copy_to_clipboard("\n".join(descriptions))
            self._set_message(
                "description copied"
                if len(descriptions) == 1
                else f"{len(descriptions)} descriptions copied"
            )

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

        def action_toggle_all_group_collapsed(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            had_groups = any(row.group for row in self.state.rows)
            changed, expanded = self.state.toggle_visible_groups_collapsed()
            self._refresh_table()
            if changed or had_groups:
                self._set_message("groups expanded" if expanded else "groups collapsed")
            else:
                self._set_message("no visible groups changed")

        def action_toggle_description_expanded(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            rows = self.state.selected_rows if self.state.selected_paths else [self.state.selected_row]
            changed = self._toggle_description_rows_expanded([row for row in rows if row is not None])
            if changed:
                self._refresh_table()
                self._set_message("description toggled" if changed == 1 else "descriptions toggled")
            else:
                self._set_message("description already fully visible")

        def action_toggle_all_descriptions_expanded(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            rows = self._rows_with_hidden_descriptions(self.state.rows)
            if not rows:
                self._set_message("descriptions already fully visible")
                return
            item_ids = {id(row.item) for row in rows}
            if any(item_id not in self.expanded_description_item_ids for item_id in item_ids):
                self.expanded_description_item_ids.update(item_ids)
                message = "descriptions expanded"
            else:
                self.expanded_description_item_ids.difference_update(item_ids)
                message = "descriptions collapsed"
            self._refresh_table()
            self._set_message(message)

        def action_delete_rows(self) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            count = self.state.selected_delete_count()
            if count == 0:
                self._set_message("no row selected")
                return
            message = "Delete row? (y/N)" if count == 1 else f"Delete {count} rows? (y/N)"
            self._start_prompt("delete-confirm", message)

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

        def action_insert_unsorted_subtask(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            if self.state.insert_unsorted_subtask() is None:
                self._set_message("no row selected")
                return
            self._refresh_table()
            self._start_description_edit()

        def action_insert_sorted_subtask(self) -> None:
            self._cancel_prompt()
            self._exit_edit_mode(commit=False)
            self._sync_selection_from_table_cursor()
            if self.state.insert_sorted_subtask() is None:
                self._set_message("no row selected")
                return
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

        def action_help_quit(self) -> None:
            self._notify_warning("Press ctrl+q to quit the app")

        def on_input_submitted(self, event: Any) -> None:
            if event.input is self.edit_input:
                if self.prompt_kind is not None:
                    self._submit_prompt()
                else:
                    self._exit_edit_mode(commit=True)

        def on_data_table_row_highlighted(self, event: Any) -> None:
            rows = self.state.rows
            reset_range_anchor = not (
                0 <= event.cursor_row < len(rows)
                and self.state.selected_path == rows[event.cursor_row].path
            )
            self._sync_selection_from_cursor_row(
                event.cursor_row,
                reset_range_anchor=reset_range_anchor,
            )

        def on_mouse_down(self, event: Any) -> None:
            if getattr(event, "button", None) != 3:
                return
            row_index = self._event_table_row_index(event)
            if row_index is None:
                return
            self._handle_row_right_click(row_index, double=self._is_double_right_click(row_index))
            stop = getattr(event, "stop", None)
            if stop is not None:
                stop()

        def _handle_row_right_click(self, row_index: int, *, double: bool) -> None:
            self._sync_selection_from_cursor_row(row_index)
            if double:
                undone_description_toggle = self._undo_prior_right_click_description_toggle()
                if self.state.toggle_selected_group_collapsed():
                    self._refresh_table()
                    self._set_message("group toggled")
                else:
                    if undone_description_toggle:
                        self._refresh_table()
                    self._set_message("selected row is not a group")
            elif self._toggle_selected_description_expanded():
                row = self.state.selected_row
                self._last_right_click_description_toggle_path = row.path if row is not None else None
                self._last_right_click_description_toggle_item_id = id(row.item) if row is not None else None
                self._refresh_table()
                self._set_message("description toggled")
            else:
                self._last_right_click_description_toggle_path = None
                self._last_right_click_description_toggle_item_id = None
                self._set_message("description already fully visible")

        def _is_double_right_click(self, row_index: int) -> bool:
            path = self.state.rows[row_index].path
            now = monotonic()
            double = (
                self._last_right_click_path == path
                and now - self._last_right_click_time <= _RIGHT_CLICK_DOUBLE_CLICK_SECONDS
            )
            self._last_right_click_path = None if double else path
            self._last_right_click_time = 0.0 if double else now
            return double

        def key_escape(self) -> None:
            if self.cheatsheet_visible:
                self._hide_cheatsheet()
            elif self.prompt_kind is not None:
                self._cancel_prompt()
            elif self.editing:
                self._exit_edit_mode(commit=False)
            elif self.state.selected_paths:
                self.state.clear_row_marks()
                self._refresh_table()
                self._set_message("row selection cleared")

        def _show_cheatsheet(self) -> None:
            cheatsheet = self._cheatsheet()
            cheatsheet.update(_cheatsheet_renderable(text))
            overlay = self._cheatsheet_overlay()
            overlay.styles.display = "block"
            self.cheatsheet_visible = True
            self._cheatsheet_panel().focus()

        def _hide_cheatsheet(self) -> None:
            overlay = self._cheatsheet_overlay()
            overlay.styles.display = "none"
            self.cheatsheet_visible = False

        def _start_description_edit(self) -> None:
            row = self.state.selected_row
            if row is None:
                self._set_message("no row selected")
                return
            if row.completed:
                self._set_message("completed rows are read-only")
                return

            description_area = self._description_area()
            description_area.load_text(row.description)
            description_area.styles.display = "block"
            description_area.focus()
            description_area.select_all()
            self.editing = True
            self._set_prompt_message("editing description; alt+enter adds a newline")

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
            self._set_prompt_message(message)

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
                elif self.prompt_kind == "delete-confirm":
                    if parse_confirmation_prompt(edit_input.value, default=False):
                        count = len(self.state.delete_selected_items())
                        message = "row deleted" if count == 1 else f"{count} rows deleted"
                        self._finish_prompt(message)
                    else:
                        self._finish_prompt("delete cancelled")
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
                self._notify_error(str(exc))

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

        def _extend_selection(self, delta: int) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor(reset_range_anchor=False)
            if self.state.extend_selection(delta):
                self._refresh_table()
                self._set_message("row selection extended")
            else:
                self._set_message("selection boundary reached")

        def _adjust_priority_shortcut(self, delta: int) -> None:
            if self.prompt_kind is not None or self.editing:
                return
            self._sync_selection_from_table_cursor()
            changed = self.state.adjust_selected_priority(delta)
            if changed:
                self._refresh_table()
                self._set_message("priority updated")
            else:
                self._set_message("priority unchanged")

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
            self._notify_for_message(message)

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
            self._notify_info("edit cancelled")

        def _exit_edit_mode(self, *, commit: bool) -> None:
            if not self.editing:
                return

            if commit:
                try:
                    changed = self.state.update_selected_description(
                        self._description_area().text
                    )
                except ValueError as exc:
                    self._notify_error(str(exc))
                    return
                if changed:
                    self._refresh_table()
                    self._notify_success("description updated")
                else:
                    self._notify_info("description unchanged")
            else:
                self._notify_info("edit cancelled")

            description_area = self._description_area()
            description_area.styles.display = "none"
            description_area.load_text("")
            self.editing = False
            self._table().focus()

        def _refresh_table(self) -> None:
            self.state.repair_selection()
            _populate_table(
                self._table(),
                self.state,
                text,
                style_cls,
                table_width=self.size.width,
                expanded_description_item_ids=self.expanded_description_item_ids,
            )
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

        def _sync_selection_from_table_cursor(
            self,
            *,
            reset_range_anchor: bool = True,
        ) -> None:
            self._sync_selection_from_cursor_row(
                self._table().cursor_row,
                reset_range_anchor=reset_range_anchor,
            )

        def _sync_selection_from_cursor_row(
            self,
            cursor_row: int,
            *,
            reset_range_anchor: bool = True,
        ) -> None:
            rows = self.state.rows
            if not rows:
                self.state.selected_path = None
                if reset_range_anchor and not self._has_active_range_selection():
                    self.state.range_anchor_path = None
                return
            if 0 <= cursor_row < len(rows):
                self.state.selected_path = rows[cursor_row].path
                if reset_range_anchor and not self._has_active_range_selection():
                    self.state.range_anchor_path = None

        def _has_active_range_selection(self) -> bool:
            return self.state.range_anchor_path is not None and bool(self.state.selected_paths)

        def _event_table_row_index(self, event: Any) -> int | None:
            style = getattr(event, "style", None)
            meta = getattr(style, "meta", None) if style is not None else None
            if not isinstance(meta, dict) or meta.get("out_of_bounds", False):
                return None
            row_index = meta.get("row")
            if not isinstance(row_index, int) or not 0 <= row_index < len(self.state.rows):
                return None
            return row_index

        def _rows_with_hidden_descriptions(self, rows: list[EditorRow]) -> list[EditorRow]:
            all_rows = self.state.rows
            return [
                row
                for row in rows
                if _description_has_hidden_content(row, all_rows, self.size.width)
            ]

        def _toggle_description_rows_expanded(self, rows: list[EditorRow]) -> int:
            changed = 0
            for row in rows:
                if not _description_has_hidden_content(row, self.state.rows, self.size.width):
                    self.expanded_description_item_ids.discard(id(row.item))
                    continue
                item_id = id(row.item)
                if item_id in self.expanded_description_item_ids:
                    self.expanded_description_item_ids.remove(item_id)
                else:
                    self.expanded_description_item_ids.add(item_id)
                changed += 1
            return changed

        def _undo_prior_right_click_description_toggle(self) -> bool:
            row = self.state.selected_row
            if row is None:
                self._last_right_click_description_toggle_path = None
                self._last_right_click_description_toggle_item_id = None
                return False
            if (
                self._last_right_click_description_toggle_path != row.path
                or self._last_right_click_description_toggle_item_id != id(row.item)
            ):
                self._last_right_click_description_toggle_path = None
                self._last_right_click_description_toggle_item_id = None
                return False
            self._last_right_click_description_toggle_path = None
            self._last_right_click_description_toggle_item_id = None
            return bool(self._toggle_selected_description_expanded())

        def _toggle_selected_description_expanded(self) -> bool:
            row = self.state.selected_row
            if row is None:
                return False
            if not _description_has_hidden_content(row, self.state.rows, self.size.width):
                self.expanded_description_item_ids.discard(id(row.item))
                return False
            item_id = id(row.item)
            if item_id in self.expanded_description_item_ids:
                self.expanded_description_item_ids.remove(item_id)
            else:
                self.expanded_description_item_ids.add(item_id)
            return True

        def _refresh_top_bar(self) -> None:
            top_bar = self.top_bar or self.query_one("#top-bar", static)
            self.top_bar = top_bar
            top_bar.update(_top_bar_renderable(self.document, self.state, text))

        def _set_message(self, message: str, severity: NotificationSeverity | None = None) -> None:
            if severity is None:
                self._notify_for_message(message)
            else:
                self._notify(message, severity)

        def _set_prompt_message(self, message: str) -> None:
            message_bar = self.message_bar or self.query_one("#message-bar", static)
            self.message_bar = message_bar
            message_bar.update(message)

        def _clear_prompt_message(self) -> None:
            self._set_prompt_message("")

        def _notify_success(self, message: str) -> None:
            self._notify(message, "success")

        def _notify_info(self, message: str) -> None:
            self._notify(message, "info")

        def _notify_warning(self, message: str) -> None:
            self._notify(message, "warning")

        def _notify_error(self, message: str) -> None:
            self._notify(message, "error")

        def _notify_for_message(self, message: str) -> None:
            lowered = message.casefold()
            if any(token in lowered for token in ("error", "failed", "must", "invalid")):
                self._notify_error(message)
            elif any(
                token in lowered
                for token in (
                    "no row",
                    "read-only",
                    "only available",
                    "not started",
                    "already",
                    "cannot",
                    "boundary",
                )
            ):
                self._notify_warning(message)
            elif any(
                token in lowered
                for token in (
                    "updated",
                    "saved",
                    "deleted",
                    "moved",
                    "grouped",
                    "converted",
                    "toggled",
                    "indented",
                    "outdented",
                    "hidden",
                    "visible",
                    "expanded",
                    "collapsed",
                )
            ):
                self._notify_success(message)
            else:
                self._notify_info(message)

        def _notify(self, message: str, severity: NotificationSeverity) -> None:
            if self.prompt_kind is None and not self.editing:
                self._clear_prompt_message()
            notification = _Notification(self.next_notification_id, message, severity)
            self.next_notification_id += 1
            if len(self.visible_notifications) >= TUI_NOTIFICATION_MAX_VISIBLE:
                self.visible_notifications.pop(0)
            self._show_notification(notification)
            self._refresh_notifications()

        def _show_notification(self, notification: _Notification) -> None:
            self.visible_notifications.append(notification)
            try:
                import asyncio

                asyncio.get_running_loop()
            except RuntimeError:
                return
            self.set_timer(
                _notification_timeout(notification.severity),
                lambda: self._dismiss_notification(notification.id),
            )

        def _dismiss_notification(self, notification_id: int) -> None:
            before = len(self.visible_notifications)
            self.visible_notifications = [
                notification
                for notification in self.visible_notifications
                if notification.id != notification_id
            ]
            if len(self.visible_notifications) == before:
                return
            self._refresh_notifications()

        def _refresh_notifications(self) -> None:
            for index, slot in enumerate(self._notification_slots()):
                if index >= len(self.visible_notifications):
                    slot.styles.display = "none"
                    slot.update("")
                    continue
                notification = self.visible_notifications[index]
                slot.styles.display = "block"
                slot.styles.width = _notification_width()
                slot.styles.height = _notification_height()
                slot.styles.offset = (_notification_offset_x(self.size.width), _notification_offset_y(index))
                slot.update(_notification_renderable(text, notification))

        def _table(self) -> Any:
            if self.table is None:
                self.table = self.query_one("#roadmap-grid", data_table)
            return self.table

        def _notification_slots(self) -> list[Any]:
            if not self.notification_slots:
                self.notification_slots = [
                    self.query_one(f"#notification-{index}", static)
                    for index in range(TUI_NOTIFICATION_MAX_VISIBLE)
                ]
            return self.notification_slots

        def _edit_input(self) -> Any:
            if self.edit_input is None:
                self.edit_input = self.query_one("#description-edit", input_widget)
            return self.edit_input

        def _description_area(self) -> Any:
            if self.description_area is None:
                self.description_area = self.query_one("#description-area", text_area_widget)
            return self.description_area

        def _cheatsheet(self) -> Any:
            if self.cheatsheet is None:
                self.cheatsheet = self.query_one("#cheatsheet", static)
            return self.cheatsheet

        def _cheatsheet_overlay(self) -> Any:
            if self.cheatsheet_overlay is None:
                self.cheatsheet_overlay = self.query_one("#cheatsheet-overlay", center_middle)
            return self.cheatsheet_overlay

        def _cheatsheet_panel(self) -> Any:
            if self.cheatsheet_panel is None:
                self.cheatsheet_panel = self.query_one("#cheatsheet-panel", vertical_scroll)
            return self.cheatsheet_panel

    return RoadmapEditorApp(document)


_CHEATSHEET_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Navigation",
        (
            ("F1", "toggle this cheatsheet"),
            ("Esc", "close cheatsheet, cancel edit, or clear marks"),
            ("Up / Down", "move one row"),
            ("Shift+Up / Shift+Down", "extend row selection"),
            ("Space", "mark or unmark focused row"),
            ("Enter", "edit focused description"),
            ("C", "copy focused or marked descriptions"),
            ("Ctrl+H", "toggle completed rows"),
        ),
    ),
    (
        "Roadmap",
        (
            ("O", "insert sorted sibling"),
            ("U", "insert unsorted sibling"),
            ("Ctrl+U", "insert unsorted subtask"),
            ("Ctrl+O", "insert sorted subtask"),
            ("Ctrl+G", "group marked rows or convert task"),
            ("Ctrl+T", "toggle focused group"),
            ("Ctrl+Shift+T", "expand or collapse visible groups"),
            ("Ctrl+D", "toggle focused or marked descriptions"),
            ("Ctrl+Shift+D", "expand or collapse long descriptions"),
            ("Delete", "delete selected rows after confirmation"),
            ("Ctrl+S", "save roadmap"),
            ("Q / Ctrl+Q", "Exit"),
        ),
    ),
    (
        "Metadata",
        (
            ("M", "edit milestone"),
            ("P", "edit priority or optionality"),
            ("E", "edit explicit completion"),
            ("Ctrl+Space", "cycle status"),
        ),
    ),
    (
        "Priority",
        (
            ("Alt+Up / Alt+Down", "adjust priority by one"),
            ("Alt+Shift+Up / Alt+Shift+Down", "adjust priority by ten"),
        ),
    ),
    (
        "Completion",
        (
            ("+ / -", "adjust completion by one"),
            ("] / [", "adjust completion by ten"),
        ),
    ),
    (
        "Sorting",
        (
            ("Ctrl+K / Ctrl+J", "move row up or down"),
            ("> / <", "indent or outdent row"),
        ),
    ),
    (
        "Mouse",
        (
            ("Double click", "edit row description"),
            ("Right click", "toggle long description"),
            ("Double right click", "toggle focused group"),
        ),
    ),
)


def _cheatsheet_renderable(text: Any) -> Any:
    cheatsheet = text()
    cheatsheet.append("Roadmap Editor Shortcuts\n", style="bold cyan")
    cheatsheet.append("F1 or Esc closes this panel.\n")
    for group, shortcuts in _CHEATSHEET_GROUPS:
        cheatsheet.append(f"\n{group}\n", style="bold magenta")
        for key, description in shortcuts:
            cheatsheet.append(f"  {key:<30}", style="bold yellow")
            cheatsheet.append(f"{description}\n")
    return cheatsheet


def _notification_renderable(text: Any, notification: _Notification) -> Any:
    renderable = text()
    border_style = f"bold {_notification_color(notification.severity)}"
    lines = _notification_display_lines(notification.message)
    for index, line in enumerate(lines):
        renderable.append("│", style=border_style)
        renderable.append(f" {line} ")
        renderable.append("│", style=border_style)
        if index < len(lines) - 1:
            renderable.append("\n")
    return renderable


def _notification_display_lines(message: str) -> list[str]:
    message_width = _notification_message_width()
    max_lines = _notification_height()
    lines = textwrap.wrap(
        message,
        width=message_width,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize_notification_line(lines[-1], message_width)
    padded = [line.ljust(message_width) for line in lines]
    padded.extend(" " * message_width for _line in range(max_lines - len(padded)))
    return padded


def _ellipsize_notification_line(line: str, width: int) -> str:
    if width <= 3:
        return "." * width
    return f"{line[: width - 3]}..."


def _notification_color(severity: NotificationSeverity) -> str:
    if severity == "success":
        return "green"
    if severity == "warning":
        return "yellow"
    if severity == "error":
        return "red"
    return "cyan"


def _notification_timeout(severity: NotificationSeverity) -> float:
    if severity == "success":
        return TUI_NOTIFICATION_SUCCESS_TIMEOUT_SECONDS
    if severity == "warning":
        return TUI_NOTIFICATION_WARNING_TIMEOUT_SECONDS
    if severity == "error":
        return TUI_NOTIFICATION_ERROR_TIMEOUT_SECONDS
    return TUI_NOTIFICATION_INFO_TIMEOUT_SECONDS


def _notification_offset_x(width: int) -> int:
    return max(0, width - (_notification_width() + 2))


def _notification_offset_y(index: int) -> int:
    return 1 + index * (_notification_height() + 1)


def _notification_width() -> int:
    return max(TUI_NOTIFICATION_WIDTH, 4)


def _notification_height() -> int:
    return max(TUI_NOTIFICATION_MAX_LINES, 1)


def _notification_message_width() -> int:
    return max(_notification_width() - 4, 1)


def _top_bar_text(document: Document, state: EditorState) -> str:
    directory_text, name_text = _top_bar_path_parts(document)
    dirty_text = "  [UNSAVED]" if state.dirty else ""
    return f"PATH {directory_text}{name_text}  FORMAT {document.format}{dirty_text}"


def _top_bar_renderable(document: Document, state: EditorState, text: Any) -> Any:
    directory_text, name_text = _top_bar_path_parts(document)
    bar = text()
    bar.append("PATH ", style="bold cyan")
    bar.append(directory_text, style="dim white")
    bar.append(name_text, style="white")
    bar.append("  FORMAT ", style="bold cyan")
    bar.append(document.format, style="magenta")
    if state.dirty:
        bar.append("  [UNSAVED]", style="bold orange1")
    return bar


def _top_bar_path_parts(document: Document) -> tuple[str, str]:
    if document.path is None:
        return f"{Path.cwd()}/", "<UNNAMED>"

    path = document.path.expanduser()
    absolute_path = path if path.is_absolute() else Path.cwd() / path
    return f"{absolute_path.parent}/", absolute_path.name


def _populate_table(
    table: Any,
    state: EditorState,
    text: Any,
    style_cls: Any,
    *,
    table_width: int = 80,
    expanded_description_item_ids: set[int] | None = None,
) -> None:
    table.clear(columns=True)
    table.add_columns("Completion", "Priority", "Milestone", "Order", "Description")
    rows = state.rows
    expanded_ids = expanded_description_item_ids or set()
    description_width = _description_width(table_width)
    for row in rows:
        description_text, row_height = _display_description(
            row,
            rows,
            description_width,
            expanded_ids,
        )
        table.add_row(
            _styled_text(row.completion_text, row, text, style_cls, cell="completion", cell_index=0),
            _styled_text(row.priority_text, row, text, style_cls, cell="priority", cell_index=1),
            _styled_text(row.milestone_text, row, text, style_cls, cell="milestone", cell_index=2),
            _styled_text(row.order_text, row, text, style_cls, cell="order", cell_index=3),
            _styled_text(
                description_text,
                row,
                text,
                style_cls,
                cell="description",
                cell_index=4,
            ),
            key=str(row.path),
            height=row_height,
        )


def _description_width(table_width: int) -> int:
    return max(int(table_width) - _FIXED_TABLE_WIDTH, _MIN_DESCRIPTION_WIDTH)


def _display_description(
    row: EditorRow,
    rows: list[EditorRow],
    width: int,
    expanded_description_item_ids: set[int],
) -> tuple[str, int]:
    lines, continuation_prefix = _wrapped_tree_description(row, rows, width)
    minimum_height = max(TUI_TABLE_ROW_HEIGHT, 1)
    if id(row.item) in expanded_description_item_ids:
        visible_lines = lines
    else:
        visible_lines = lines[:minimum_height]
    visible_lines = [*visible_lines, *([continuation_prefix] * (minimum_height - len(visible_lines)))]
    return "\n".join(visible_lines), max(minimum_height, len(visible_lines))


def _description_has_hidden_content(
    row: EditorRow,
    rows: list[EditorRow],
    table_width: int,
) -> bool:
    lines, _continuation_prefix = _wrapped_tree_description(row, rows, _description_width(table_width))
    return len(lines) > max(TUI_TABLE_ROW_HEIGHT, 1)


def _wrapped_tree_description(
    row: EditorRow,
    rows: list[EditorRow],
    width: int,
) -> tuple[list[str], str]:
    sibling_indexes = _visible_sibling_indexes(rows)
    parent_paths = _visible_parent_paths(rows)
    first_prefix, continuation_prefix, description = _tree_description_parts(row, sibling_indexes, parent_paths)
    wrapped: list[str] = []
    for line_index, line in enumerate(description.splitlines() or [""]):
        prefix = first_prefix if line_index == 0 else continuation_prefix
        wrapped.extend(_wrapped_description_line(line, prefix, continuation_prefix, width))
    return wrapped, continuation_prefix


def _wrapped_description_line(
    line: str,
    first_prefix: str,
    continuation_prefix: str,
    width: int,
) -> list[str]:
    first_width = max(width - len(first_prefix), 1)
    chunks = textwrap.wrap(
        line,
        width=first_width,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    wrapped = [f"{first_prefix}{chunks[0]}"]
    continuation_width = max(width - len(continuation_prefix), 1)
    for chunk in chunks[1:]:
        continuation_chunks = textwrap.wrap(
            chunk,
            width=continuation_width,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        wrapped.extend(f"{continuation_prefix}{continuation_chunk}" for continuation_chunk in continuation_chunks)
    return wrapped


def _styled_text(
    value: str,
    row: EditorRow,
    text: Any,
    style_cls: Any,
    *,
    cell: str,
    cell_index: int,
) -> Any:
    if _uses_gradient_style(row):
        return _foreground_gradient_text(value, row, text, style_cls, cell_index)
    style = _priority_style(row) if _uses_priority_style(cell, row) else _row_style(row)
    if row.selected:
        style = f"{style} reverse".strip()
    return text(value, style=style)


def _foreground_gradient_text(
    value: str,
    row: EditorRow,
    text: Any,
    style_cls: Any,
    cell_index: int,
) -> Any:
    rendered = text(value, style="reverse" if row.selected else "")
    if not value:
        return rendered

    colors = _priority_gradient_cell_colors(row, cell_index)
    denominator = max(len(value) - 1, 1)
    for index, _character in enumerate(value):
        color = _gradient_color_at(colors, index / denominator)
        rendered.stylize(style_cls(color=color), index, index + 1)
    return rendered


def _uses_priority_style(cell: str, row: EditorRow) -> bool:
    if row.completed:
        return False
    return cell in {"priority", "milestone", "order", "description"} and row.item.optional


def _uses_gradient_style(row: EditorRow) -> bool:
    return not row.completed and not row.item.optional and row.item.priority > 0


def _row_style(row: EditorRow) -> str:
    if row.status == COMPLETED:
        return "dim"
    if row.status == ONGOING:
        return "yellow"
    return ""


def _priority_style(row: EditorRow) -> str:
    if row.item.optional:
        return "cyan"
    if row.item.priority >= 667:
        return "red"
    if row.item.priority >= 334:
        return "yellow"
    if row.item.priority > 0:
        return "green"
    return _row_style(row)


def _priority_gradient_colors(row: EditorRow) -> list[str]:
    from roadmaps.constants import MAX_PRIORITY

    ratio = max(0.0, min(float(row.item.priority), float(MAX_PRIORITY))) / float(MAX_PRIORITY)
    if ratio <= 0.5:
        return [_PRIORITY_GRADIENT_LOW, _interpolate_hex(_PRIORITY_GRADIENT_LOW, _PRIORITY_GRADIENT_MID, ratio * 2.0)]
    return [
        _PRIORITY_GRADIENT_LOW,
        _PRIORITY_GRADIENT_MID,
        _interpolate_hex(_PRIORITY_GRADIENT_MID, _PRIORITY_GRADIENT_HIGH, (ratio - 0.5) * 2.0),
    ]


def _priority_gradient_cell_colors(row: EditorRow, cell_index: int) -> list[str]:
    start = cell_index / _TABLE_CELL_COUNT
    end = (cell_index + 1) / _TABLE_CELL_COUNT
    row_colors = _priority_gradient_colors(row)
    return [
        _gradient_color_at(row_colors, start),
        _gradient_color_at(row_colors, end),
    ]


def _gradient_color_at(colors: list[str], position: float) -> str:
    if len(colors) == 1:
        return colors[0]
    position = max(0.0, min(position, 1.0))
    scaled = position * (len(colors) - 1)
    index = min(int(scaled), len(colors) - 2)
    return _interpolate_hex(colors[index], colors[index + 1], scaled - index)


def _interpolate_hex(start: str, end: str, ratio: float) -> str:
    ratio = max(0.0, min(ratio, 1.0))
    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    channels = [round(start_channel + (end_channel - start_channel) * ratio) for start_channel, end_channel in zip(start_rgb, end_rgb, strict=True)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text_value = value.removeprefix("#")
    return (int(text_value[0:2], 16), int(text_value[2:4], 16), int(text_value[4:6], 16))


def _tree_description(row: EditorRow, rows: list[EditorRow] | None = None) -> str:
    if rows is None:
        if row.depth == 0:
            return row.description
        guide = "  " * (row.depth - 1)
        return f"{guide}└─ {row.description}"
    return _tree_descriptions(rows)[row.path]


def _tree_descriptions(rows: list[EditorRow]) -> dict[tuple[int, ...], str]:
    sibling_indexes = _visible_sibling_indexes(rows)
    parent_paths = _visible_parent_paths(rows)
    return {row.path: _tree_description_for_row(row, sibling_indexes, parent_paths) for row in rows}


def _tree_description_for_row(
    row: EditorRow,
    sibling_indexes: dict[tuple[int, ...], list[int]],
    parent_paths: set[tuple[int, ...]],
) -> str:
    first_prefix, _continuation_prefix, description = _tree_description_parts(row, sibling_indexes, parent_paths)
    return f"{first_prefix}{description}"


def _tree_description_parts(
    row: EditorRow,
    sibling_indexes: dict[tuple[int, ...], list[int]],
    parent_paths: set[tuple[int, ...]],
) -> tuple[str, str, str]:
    marker = "* " if row.selected else ""
    collapsed = "▸ " if row.collapsed else ""
    marker_padding = " " * len(marker + collapsed)
    has_visible_child = row.path in parent_paths
    if row.depth == 0:
        has_later_sibling = _has_later_sibling(sibling_indexes, (), row.path[0])
        continuation_prefix = "│  " if has_later_sibling else "   " if has_visible_child else ""
        if has_visible_child:
            continuation_prefix += "│  "
        return marker + collapsed, continuation_prefix + marker_padding, row.description

    prefix = ""
    for depth in range(row.depth):
        ancestor_parent = row.path[:depth]
        ancestor_index = row.path[depth]
        if _has_later_sibling(sibling_indexes, ancestor_parent, ancestor_index):
            prefix += "│  "
        else:
            prefix += "   "

    parent_path = row.path[:-1]
    has_later_sibling = _has_later_sibling(sibling_indexes, parent_path, row.path[-1])
    branch = "├─ " if has_later_sibling else "└─ "
    continuation_branch = "│  " if has_later_sibling else "   "
    if has_visible_child:
        continuation_branch += "│  "
    return (
        f"{prefix}{branch}{marker}{collapsed}",
        f"{prefix}{continuation_branch}{marker_padding}",
        row.description,
    )


def _visible_sibling_indexes(rows: list[EditorRow]) -> dict[tuple[int, ...], list[int]]:
    indexes: dict[tuple[int, ...], list[int]] = {}
    for row in rows:
        indexes.setdefault(row.path[:-1], []).append(row.path[-1])
    return indexes


def _visible_parent_paths(rows: list[EditorRow]) -> set[tuple[int, ...]]:
    return {row.path[:-1] for row in rows if row.path}


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
