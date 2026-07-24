import pytest

from roadmaps import COMPLETED, MAX_PRIORITY, ONGOING, Roadmap, Task, TaskGroup


def test_parse_nested_tasks_comments_blank_lines_and_continuations() -> None:
    roadmap = Roadmap.from_text(
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
    roadmap = Roadmap.from_text(
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

    assert roadmap.to_text() == (
        "- [~] backlog item\n"
        "  - [ ]? optional child\n"
        "  - [ ]! urgent child\n"
        "  - [ ]^900 prioritized child\n"
        "  - [~] ongoing child"
    )


def test_render_removes_priority_from_completed_tasks() -> None:
    task = Task("completed urgent", priority=MAX_PRIORITY)
    task.mark_completed()
    roadmap = Roadmap([task, Task("completed optional", optional=True, status=COMPLETED)])

    assert roadmap.to_text() == (
        "- [x] completed urgent\n"
        "- [x]? completed optional"
    )


def test_parse_normalizes_completed_mandatory_priority_markers() -> None:
    roadmap = Roadmap.from_text(
        """
- [x]! completed urgent
- [x]^900 completed prioritized
""".strip()
    )

    assert roadmap.steps == [
        Task("completed urgent", status=COMPLETED),
        Task("completed prioritized", status=COMPLETED),
    ]


def test_task_line_wins_over_continuation_line() -> None:
    roadmap = Roadmap.from_text(
        """
- [ ] parent
  Not a task line.
  - [ ] child
""".strip()
    )

    assert roadmap == Roadmap(
        [
            TaskGroup(
                "parent\nNot a task line.",
                tasks=[Task("child")],
            )
        ]
    )


def test_render_preserves_list_order_instead_of_sorting_by_order() -> None:
    roadmap = Roadmap([Task("second", order=2), Task("first", order=1), Task("loose")])

    assert roadmap.to_text() == (
        "2. [ ] second\n"
        "1. [ ] first\n"
        "- [ ] loose"
    )


def test_parse_and_render_milestones_after_metadata() -> None:
    roadmap = Roadmap.from_text(
        """
- [ ] (1) plain milestone
- [ ]^900 (2) prioritized milestone
-! (3) shorthand urgent milestone
-? (4) shorthand optional milestone
""".strip()
    )

    assert roadmap == Roadmap(
        [
            Task("plain milestone", milestone=1),
            Task("prioritized milestone", priority=900, milestone=2),
            Task("shorthand urgent milestone", priority=MAX_PRIORITY, milestone=3),
            Task("shorthand optional milestone", optional=True, milestone=4),
        ]
    )
    assert roadmap.to_text() == (
        "- [ ] (1) plain milestone\n"
        "- [ ]^900 (2) prioritized milestone\n"
        "- [ ]! (3) shorthand urgent milestone\n"
        "- [ ]? (4) shorthand optional milestone"
    )


def test_render_omits_zero_milestone() -> None:
    roadmap = Roadmap([Task("no milestone")])

    assert roadmap.to_text() == "- [ ] no milestone"


def test_parent_milestone_inherits_to_children_when_omitted() -> None:
    roadmap = Roadmap.from_text(
        """
- [ ] (2) parent
  - [ ] inherited child
  - [ ] (3) explicit child
""".strip()
    )

    assert roadmap == Roadmap(
        [
            TaskGroup(
                "parent",
                milestone=2,
                tasks=[
                    Task("inherited child", milestone=2),
                    Task("explicit child", milestone=3),
                ],
            )
        ]
    )
    assert [task.description for task in roadmap.milestones(index=2)[2]] == [
        "inherited child"
    ]
    assert [task.description for task in roadmap.milestones(index=3)[3]] == [
        "explicit child"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "\t- [ ] tabs are invalid",
        " - [ ] one-space indentation is invalid",
        "- [ ]?^900 optional priority conflict is invalid",
        "  - [ ] indentation cannot skip root",
        "1. [ ] first\n3. [ ] missing second",
        "1. [ ] first\n1. [ ] duplicate first",
        "- [ ] (0) zero milestone",
        "- [ ] (-1) negative milestone",
        "- [ ] (abc) non-integer milestone",
        "- [ ] (1 malformed milestone",
    ],
)
def test_parse_rejects_invalid_text_syntax(source: str) -> None:
    with pytest.raises(ValueError):
        Roadmap.from_text(source)
