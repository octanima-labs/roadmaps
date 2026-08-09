import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.text import Text

from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    MAX_PRIORITY,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    UNSORTED,
    Roadmap,
    Task,
    TaskGroup,
)
from roadmaps._documents import Document, load_document
from roadmaps.editor import (
    _cheatsheet_renderable,
    _notification_display_lines,
    _notification_offset_x,
    _notification_offset_y,
    _priority_gradient_cell_colors,
    _priority_gradient_colors,
    _top_bar_renderable,
    _top_bar_text,
    _tree_description,
    _tree_descriptions,
    create_editor_app,
    parse_exit_save_prompt,
    parse_save_failure_prompt,
    parse_save_format_prompt,
)


class FakeTable:
    def __init__(self) -> None:
        self.columns: list[str] = []
        self.rows: list[tuple[object, ...]] = []
        self.row_heights: list[int | None] = []
        self.cursor_row = 0
        self.hover_row: int | None = None
        self.focused = False

    def clear(self, *, columns: bool = False) -> None:
        self.rows = []
        self.row_heights = []
        if columns:
            self.columns = []

    def add_columns(self, *columns: str) -> None:
        self.columns.extend(columns)

    def add_row(self, *cells: object, key: str, height: int | None = None) -> None:
        self.rows.append(cells)
        self.row_heights.append(height)

    def move_cursor(self, *, row: int, animate: bool = False) -> None:
        self.cursor_row = row

    def focus(self) -> None:
        self.focused = True


class FakeStatic:
    def __init__(self) -> None:
        self.value: object = ""
        self.styles = SimpleNamespace(display="none")
        self.focused = False

    def update(self, value: object) -> None:
        self.value = value

    def focus(self) -> None:
        self.focused = True


class FakeInput:
    def __init__(self) -> None:
        self.value = ""
        self.styles = SimpleNamespace(display="none")
        self.focused = False

    def focus(self) -> None:
        self.focused = True


class FakeTextArea:
    def __init__(self) -> None:
        self.text = ""
        self.styles = SimpleNamespace(display="none")
        self.focused = False

    def load_text(self, value: str) -> None:
        self.text = value

    def insert(self, value: str) -> None:
        self.text += value

    def focus(self) -> None:
        self.focused = True


def _wire_fake_widgets(app: Any) -> None:
    app.table = FakeTable()
    app.top_bar = FakeStatic()
    app.edit_input = FakeInput()
    app.description_area = FakeTextArea()
    app.message_bar = FakeStatic()
    app.notification_slots = [FakeStatic() for _ in range(3)]
    app.cheatsheet = FakeStatic()
    app.cheatsheet_panel = FakeStatic()
    app.cheatsheet_overlay = FakeStatic()


def _toast_text(app: Any) -> str:
    values = []
    for slot in app.notification_slots:
        value = slot.value
        plain = value.plain if hasattr(value, "plain") else str(value)
        if plain:
            lines = plain.splitlines()
            if lines and all(line.startswith("│ ") and line.endswith(" │") for line in lines):
                values.append(" ".join(line[2:-2].strip() for line in lines if line[2:-2].strip()))
            else:
                values.append(plain)
    return "\n".join(values)


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

    assert _top_bar_text(app.document, app.state) == "PATH <UNNAMED>  FORMAT yaml"
    clean_renderable = _top_bar_renderable(app.document, app.state, Text)
    assert clean_renderable.plain == "PATH <UNNAMED>  FORMAT yaml"
    assert "UNSAVED" not in clean_renderable.plain

    app.state.dirty = True

    assert _top_bar_text(app.document, app.state) == "PATH <UNNAMED>  FORMAT yaml  [UNSAVED]"
    renderable = _top_bar_renderable(app.document, app.state, Text)
    assert renderable.plain == "PATH <UNNAMED>  FORMAT yaml  [UNSAVED]"
    assert renderable.spans
    assert any("orange" in str(span.style) for span in renderable.spans)


def test_tree_description_uses_visible_tree_guides() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup(
                        "first",
                        tasks=[
                            Task("first child"),
                            TaskGroup("second child", tasks=[Task("grandchild")]),
                        ],
                    ),
                    TaskGroup("second", tasks=[Task("last child")]),
                ]
            ),
            "text",
        )
    )
    descriptions = _tree_descriptions(app.state.rows)

    assert _tree_description(app.state.rows[0]) == "first"
    assert descriptions[(0,)] == "first"
    assert descriptions[(0, 0)] == "│  ├─ first child"
    assert descriptions[(0, 1)] == "│  └─ second child"
    assert descriptions[(0, 1, 0)] == "│     └─ grandchild"
    assert descriptions[(1, 0)] == "   └─ last child"


def test_tree_description_ignores_hidden_completed_rows() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup(
                        "group",
                        tasks=[
                            Task("visible"),
                            Task("done", status=COMPLETED),
                        ],
                    )
                ]
            ),
            "text",
        )
    )
    app.state.hide_completed = True

    assert _tree_descriptions(app.state.rows)[(0, 0)] == "   └─ visible"


