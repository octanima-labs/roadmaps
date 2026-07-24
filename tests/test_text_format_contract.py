import pytest

from roadmaps import COMPLETED, MAX_PRIORITY, ONGOING, Roadmap, Task, TaskGroup

pytestmark = pytest.mark.skip(reason="text parser and renderer are not implemented yet")


def parse_text_roadmap(source: str) -> Roadmap:
    raise NotImplementedError


def render_text_roadmap(roadmap: Roadmap) -> str:
    raise NotImplementedError


def test_parse_nested_tasks_comments_blank_lines_and_continuations() -> None:
    roadmap = parse_text_roadmap(
        """
# ignored comment
1. [x] Establish project scaffold

2. [~]! feat(core): stabilize task model
  This continuation line belongs to the parent task.
  1. [ ]^900 parser: define text grammar
  - [ ]? docs: draft public examples
""".strip()
    )

    assert len(roadmap.steps) == 2
    assert roadmap.steps[0] == Task(
        "Establish project scaffold",
        order=1,
        status=COMPLETED,
    )
    assert roadmap.steps[1] == TaskGroup(
        "feat(core): stabilize task model\n"
        "This continuation line belongs to the parent task.",
        order=2,
        priority=MAX_PRIORITY,
        tasks=[
            Task("parser: define text grammar", order=1, priority=900),
            Task("docs: draft public examples", optional=True),
        ],
    )


def test_parse_accepts_omitted_status_and_canonicalizes_defaults() -> None:
    roadmap = parse_text_roadmap(
        """
- backlog item
  -? optional child
  -! urgent child
  -^900 prioritized child
""".strip()
    )

    assert roadmap == Roadmap(
        [
            TaskGroup(
                "backlog item",
                tasks=[
                    Task("optional child", optional=True),
                    Task("urgent child", priority=MAX_PRIORITY),
                    Task("prioritized child", priority=900),
                ],
            )
        ]
    )


def test_render_emits_canonical_status_and_marker_positions() -> None:
    roadmap = Roadmap(
        [
            TaskGroup(
                "backlog item",
                tasks=[
                    Task("optional child", optional=True),
                    Task("urgent child", priority=MAX_PRIORITY),
                    Task("prioritized child", priority=900),
                    Task("ongoing child", status=ONGOING),
                ],
            )
        ]
    )

    assert render_text_roadmap(roadmap) == (
        "- [ ] backlog item\n"
        "  - [ ]? optional child\n"
        "  - [ ]! urgent child\n"
        "  - [ ]^900 prioritized child\n"
        "  - [~] ongoing child"
    )


def test_render_removes_priority_from_completed_tasks() -> None:
    task = Task("completed urgent", priority=MAX_PRIORITY)
    task.mark_completed()
    roadmap = Roadmap([task, Task("completed optional", optional=True, status=COMPLETED)])

    assert render_text_roadmap(roadmap) == (
        "- [x] completed urgent\n"
        "- [x]? completed optional"
    )


@pytest.mark.parametrize(
    "source",
    [
        "\t- [ ] tabs are invalid",
        " - [ ] one-space indentation is invalid",
        "- [ ]?^900 optional priority conflict is invalid",
    ],
)
def test_parse_rejects_invalid_text_syntax(source: str) -> None:
    with pytest.raises(ValueError):
        parse_text_roadmap(source)
