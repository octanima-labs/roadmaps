from roadmaps import COMPLETED, MAX_PRIORITY, ONGOING, Roadmap, Task, TaskGroup


def test_markdown_renders_status_checkboxes() -> None:
    roadmap = Roadmap(
        [
            Task("not started"),
            Task("ongoing", status=ONGOING),
            Task("completed", status=COMPLETED),
        ]
    )

    assert roadmap.to_markdown() == (
        "- [ ] not started\n"
        "- [~] ongoing\n"
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
        "- [ ] (999) urgent"
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


def test_markdown_minimally_escapes_list_breaking_description_lines() -> None:
    roadmap = Roadmap([Task("- list-like\n1. numbered-like\n**markdown stays**")])

    assert roadmap.to_markdown() == (
        "- [ ] \\- list-like\n"
        "  \\1. numbered-like\n"
        "  **markdown stays**"
    )
