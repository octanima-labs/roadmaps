from __future__ import annotations

from importlib import import_module
from typing import Any

from roadmaps._documents import Document
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
        """
        BINDINGS = (("q", "quit", "Quit"),)

        def __init__(self, document: Document) -> None:
            super().__init__()
            self.document = document
            self.state = EditorState(document.roadmap)
            self.table: Any | None = None

        def compose(self) -> Any:
            yield static(_top_bar_text(self.document, self.state), id="top-bar")
            table = data_table(id="roadmap-grid", zebra_stripes=True)
            self.table = table
            yield table

        def on_mount(self) -> None:
            table = self.table
            if table is None:
                table = self.query_one("#roadmap-grid", data_table)
                self.table = table
            _populate_table(table, self.state, text)

    return RoadmapEditorApp(document)


def _top_bar_text(document: Document, state: EditorState) -> str:
    path_text = str(document.path) if document.path is not None else "<UNNAMED>"
    dirty_marker = " *" if state.dirty else ""
    return f"{path_text} [{document.format}]{dirty_marker}"


def _populate_table(table: Any, state: EditorState, text: Any) -> None:
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
