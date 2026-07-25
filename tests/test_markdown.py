import pytest

from roadmaps import COMPLETED, MAX_PRIORITY, ONGOING, Roadmap, Task, TaskGroup


def test_markdown_renders_status_checkboxes() -> None:
    roadmap = Roadmap(
        [
            Task("not started"),
            Task("ongoing", status=ONGOING),
            Task("partial", status=ONGOING, completion=50.0),
            Task("completed", status=COMPLETED),
        ]
    )

    assert roadmap.to_markdown() == (
        "- [ ] not started\n"
        "- [~] ongoing\n"
        "- [~50.0%] partial\n"
        "- [x] completed"
    )


def test_markdown_renders_tuple_metadata() -> None:
    roadmap = Roadmap(
        [
            Task("priority", priority=900),
            Task("milestone", milestone=2),
            Task("priority milestone", priority=900, milestone=2),
            Task("optional", optional=True),
            Task("optional milestone", optional=True, milestone=3),
            Task("urgent", priority=MAX_PRIORITY),
        ]
    )

    assert roadmap.to_markdown() == (
        "- [ ] (900) priority\n"
        "- [ ] (:2) milestone\n"
        "- [ ] (900:2) priority milestone\n"
        "- [ ] (?) optional\n"
        "- [ ] (?:3) optional milestone\n"
        "- [ ] (!) urgent"
    )


def test_markdown_renders_nested_groups_with_existing_order() -> None:
    roadmap = Roadmap(
        [
            TaskGroup(
                "group",
                order=2,
                tasks=[
                    Task("loose child"),
                    Task("first child", order=1),
                    Task("ongoing child", status=ONGOING),
                ],
            ),
            Task("first", order=1),
        ]
    )

    assert roadmap.to_markdown() == (
        "2. [~] group\n"
        "  - [ ] loose child\n"
        "  1. [ ] first child\n"
        "  - [~] ongoing child\n"
        "1. [ ] first"
    )


def test_markdown_omits_completed_mandatory_priority() -> None:
    task = Task("completed priority", priority=900)
    task.mark_completed()
    roadmap = Roadmap([task, Task("completed optional", optional=True, status=COMPLETED)])

    assert roadmap.to_markdown() == (
        "- [x] completed priority\n"
        "- [x] (?) completed optional"
    )


def test_markdown_renders_multiline_descriptions_as_continuations() -> None:
    roadmap = Roadmap([Task("description\nsecond line")])

    assert roadmap.to_markdown() == (
        "- [ ] description\n"
        "  second line"
    )


def test_markdown_preserves_inline_markdown_description_text() -> None:
    description = (
        "docs: use **bold**, *italic*, `code`, $x^2$, "
        "[links](#), and issue #123"
    )
    roadmap = Roadmap([Task(description)])

    assert roadmap.to_markdown() == f"- [ ] {description}"
    assert Roadmap.from_markdown(roadmap.to_markdown()) == roadmap


def test_markdown_minimally_escapes_list_breaking_description_lines() -> None:
    roadmap = Roadmap([Task("- list-like\n1. numbered-like\n**markdown stays**")])

    assert roadmap.to_markdown() == (
        "- [ ] \\- list-like\n"
        "  \\1. numbered-like\n"
        "  **markdown stays**"
    )


def test_markdown_round_trip_from_renderer_subset() -> None:
    roadmap = Roadmap(
        [
            TaskGroup(
                "group",
                milestone=2,
                tasks=[
                    Task("urgent", priority=MAX_PRIORITY, milestone=2),
                    Task("optional", optional=True, milestone=2),
                    Task("ongoing", status=ONGOING, milestone=2),
                ],
            )
        ]
    )

    assert Roadmap.from_markdown(roadmap.to_markdown()) == roadmap


def test_markdown_parses_status_markers_and_metadata_tuples() -> None:
    roadmap = Roadmap.from_markdown(
        """
- [ ] (!) urgent
- [ ] (900) priority
- [ ] (:2) milestone
- [ ] (!:2) urgent milestone
- [ ] (900:3) priority milestone
- [ ] (?) optional
- [ ] (?:4) optional milestone
- [~] ongoing
- [~50.0%] partial
- [X] completed
""".strip()
    )

    assert roadmap == Roadmap(
        [
            Task("urgent", priority=MAX_PRIORITY),
            Task("priority", priority=900),
            Task("milestone", milestone=2),
            Task("urgent milestone", priority=MAX_PRIORITY, milestone=2),
            Task("priority milestone", priority=900, milestone=3),
            Task("optional", optional=True),
            Task("optional milestone", optional=True, milestone=4),
            Task("ongoing", status=ONGOING),
            Task("partial", status=ONGOING, completion=50.0),
            Task("completed", status=COMPLETED),
        ]
    )


def test_markdown_round_trips_custom_ongoing_completion() -> None:
    roadmap = Roadmap(
        [
            Task("partial", status=ONGOING, completion=50.0),
            Task("completed", status=COMPLETED),
            Task("not started"),
        ]
    )

    assert Roadmap.from_markdown(roadmap.to_markdown()) == roadmap


def test_markdown_parses_nested_groups_and_inherits_milestones() -> None:
    roadmap = Roadmap.from_markdown(
        """
- [ ] (:2) parent
  - [ ] inherited child
  - [ ] (:3) explicit child
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


def test_markdown_parses_selected_roadmap_section_from_document() -> None:
    roadmap = Roadmap.from_markdown(
        """
# Intro

- [ ] ignored

## Roadmap

- [ ] lower level ignored

# Roadmap

- [ ] selected task

# Notes

- [ ] ignored note
""".strip()
    )

    assert roadmap == Roadmap([Task("selected task")])


def test_markdown_parser_unescapes_list_breaking_description_lines() -> None:
    roadmap = Roadmap.from_markdown(
        """
- [ ] \\- list-like
  \\1. numbered-like
  **markdown stays**
""".strip()
    )

    assert roadmap == Roadmap([Task("- list-like\n1. numbered-like\n**markdown stays**")])


@pytest.mark.parametrize(
    "source",
    [
        "\t- [ ] tabs are invalid",
        " - [ ] one-space indentation is invalid",
        "- [ ] (0) zero priority",
        "- [ ] (:0) zero milestone",
        "- [ ] (abc) invalid priority",
        "- [ ] (?!) malformed metadata",
        "- [~0.0%] zero completion",
        "- [~99.5%] too much completion",
        "- [~50%] missing decimal completion",
        "- [~50.55%] too precise completion",
        "- [~50.0%] parent\n  - [ ] child",
        "- [ ] description\n  # heading",
        "- [ ] description\n  ```python",
        "- [ ] description\n  > quote",
        "- [ ] description\n  | --- | --- |",
        "  - [ ] indentation skips root",
        "1. [ ] first\n3. [ ] missing second",
        "# Not Roadmap\n\n- [ ] task",
    ],
)
def test_markdown_parser_rejects_invalid_subset(source: str) -> None:
    with pytest.raises(ValueError):
        Roadmap.from_markdown(source)
