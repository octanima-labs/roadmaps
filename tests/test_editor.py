from pathlib import Path

from roadmaps import Roadmap, Task, TaskGroup
from roadmaps._documents import Document
from roadmaps.editor import _top_bar_text, _tree_description, create_editor_app


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