def test_tree_description_marks_selected_and_collapsed_rows() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("group", tasks=[Task("child")])]), "text")
    )
    app.state.selected_paths = {(0,)}
    app.state.toggle_selected_group_collapsed()

    assert _tree_descriptions(app.state.rows)[(0,)] == "* ▸ group"


def test_editor_table_uses_visual_polish_columns_and_selected_style() -> None:
    app = create_editor_app(Document(Roadmap([Task("first", order=1)]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_toggle_row_mark()

    assert app.table.columns == ["Completion", "Priority", "Milestone", "Order", "Description"]
    assert app.table.row_heights == [2]
    assert app.table.rows[0][3].plain == "1"
    assert app.table.rows[0][4].plain == "* first\n  "
    assert "reverse" in str(app.table.rows[0][4].style)


def test_editor_multiline_descriptions_default_to_two_visible_rows() -> None:
    app = create_editor_app(Document(Roadmap([Task("one\ntwo\nthree")]), "text"))
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[0][4].plain == "one\ntwo"
    assert app.table.row_heights == [2]


def test_editor_expands_hidden_description_with_description_right_click() -> None:
    app = create_editor_app(Document(Roadmap([Task("one\ntwo\nthree")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    stopped: list[bool] = []
    app.on_mouse_down(
        SimpleNamespace(
            button=3,
            style=SimpleNamespace(meta={"row": 0, "column": 4}),
            stop=lambda: stopped.append(True),
        )
    )

    assert app.table.rows[0][4].plain == "one\ntwo\nthree"
    assert app.table.row_heights == [3]
    assert "description toggled" in _toast_text(app)
    assert stopped == [True]

    app.on_mouse_down(
        SimpleNamespace(
            button=3,
            style=SimpleNamespace(meta={"row": 0, "column": 4}),
            stop=lambda: stopped.append(True),
        )
    )

    assert app.table.rows[0][4].plain == "one\ntwo"
    assert app.table.row_heights == [2]


def test_editor_wraps_long_descriptions_instead_of_rendering_horizontally() -> None:
    app = create_editor_app(Document(Roadmap([Task("x" * 80)]), "text"))
    _wire_fake_widgets(app)

    app._refresh_table()

    lines = app.table.rows[0][4].plain.splitlines()
    assert len(lines) == 2
    assert all(len(line) <= 34 for line in lines)
    assert app.table.row_heights == [2]


def test_editor_wrapped_child_description_continues_tree_guides() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup(
                        "group",
                        tasks=[Task("alpha " * 20), Task("sibling")],
                    ),
                    Task("later"),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    lines = app.table.rows[1][4].plain.splitlines()
    assert lines[0].startswith("│  ├─ alpha")
    assert lines[1].startswith("│  │  alpha")


def test_editor_wrapped_last_child_description_uses_spaced_continuation() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup(
                        "group",
                        tasks=[Task("sibling"), Task("alpha " * 20)],
                    ),
                    Task("later"),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    lines = app.table.rows[2][4].plain.splitlines()
    assert lines[0].startswith("│  └─ alpha")
    assert lines[1].startswith("│     alpha")


def test_editor_wrapped_parent_description_continues_to_later_sibling_and_child() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup("alpha " * 20, tasks=[Task("child")]),
                    Task("later"),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    lines = app.table.rows[0][4].plain.splitlines()
    assert lines[0].startswith("alpha")
    assert lines[1].startswith("│  │  alpha")


def test_editor_one_line_child_description_continues_tree_guides() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup("group", tasks=[Task("child"), Task("sibling")]),
                    Task("later"),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[1][4].plain == "│  ├─ child\n│  │  "
    assert app.table.row_heights[1] == 2


def test_editor_one_line_last_child_description_uses_spaced_continuation() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup("group", tasks=[Task("sibling"), Task("child")]),
                    Task("later"),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[2][4].plain == "│  └─ child\n│     "
    assert app.table.row_heights[2] == 2


def test_editor_one_line_parent_description_continues_to_visible_child() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("parent", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[0][4].plain == "parent\n   │  "
    assert app.table.row_heights[0] == 2


def test_editor_last_root_child_description_is_padded_from_root_siblings() -> None:
    app = create_editor_app(
        Document(Roadmap([Task("first"), TaskGroup("parent", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[2][4].plain == "   └─ child\n      "
    assert app.table.row_heights[2] == 2


def test_editor_one_line_parent_description_continues_to_later_sibling_and_child() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("parent", tasks=[Task("child")]), Task("later")]), "text")
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[0][4].plain == "parent\n│  │  "
    assert app.table.row_heights[0] == 2


def test_editor_multiline_parent_description_continues_to_later_sibling_and_child() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("one\ntwo\nthree", tasks=[Task("child")]), Task("later")]), "text")
    )
    _wire_fake_widgets(app)
    app.expanded_description_item_ids.add(id(app.state.rows[0].item))

    app._refresh_table()

    assert app.table.rows[0][4].plain == "one\n│  │  two\n│  │  three"
    assert app.table.row_heights[0] == 3


def test_editor_one_line_nested_parent_description_continues_to_visible_child() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    TaskGroup(
                        "outer",
                        tasks=[TaskGroup("parent", tasks=[Task("child")])],
                    ),
                    Task("later"),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)

    app._refresh_table()

    assert app.table.rows[1][4].plain == "│  └─ parent\n│     │  "
    assert app.table.row_heights[1] == 2


def test_editor_collapsed_parent_description_does_not_continue_to_hidden_child() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("parent", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)
    app.state.toggle_selected_group_collapsed()

    app._refresh_table()

    assert app.table.rows[0][4].plain == "▸ parent\n  "
    assert app.table.row_heights[0] == 2


def test_editor_table_styles_priority_and_completed_rows() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    Task("low", priority=1),
                    Task("mid", priority=500),
                    Task("high", priority=MAX_PRIORITY),
                    Task("optional", optional=True),
                    Task("done", status=COMPLETED),
                    Task("optional done", optional=True, status=COMPLETED),
                ]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    assert all(isinstance(app.table.rows[0][index], Text) for index in range(5))
    assert all(isinstance(app.table.rows[1][index], Text) for index in range(5))
    assert all(isinstance(app.table.rows[2][index], Text) for index in range(5))
    assert app.table.rows[2][0].spans
    assert all(span.style.color is not None for span in app.table.rows[2][0].spans)
    assert all(span.style.bgcolor is None for span in app.table.rows[2][0].spans)
    assert _priority_gradient_colors(app.state.rows[0]) == ["#22c55e", "#22c55e"]
    assert _priority_gradient_colors(app.state.rows[2]) == ["#22c55e", "#facc15", "#ef4444"]
    assert _priority_gradient_cell_colors(app.state.rows[2], 0)[0] == "#22c55e"
    assert _priority_gradient_cell_colors(app.state.rows[2], 4)[1] == "#ef4444"
    assert _priority_gradient_cell_colors(app.state.rows[2], 0) != _priority_gradient_cell_colors(app.state.rows[2], 4)
    assert "cyan" in str(app.table.rows[3][1].style)
    assert app.table.rows[5][1].plain == "?"
    assert all("dim" in str(app.table.rows[5][index].style) for index in range(1, 5))
    assert all("cyan" not in str(app.table.rows[5][index].style) for index in range(1, 5))
    assert app.table.rows[4][1].spans == []

    app.state.selected_paths = {(4,)}
    app._refresh_table()
    completed_style = str(app.table.rows[4][4].style)
    assert "dim" in completed_style
    assert "reverse" in completed_style


def test_save_prompt_parsers_accept_defaults_and_choices() -> None:
    assert parse_save_format_prompt("") == "yaml"
    assert parse_save_format_prompt("JSON") == "json"
    assert parse_exit_save_prompt("") == "save"
    assert parse_exit_save_prompt("n") == "discard"
    assert parse_exit_save_prompt("cancel") == "cancel"
    assert parse_save_failure_prompt("r") == "retry"
    assert parse_save_failure_prompt("change") == "change"
    assert parse_save_failure_prompt("D") == "discard"

    with pytest.raises(ValueError, match="format"):
        parse_save_format_prompt("xml")
    with pytest.raises(ValueError, match="yes"):
        parse_exit_save_prompt("maybe")
    with pytest.raises(ValueError, match="retry"):
        parse_save_failure_prompt("")


def test_cheatsheet_renderable_lists_all_shortcut_groups() -> None:
    renderable = _cheatsheet_renderable(Text)

    assert "Roadmap Editor Shortcuts" in renderable.plain
    assert "Navigation" in renderable.plain
    assert "Roadmap" in renderable.plain
    assert "Metadata" in renderable.plain
    assert "Priority" in renderable.plain
    assert "Completion" in renderable.plain
    assert "Sorting" in renderable.plain
    assert "Mouse" in renderable.plain
    assert "F1" in renderable.plain
    assert "Ctrl+S" in renderable.plain
    assert "Delete" in renderable.plain


def test_editor_f1_toggles_centered_cheatsheet() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)

    app.action_toggle_cheatsheet()

    assert app.cheatsheet_visible is True
    assert app.cheatsheet_overlay.styles.display == "block"
    assert app.cheatsheet_panel.focused is True
    assert "Roadmap Editor Shortcuts" in app.cheatsheet.value.plain

    app.action_toggle_cheatsheet()

    assert app.cheatsheet_visible is False
    assert app.cheatsheet_overlay.styles.display == "none"


def test_editor_escape_closes_cheatsheet_before_active_prompt() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app.action_edit_priority()
    app.edit_input.value = "^10"

    app.action_toggle_cheatsheet()
    app.key_escape()

    assert app.cheatsheet_visible is False
    assert app.prompt_kind == "priority"
    assert app.edit_input.value == "^10"
    assert app.edit_input.styles.display == "block"


def test_editor_cheatsheet_opens_read_only_over_description_edit() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_edit_description()
    app.description_area.text = "draft"

    app.action_toggle_cheatsheet()

    assert app.cheatsheet_visible is True
    assert app.editing is True
    assert app.description_area.text == "draft"


def test_editor_notifications_render_severity_colors_and_clear_idle_bar() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app.message_bar.update("old")

    app._notify_success("saved")
    app._notify_info("info")
    app._notify_warning("careful")

    assert app.message_bar.value == ""
    assert all(slot.styles.display == "block" for slot in app.notification_slots)
    assert [slot.value.plain for slot in app.notification_slots] == [
        (
            "│ saved                        │\n"
            "│                              │"
        ),
        (
            "│ info                         │\n"
            "│                              │"
        ),
        (
            "│ careful                      │\n"
            "│                              │"
        ),
    ]
    assert all(slot.value.plain.count("\n") == 1 for slot in app.notification_slots)
    spans = [span for slot in app.notification_slots for span in slot.value.spans]
    styles = [str(span.style) for span in spans]
    assert any("green" in style for style in styles)
    assert any("cyan" in style for style in styles)
    assert any("yellow" in style for style in styles)
    message_spans = [span for span in spans if span.end - span.start > 1]
    assert all(str(span.style) == "none" for span in message_spans)


def test_notification_rendered_slots_have_fixed_width_and_height() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)

    app._notify_info("saved")

    assert app.notification_slots[0].styles.width == 32
    assert app.notification_slots[0].styles.height == 2
    assert app.notification_slots[0].styles.offset == (_notification_offset_x(app.size.width), 1)
    assert app.notification_slots[0].value.plain == (
        "│ saved                        │\n"
        "│                              │"
    )


def test_notification_offset_positions_stack_top_right_without_fullscreen_overlay() -> None:
    assert _notification_offset_x(100) == 66
    assert _notification_offset_x(30) == 0
    assert [_notification_offset_y(index) for index in range(3)] == [1, 4, 7]


def test_notification_display_lines_pad_and_wrap_long_messages() -> None:
    assert _notification_display_lines("saved") == [
        "saved" + " " * 23,
        " " * 28,
    ]
    assert _notification_display_lines("x" * 80) == [
        "x" * 28,
        "x" * 25 + "...",
    ]


def test_editor_notifications_replace_oldest_after_three_visible() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)

    app._notify_info("one")
    app._notify_info("two")
    app._notify_info("three")
    app._notify_info("four")

    assert [notification.message for notification in app.visible_notifications] == [
        "two",
        "three",
        "four",
    ]
    assert _toast_text(app) == "two\nthree\nfour"


def test_editor_prompt_validation_error_uses_toast_and_keeps_prompt_active() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_priority()
    app.edit_input.value = "high"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.prompt_kind == "priority"
    assert app.edit_input.styles.display == "block"
    assert app.message_bar.value == "priority: enter !, ?, ^N, N, or empty to clear"
    assert "priority" in _toast_text(app)
    assert any(
        "red" in str(span.style) and span.end - span.start == 1
        for span in app.notification_slots[0].value.spans
    )


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
    assert "completed rows hidden" in _toast_text(app)


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
    assert app.description_area.text == "New task"
    assert app.description_area.styles.display == "block"


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


def test_editor_insert_subtask_enters_description_edit_mode() -> None:
    app = create_editor_app(Document(Roadmap([Task("parent")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_insert_sorted_subtask()

    group = app.document.roadmap.steps[0]
    assert isinstance(group, TaskGroup)
    assert [task.description for task in group.tasks] == ["New task"]
    assert [task.order for task in group.tasks] == [1]
    assert app.state.selected_path == (0, 0)
    assert app.editing is True
    assert app.description_area.text == "New task"
    assert app.description_area.styles.display == "block"


def test_editor_insert_subtask_uses_visual_table_cursor_when_state_is_stale() -> None:
    group = TaskGroup("second", tasks=[Task("child")])
    app = create_editor_app(Document(Roadmap([Task("first"), group]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.table.cursor_row = 1
    app.state.selected_path = (0,)

    app.action_insert_unsorted_subtask()

    assert isinstance(app.document.roadmap.steps[0], Task)
    assert [task.description for task in group.tasks] == ["child", "New task"]
    assert [task.order for task in group.tasks] == [UNSORTED, UNSORTED]
    assert app.state.selected_path == (1, 1)
    assert app.editing is True


def test_editor_description_edit_commit_and_cancel() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_description()
    app.description_area.text = "updated"
    app._exit_edit_mode(commit=True)

    assert app.document.roadmap.steps[0].description == "updated"
    assert app.state.dirty is True
    assert app.editing is False
    assert app.description_area.styles.display == "none"

    app.action_edit_description()
    app.description_area.text = "cancelled"
    app._exit_edit_mode(commit=False)

    assert app.document.roadmap.steps[0].description == "updated"
    assert "edit cancelled" in _toast_text(app)


def test_editor_description_edit_commits_multiline_text() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_description()
    app.description_area.text = "  first line\nsecond line  "
    app._exit_edit_mode(commit=True)

    assert app.document.roadmap.steps[0].description == "first line\nsecond line"
    assert app.state.dirty is True
    assert app.editing is False


def test_editor_description_edit_rejects_blank_input() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_description()
    app.description_area.text = "   "
    app._exit_edit_mode(commit=True)

    assert app.document.roadmap.steps[0].description == "first"
    assert app.state.dirty is False
    assert app.editing is True
    assert app.description_area.styles.display == "block"
    assert "description must be a non-empty string" in _toast_text(app)


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"row": 1, "column": 4}, 1),
        ({"row": -1, "column": 4}, None),
        ({"row": 2, "column": 4, "out_of_bounds": True}, None),
        ({"row": 2, "column": 4}, None),
        ({}, None),
    ],
)
def test_editor_table_event_row_index_validates_click_targets(
    meta: dict[str, object],
    expected: int | None,
) -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.table.hover_row = 1

    row_index = app._event_table_row_index(
        SimpleNamespace(
            style=SimpleNamespace(meta=meta),
        )
    )

    assert row_index == expected


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
    assert "milestone updated" in _toast_text(app)


def test_editor_priority_prompt_sets_optional_and_clears_priority() -> None:
    app = create_editor_app(Document(Roadmap([Task("task", priority=5)]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_priority()
    app.edit_input.value = "?"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.document.roadmap.steps[0].optional is True
    assert app.table.rows[0][1].plain == "?"

    app.action_edit_priority()
    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.document.roadmap.steps[0].optional is False
    assert app.document.roadmap.steps[0].priority == 0
    assert "priority updated" in _toast_text(app)


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
    assert "completion updated" in _toast_text(app)


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
    assert "completion edit cancelled" in _toast_text(app)


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
    assert "completion updated" in _toast_text(app)


def test_editor_completion_shortcuts_adjust_ongoing_task() -> None:
    task = Task("task", status=ONGOING, completion=50.0)
    app = create_editor_app(Document(Roadmap([task]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_increase_completion()
    assert task.completion == 51.0
    assert "completion updated" in _toast_text(app)

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
    assert "completion updated" in _toast_text(app)


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
    assert "completion updated" in _toast_text(app)


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
    assert "completion edit cancelled" in _toast_text(app)


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
    assert "completion updated" in _toast_text(app)


def test_editor_completion_shortcut_noop_messages() -> None:
    app = create_editor_app(
        Document(Roadmap([Task("pending"), TaskGroup("group", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_decrease_completion()
    assert "task is not started" in _toast_text(app)

    app.action_cursor_down()
    app.action_decrease_completion()
    assert "completion editing is only available for leaf tasks" in _toast_text(app)


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
    assert "completed rows are read-only" in _toast_text(app)
    app.action_edit_priority()
    assert "completed rows are read-only" in _toast_text(app)

    app.action_cursor_down()
    app.action_edit_completion()
    assert "completion editing is only available for leaf tasks" in _toast_text(app)


def test_editor_invalid_prompt_input_stays_open() -> None:
    app = create_editor_app(Document(Roadmap([Task("task")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_priority()
    app.edit_input.value = "high"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.prompt_kind == "priority"
    assert app.edit_input.styles.display == "block"
    assert "priority" in _toast_text(app)


def test_editor_rejects_completed_description_edit() -> None:
    app = create_editor_app(Document(Roadmap([Task("done", status=COMPLETED)]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_edit_description()

    assert app.editing is False
    assert "completed rows are read-only" in _toast_text(app)


def test_editor_cycle_status_refreshes_and_preserves_visible_selection() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_cursor_down()

    app.action_cycle_status()

    assert app.document.roadmap.steps[1].status != 0
    assert app.state.selected_path == (1,)
    assert app.table.cursor_row == 1
    assert "status updated" in _toast_text(app)


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
    assert "row moved" in _toast_text(app)

    app.action_move_row_up()
    assert "already at top" in _toast_text(app)

    app.action_move_row_down()
    assert [step.description for step in app.document.roadmap.steps] == [
        "first",
        "second",
    ]
    assert app.state.selected_path == (1,)
    assert "row moved" in _toast_text(app)


def test_editor_indent_outdent_actions_refresh_selection_and_show_messages() -> None:
    app = create_editor_app(Document(Roadmap([Task("parent"), Task("child")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_cursor_down()

    app.action_indent_row()

    group = app.document.roadmap.steps[0]
    assert isinstance(group, TaskGroup)
    assert [task.description for task in group.tasks] == ["child"]
    assert app.state.selected_path == (0, 0)
    assert app.table.cursor_row == 1
    assert "row indented" in _toast_text(app)

    app.action_outdent_row()
    assert [step.description for step in app.document.roadmap.steps] == [
        "parent",
        "child",
    ]
    assert app.state.selected_path == (1,)
    assert "row outdented" in _toast_text(app)

    app.action_outdent_row()
    assert "already at top level" in _toast_text(app)


def test_editor_indent_first_visible_row_is_noop() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_indent_row()

    assert [step.description for step in app.document.roadmap.steps] == ["first", "second"]
    assert "cannot indent row" in _toast_text(app)


def test_editor_toggle_row_mark_updates_description_prefix() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_toggle_row_mark()

    assert app.state.selected_paths == {(0,)}
    assert app.table.rows[0][4].plain == "* first\n  "
    assert "row selection toggled" in _toast_text(app)


def test_editor_shift_selection_and_escape_clear_marks() -> None:
    app = create_editor_app(
        Document(Roadmap([Task("first"), Task("second"), Task("third"), Task("fourth")]), "text")
    )
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_cursor_down()

    app.action_select_down()
    assert app.state.selected_path == (2,)
    assert app.state.selected_paths == {(1,), (2,)}
    assert "row selection extended" in _toast_text(app)

    app.action_select_down()
    assert app.state.selected_path == (3,)
    assert app.state.selected_paths == {(1,), (2,), (3,)}

    app.key_escape()
    assert app.state.selected_paths == set()
    assert "row selection cleared" in _toast_text(app)


def test_editor_priority_shortcuts_update_focus_or_marked_rows() -> None:
    optional = Task("optional", optional=True)
    pending = Task("pending")
    done = Task("done", status=COMPLETED)
    app = create_editor_app(Document(Roadmap([optional, pending, done]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_increase_priority()
    assert optional.optional is False
    assert optional.priority == DEFAULT_PRIORITY
    assert "priority updated" in _toast_text(app)

    app.action_increase_priority()
    assert optional.priority == 1

    app.action_decrease_priority_large()
    assert optional.optional is True
    assert optional.priority == OPTIONAL_TASK

    app.state.selected_paths = {(1,), (2,)}
    app.action_increase_priority_large()
    assert pending.priority == 10
    assert done.priority == DEFAULT_PRIORITY
    assert app.state.selected_paths == {(1,), (2,)}


def test_editor_group_selected_rows_enters_group_description_edit() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_toggle_row_mark()
    app.action_cursor_down()
    app.action_toggle_row_mark()

    app.action_group_rows()

    group = app.document.roadmap.steps[0]
    assert isinstance(group, TaskGroup)
    assert group.description == "New group"
    assert [task.description for task in group.tasks] == ["first", "second"]
    assert app.state.selected_path == (0,)
    assert app.editing is True
    assert app.description_area.text == "New group"


def test_editor_group_selected_rows_rejects_different_parents() -> None:
    app = create_editor_app(
        Document(
            Roadmap([Task("top"), TaskGroup("group", tasks=[Task("child")])]),
            "text",
        )
    )
    _wire_fake_widgets(app)
    app._refresh_table()
    app.state.selected_paths = {(0,), (1, 0)}

    app.action_group_rows()

    assert "selected rows must share the same parent" in _toast_text(app)


def test_editor_group_single_task_converts_without_editing() -> None:
    app = create_editor_app(Document(Roadmap([Task("task")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_group_rows()

    assert isinstance(app.document.roadmap.steps[0], TaskGroup)
    assert app.editing is False
    assert "task converted to group" in _toast_text(app)


def test_editor_toggle_group_collapsed_action_and_right_click() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("group", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_toggle_group_collapsed()
    assert [row.description for row in app.state.rows] == ["group"]
    assert app.table.rows[0][4].plain == "▸ group\n  "
    assert "group toggled" in _toast_text(app)

    stopped: list[bool] = []
    app.on_mouse_down(
        SimpleNamespace(
            button=3,
            style=SimpleNamespace(meta={"row": 0, "column": 0}),
            stop=lambda: stopped.append(True),
        )
    )
    assert [row.description for row in app.state.rows] == ["group", "child"]
    assert stopped == [True]


def test_editor_description_right_click_on_group_toggles_text_not_children() -> None:
    app = create_editor_app(
        Document(Roadmap([TaskGroup("one\ntwo\nthree", tasks=[Task("child")])]), "text")
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.on_mouse_down(
        SimpleNamespace(
            button=3,
            style=SimpleNamespace(meta={"row": 0, "column": 4}),
            stop=lambda: None,
        )
    )

    assert [row.description for row in app.state.rows] == ["one\ntwo\nthree", "child"]
    assert app.table.rows[0][4].plain == "one\n   │  two\n   │  three"
    assert app.table.row_heights[0] == 3


def test_editor_toggle_all_group_collapsed_alternates_visible_groups() -> None:
    app = create_editor_app(
        Document(
            Roadmap(
                [TaskGroup("outer", tasks=[TaskGroup("inner", tasks=[Task("child")])])]
            ),
            "text",
        )
    )
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_toggle_all_group_collapsed()
    assert [row.description for row in app.state.rows] == ["outer", "inner", "child"]
    assert "groups expanded" in _toast_text(app)

    app.action_toggle_all_group_collapsed()
    assert [row.description for row in app.state.rows] == ["outer"]
    assert "groups collapsed" in _toast_text(app)

    app.action_toggle_all_group_collapsed()
    assert [row.description for row in app.state.rows] == ["outer", "inner"]
    assert "groups expanded" in _toast_text(app)


def test_editor_delete_prompt_defaults_to_cancel() -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_delete_rows()

    assert app.prompt_kind == "delete-confirm"
    assert app.message_bar.value == "Delete row? (y/N)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert [step.description for step in app.document.roadmap.steps] == ["first"]
    assert app.state.dirty is False
    assert "delete cancelled" in _toast_text(app)


def test_editor_delete_prompt_removes_focused_row_after_confirmation() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.action_delete_rows()
    app.edit_input.value = "y"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert [step.description for step in app.document.roadmap.steps] == ["second"]
    assert app.state.dirty is True
    assert app.state.selected_path == (0,)
    assert "row deleted" in _toast_text(app)


def test_editor_delete_prompt_removes_marked_outer_rows_after_confirmation() -> None:
    group = TaskGroup("group", tasks=[Task("child")])
    app = create_editor_app(Document(Roadmap([group, Task("after")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.state.selected_paths = {(0,), (0, 0), (1,)}

    app.action_delete_rows()
    assert app.message_bar.value == "Delete 2 rows? (y/N)"

    app.edit_input.value = "yes"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.document.roadmap.steps == []
    assert app.state.selected_paths == set()
    assert "2 rows deleted" in _toast_text(app)


def test_editor_highlight_event_updates_internal_selection() -> None:
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))
    _wire_fake_widgets(app)
    app._refresh_table()

    app.on_data_table_row_highlighted(SimpleNamespace(cursor_row=1))

    assert app.state.selected_path == (1,)


def test_editor_save_named_document_and_prompt_unnamed_save(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text", path=path))
    _wire_fake_widgets(app)
    app.state.dirty = True

    app.action_save()

    assert path.read_text() == "- [ ] first"
    assert app.state.dirty is False
    assert "saved" in _toast_text(app)

    unnamed = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(unnamed)
    unnamed.action_save()

    assert unnamed.prompt_kind == "save-path"
    assert unnamed.message_bar.value == "Save as path:"


def test_editor_unnamed_save_unknown_extension_prompts_format_default_yaml(
    tmp_path: Path,
) -> None:
    path = tmp_path / "roadmap.data"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)

    app.action_save()
    app.edit_input.value = str(path)
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert app.prompt_kind == "save-format"
    assert app.message_bar.value == "Format? text/json/yaml/markdown (yaml)"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert Roadmap.from_yaml(path.read_text()) == Roadmap([Task("first")])
    assert app.document.path == path
    assert app.document.format == "yaml"
    assert app.document.exists is True
    assert app.state.dirty is False
    assert "saved" in _toast_text(app)


def test_editor_save_prompt_asks_before_overwriting_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] old")
    app = create_editor_app(Document(Roadmap([Task("new")]), "text"))
    _wire_fake_widgets(app)

    app.action_save()
    app.edit_input.value = str(path)
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "save-overwrite-confirm"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert path.read_text() == "- [ ] old"
    assert "save cancelled" in _toast_text(app)

    app.action_save()
    app.edit_input.value = str(path)
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    app.edit_input.value = "y"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert path.read_text() == "- [ ] new"
    assert "saved" in _toast_text(app)


def test_editor_save_prompt_reports_missing_parent(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "roadmap.roadmap"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)

    app.action_save()
    app.edit_input.value = str(path)
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert "save failed" in _toast_text(app)
    assert app.document.path is None


def test_editor_dirty_quit_saves_named_document_by_default(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text", path=path))
    _wire_fake_widgets(app)
    app.state.dirty = True
    exited: list[bool] = []
    app.exit = lambda: exited.append(True)

    app.action_quit()
    assert app.prompt_kind == "exit-save-confirm"

    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert path.read_text() == "- [ ] first"
    assert exited == [True]
    assert app.state.dirty is False


def test_editor_dirty_quit_can_discard_or_cancel(tmp_path: Path) -> None:
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app.state.dirty = True
    exited: list[bool] = []
    app.exit = lambda: exited.append(True)

    app.action_quit()
    app.edit_input.value = "c"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert exited == []
    assert "exit cancelled" in _toast_text(app)

    app.action_quit()
    app.edit_input.value = "n"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert exited == [True]


def test_editor_dirty_unnamed_quit_saves_path_then_exits(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))
    _wire_fake_widgets(app)
    app.state.dirty = True
    exited: list[bool] = []
    app.exit = lambda: exited.append(True)

    app.action_quit()
    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "save-path"

    app.edit_input.value = str(path)
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))

    assert path.read_text() == "- [ ] first"
    assert exited == [True]
    assert app.document.path == path


def test_editor_exit_save_failure_retry_change_or_discard(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "roadmap.roadmap"
    app = create_editor_app(Document(Roadmap([Task("first")]), "text", path=path))
    _wire_fake_widgets(app)
    app.state.dirty = True
    exited: list[bool] = []
    app.exit = lambda: exited.append(True)

    app.action_quit()
    app.edit_input.value = ""
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "save-failure"

    app.edit_input.value = "r"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "save-failure"

    app.edit_input.value = "c"
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert app.prompt_kind == "save-path"

    app.edit_input.value = str(tmp_path / "saved.roadmap")
    app.on_input_submitted(SimpleNamespace(input=app.edit_input))
    assert exited == [True]

    other = create_editor_app(Document(Roadmap([Task("first")]), "text", path=path))
    _wire_fake_widgets(other)
    other.state.dirty = True
    other_exited: list[bool] = []
    other.exit = lambda: other_exited.append(True)
    other.action_quit()
    other.edit_input.value = ""
    other.on_input_submitted(SimpleNamespace(input=other.edit_input))
    other.edit_input.value = "d"
    other.on_input_submitted(SimpleNamespace(input=other.edit_input))
    assert other_exited == [True]


def test_editor_save_after_edit_updates_document(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.roadmap"
    path.write_text("- [ ] old")
    app = create_editor_app(load_document(path))
    _wire_fake_widgets(app)
    app._refresh_table()
    app.action_edit_description()
    app.description_area.text = "new"

    app.action_save()

    assert path.read_text() == "- [ ] new"
    assert app.editing is False


def test_textual_pilot_table_enter_starts_description_editing() -> None:
    pytest.importorskip("textual")
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))

    async def run_pilot() -> None:
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.editing is True
            assert app.description_area.text == "first"

            await pilot.press("escape")
            assert app.editing is False

    asyncio.run(run_pilot())


def test_textual_pilot_f1_toggles_cheatsheet() -> None:
    pytest.importorskip("textual")
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))

    async def run_pilot() -> None:
        async with app.run_test() as pilot:
            await pilot.press("f1")
            assert app.cheatsheet_visible is True

            await pilot.press("escape")
            assert app.cheatsheet_visible is False

    asyncio.run(run_pilot())


def test_textual_pilot_double_click_row_starts_description_editing() -> None:
    pytest.importorskip("textual")
    app = create_editor_app(Document(Roadmap([Task("first"), Task("second")]), "text"))

    async def run_pilot() -> None:
        async with app.run_test(size=(80, 20)) as pilot:
            await pilot.click("#roadmap-grid", offset=(20, 4))
            assert app.editing is False

            await pilot.double_click("#roadmap-grid", offset=(20, 4))
            assert app.state.selected_path == (1,)
            assert app.editing is True
            assert app.description_area.text == "second"

    asyncio.run(run_pilot())


def test_textual_pilot_alt_enter_inserts_description_newline() -> None:
    pytest.importorskip("textual")
    app = create_editor_app(Document(Roadmap([Task("first")]), "text"))

    async def run_pilot() -> None:
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await pilot.press("end")
            await pilot.press("alt+enter")

            assert app.editing is True
            assert app.description_area.text == "first\n"

            app.description_area.insert("second")
            await pilot.press("enter")

            assert app.editing is False
            assert app.document.roadmap.steps[0].description == "first\nsecond"

    asyncio.run(run_pilot())


def test_textual_pilot_drives_remaining_shortcuts() -> None:
    pytest.importorskip("textual")
    second = Task("second")
    app = create_editor_app(
        Document(
            Roadmap(
                [
                    Task("first"),
                    second,
                    TaskGroup("group", tasks=[Task("child")]),
                ]
            ),
            "text",
        )
    )

    async def run_pilot() -> None:
        async with app.run_test(size=(80, 20)) as pilot:
            await pilot.press("shift+down")
            assert app.state.selected_paths == {(0,), (1,)}

            await pilot.press("shift+down")
            assert app.state.selected_paths == {(0,), (1,), (2,)}

            await pilot.press("escape")
            assert app.state.selected_paths == set()

            await pilot.press("up")
            await pilot.press("alt+up")
            assert second.priority == 1

            await pilot.press("alt+shift+up")
            assert second.priority == 11

            await pilot.press("ctrl+shift+t")
            assert [row.description for row in app.state.rows] == [
                "first",
                "second",
                "group",
                "child",
            ]

            await pilot.press("ctrl+shift+t")
            assert [row.description for row in app.state.rows] == [
                "first",
                "second",
                "group",
            ]

    asyncio.run(run_pilot())


def test_textual_pilot_drives_alt_subtask_keybinding() -> None:
    pytest.importorskip("textual")
    document = Document(Roadmap([Task("parent")]), "text")
    app = create_editor_app(document)

    async def run_pilot() -> None:
        async with app.run_test() as pilot:
            await pilot.press("ctrl+o")

            group = document.roadmap.steps[0]
            assert isinstance(group, TaskGroup)
            assert [(task.description, task.order) for task in group.tasks] == [("New task", 1)]
            assert app.state.selected_path == (0, 0)
            assert app.editing is True

    asyncio.run(run_pilot())


def test_textual_pilot_drives_mnemonic_sibling_insert_keybindings() -> None:
    pytest.importorskip("textual")
    document = Document(Roadmap([Task("first")]), "text")
    app = create_editor_app(document)

    async def run_pilot() -> None:
        async with app.run_test() as pilot:
            await pilot.press("o")
            assert [(task.description, task.order) for task in document.roadmap.steps] == [
                ("first", UNSORTED),
                ("New task", 1),
            ]
            assert app.state.selected_path == (1,)
            assert app.editing is True

            await pilot.press("escape")
            await pilot.press("u")
            assert [(task.description, task.order) for task in document.roadmap.steps] == [
                ("first", UNSORTED),
                ("New task", 1),
                ("New task", UNSORTED),
            ]
            assert app.state.selected_path == (2,)
            assert app.editing is True

    asyncio.run(run_pilot())


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

            await pilot.press("o")
            assert app.editing is True
            assert app.state.selected_path == (1,)

            app.description_area.load_text("inserted")
            await pilot.press("enter")
            assert app.editing is False
            assert document.roadmap.steps[1].description == "inserted"
            assert document.roadmap.steps[1].order == 1

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

            await pilot.press("ctrl+j")
            await pilot.press(">")
            assert isinstance(document.roadmap.steps[0], TaskGroup)
            assert document.roadmap.steps[0].tasks[0].description == "inserted"

            await pilot.press("ctrl+s")
            assert app.state.dirty is False

    asyncio.run(run_pilot())
    assert path.read_text().splitlines() == [
        "- [~] first",
        "  1. [~1.0%] (2) inserted",
        "- [x] done",
    ]
