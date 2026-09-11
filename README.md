# roadmaps

`roadmaps` is a Python library for structured, human-editable roadmap files.

It models roadmap items as `Roadmap`, `TaskGroup`, and `Task` objects with status, ordering, priority, optionality, milestones, completion, next-step selection, custom text parsing/rendering, Markdown parsing/rendering, JSON/YAML round-trips, and a CLI.

The current package is alpha software. The CLI can inspect, convert, initialize, and update roadmap files.

## Installation

This package is not published yet. Install the CLI directly from GitHub with `pipx`:

```bash
pipx install "roadmaps[all] @ git+https://github.com/octanima-labs/roadmaps.git"
```

Use `--force` to upgrade an existing GitHub install:

```bash
pipx install --force "roadmaps[all] @ git+https://github.com/octanima-labs/roadmaps.git"
```

The `all` extra includes both optional YAML and interactive editor dependencies.

Or install it from a local clone:

```bash
python -m pip install /path/to/roadmaps
```

YAML support is optional and uses PyYAML:

```bash
python -m pip install "/path/to/roadmaps[yaml]"
```

The interactive editor is optional and uses Textual:

```bash
python -m pip install "/path/to/roadmaps[editor]"
```

Or install it editable while developing:

```bash
python -m pip install -e /path/to/roadmaps
```

## Text Roadmaps

The custom text format is the primary human-editable format.

```python
from roadmaps import Roadmap

source = """
1. [x] (1) project: create package scaffold
2. [~]! (2) core: stabilize roadmap model
  1. [~50.0%]^900 parser: implement text format
  - [ ]? docs: add **public** examples with [links](#)
- [ ] backlog: keep unordered ideas
""".strip()

roadmap = Roadmap.from_text(source)

print(roadmap.completion_percent)
print(roadmap.to_text())
print([task.description for task in roadmap.next(count=3)])
```

## Text Syntax

```text
1. [x] (1) completed milestone task
2. [~]! urgent ongoing task
  1. [ ]^900 high-priority child
  2. [~50.0%] partially complete child
  - [ ]? optional child
- [ ] unordered task
```

Syntax summary:

- Use exactly two spaces per nesting level.
- Use `-` for unordered items or `1.`, `2.`, `3.` for numbered sibling items.
- Use `[ ]`, `[~]`, `[~50.0%]`, and `[x]` for not-started, ongoing, partially complete ongoing, and completed status.
- Omitted status is accepted as not started, but rendering always emits status.
- Use `!` for urgent priority and `^N` for numeric priority; larger numbers are higher priority.
- Use `?` for optional tasks; optionality and priority are mutually exclusive.
- Use `(N)` for positive-integer milestones.
- Descriptions may contain inline Markdown-like text such as `**bold**`, `*italic*`, inline code, `$math$`, and `[links](#)`.
- Descriptions do not support headings, blockquotes, fenced code blocks, tables, or nested block lists.
- Blank lines and `#` comments are ignored.

## JSON And YAML Round-Trips

Use JSON when a stable machine-readable representation is needed. YAML uses the same schema and is available when PyYAML is installed.

```python
from roadmaps import JSONValidationError, Roadmap

roadmap = Roadmap.from_text("- [ ]^900 (1) json: serialize roadmap")
payload = roadmap.to_json()

try:
    loaded = Roadmap.from_json(payload)
except JSONValidationError as error:
    print(error)

assert loaded == roadmap
```

JSON and YAML deserialization are strict. Decode errors include line and column details when available, and schema errors include JSON paths such as `$.steps[0].tasks[1].priority`.

YAML mirrors the JSON API with `to_yaml()` and `from_yaml()`:

```python
from roadmaps import Roadmap, YAMLValidationError

roadmap = Roadmap.from_text("- [ ]^900 (1) yaml: serialize roadmap")
payload = roadmap.to_yaml()

try:
    loaded = Roadmap.from_yaml(payload)
except YAMLValidationError as error:
    print(error)

assert loaded == roadmap
```

If PyYAML is not installed, YAML methods and CLI commands raise a clear error asking for `roadmaps[yaml]`.

Leaf task `completion` is loaded for ongoing tasks. Not-started tasks must use `0.0`, completed tasks must use `100.0`, and ongoing tasks may use `0.0` or a one-decimal value from `1.0` through `99.0`. Group and roadmap completion values are derived from children and recomputed on load.

Leaf task `start_date` and `completion_date` are optional JSON-only fields. They use UTC ISO timestamps such as `2026-07-25T10:30:00Z`, are validated against task status, and are omitted when absent. Task groups serialize derived dates when present; text and Markdown formats do not preserve dates.

Descriptions remain plain strings in JSON. Inline rich text is preserved, while block Markdown structures are rejected during model validation.

## Markdown Rendering

Render a roadmap for display with `to_markdown()` or parse a roadmap section with `from_markdown()`:

```python
from roadmaps import Roadmap

roadmap = Roadmap.from_text("- [~50.0%]^900 (1) docs: publish **examples**")
same_roadmap = Roadmap.from_markdown("- [~50.0%] (900:1) docs: publish **examples**")

print(roadmap.to_markdown())
assert same_roadmap == roadmap
```

Markdown output uses GitHub-style task markers and compact metadata tuples:

```markdown
- [~50.0%] (900:1) docs: publish **examples**
```

Tuple metadata uses `(priority:milestone)`, `(!:milestone)`, `(:milestone)`, `(priority)`, `(!)`, `(?)`, or `(?:milestone)` as needed. Inline Markdown in descriptions is preserved as written, but block Markdown structures are invalid. Larger Markdown documents can be parsed when they contain a heading named `Roadmap`; the parser reads the highest-level matching section.

## Core API

Useful entry points:

- `Roadmap.from_text(source)` and `roadmap.to_text()`
- `Roadmap.from_json(source)` and `roadmap.to_json()`
- `Roadmap.from_yaml(source)` and `roadmap.to_yaml()`
- `Roadmap.from_dict(data)` and `roadmap.to_dict()`
- `Roadmap.from_markdown(source)` and `roadmap.to_markdown()`
- `roadmap.next(count=1)` and `task_group.next(count=1)` for counted incomplete leaf tasks ordered by priority, optionality, status, and order
- `roadmap.milestones()` for leaf tasks grouped by milestone
- `roadmap.filter_items()` for status, optionality, and conventional category filtering across tasks and groups
- `Task.to_group()` and `TaskGroup.to_task()` for low-level task/group conversion
- `roadmap.task_to_group(task)` and `roadmap.group_to_task(group)` for in-place identity-based conversion, including nested items
- `ENABLE_TUI_ORDER_BREADCRUMBS` controls whether the optional editor shows display-only order breadcrumbs
- `ENABLE_TUI_UNICODE_PROGRESS`, `TUI_PROGRESS_BAR_WIDTH`, and `ENABLE_TUI_ROMAN_MILESTONES` control optional editor progress-bar and milestone display polish
- `Task`, `TaskGroup`, and `Roadmap` for direct object construction

`Task.mark_ongoing()` sets `start_date` when missing and clears `completion_date`. `Task.mark_completed()` sets `completion_date` and fills `start_date` if needed. `TaskGroup.start_date` and `TaskGroup.completion_date` are derived from descendant leaf tasks.

Convert an existing task into a group, then flatten it back while preserving metadata:

```python
from roadmaps import Roadmap, Task

task = Task("parser: add examples", priority=900, milestone=1)
roadmap = Roadmap([task])

group = roadmap.task_to_group(task, tasks=[Task("write text example")])
roadmap.group_to_task(group)

print(roadmap.to_text())
```

`Task -> TaskGroup` preserves description, order, priority, optionality, and milestone. Explicit ongoing completion is dropped because groups derive completion from children. `TaskGroup -> Task` uses the group's derived status, inserts former children as following siblings, and does not renumber existing order values.

## CLI

The `roadmaps` command infers input format from `.roadmap`, `.txt`, `.json`, `.yaml`, `.yml`, `.md`, and `.markdown` extensions, or accepts `--format text|json|yaml|markdown`.

Validate a file:

```bash
roadmaps validate roadmap.roadmap
```

Show the next task, or several next tasks, in the source format:

```bash
roadmaps next roadmap.md
roadmaps next roadmap.md --count 3
```

Render between formats:

```bash
roadmaps export roadmap.roadmap --to markdown
roadmaps export roadmap.json --to yaml
```

Show completion and task counts:

```bash
roadmaps stats roadmap.json
```

Filter roadmap items:

```bash
roadmaps search roadmap.roadmap --uncompleted
roadmaps search roadmap.md --completed --ongoing --optional
roadmaps search roadmap.yaml --category docs 'feat(parser)' --to markdown
```

`search` returns flat `Task` and `TaskGroup` matches in traversal order. Status filters combine by union, optional items are hidden unless `--optional` or `--all` is supplied, categories match conventional prefixes such as `docs:` or `feat(parser):`, and no matches returns `no matching tasks` with exit code `0`.

Create a new empty roadmap file:

```bash
roadmaps init roadmap.roadmap
roadmaps init --format json roadmap.data
roadmaps init --format yaml roadmap.data
roadmaps init --example roadmap.md
```

`init` refuses to overwrite existing files. Unknown extensions default to text unless `--format` is provided. Markdown initialization writes a `## Roadmap` section. Use `--example` to create a feature-rich starter roadmap.

Append a top-level task or add a nested child by 1-based dotted path:

```bash
roadmaps task add roadmap.roadmap -d "docs: publish examples" --urgent --milestone 1
roadmaps task add roadmap.json -d "core: partial work" --status ongoing --completion 50.0
roadmaps task add roadmap.yaml -d "core: partial work" --status ongoing --completion 50.0
roadmaps task add roadmap.roadmap --parent 1.2 -d "nested child"
```

`task add` supports `--order`, `--priority`, `--urgent`, `--optional`, `--milestone`, `--status not-started|ongoing|completed`, and `--completion`. With `--parent`, the parent path counts all siblings at each level, leaf parents are converted to groups, child order is assigned automatically, and omitted milestones inherit from the parent. Ongoing and completed tasks created through `task add` receive JSON-persisted date fields automatically. Markdown saves preserve an existing `Roadmap` section heading level.

Edit, delete, move, group, and ungroup existing items by 1-based dotted path:

```bash
roadmaps task set roadmap.roadmap 1.2 -d "docs: updated" --status ongoing --completion 50
roadmaps task delete roadmap.roadmap 2
roadmaps task move roadmap.roadmap 3 --before 1
roadmaps task move roadmap.roadmap 2 --parent 1
roadmaps task group roadmap.roadmap 1 2 -d "New group"
roadmaps task ungroup roadmap.roadmap 1
```

`task set` supports `--description`, `--priority`, `--urgent`, `--optional`, `--not-optional`, `--milestone`, `--status not-started|ongoing|completed`, and `--completion`. `task delete` removes a `TaskGroup` subtree. `task move` accepts exactly one of `--before PATH`, `--after PATH`, `--parent PATH`, or `--top-level`; leaf parents are converted to groups. `task group` requires sibling paths and `task ungroup` promotes children to the group parent. Write commands parse and re-render files canonically while preserving the source format.

`roadmaps editor [PATH] [--format text|json|yaml|markdown]` launches an MVP Textual editor when `roadmaps[editor]` is installed. It shows a styled path/format top bar with an orange `[UNSAVED]` tag only when dirty, plus Completion, Priority, Milestone, Order, and tree-prefixed Description columns with progress bars, priority coloring across metadata and description columns, cyan incomplete optional tasks, dimmed completed rows, roman milestones, selected-row reverse styling, and display-only order breadcrumbs. Keybindings include navigation, row selection/grouping/collapse, metadata prompts, completion/priority shortcuts, description editing, description copy with `c`, sibling and subtask insertion, movement, nesting, completed-row visibility, save, and dirty-exit confirmation. Without Textual it returns `error: Textual is required for the editor; install roadmaps[editor]`.

## Development

Run checks from this `public/` directory:

```bash
hatch run python -m pytest
hatch run python -m ruff check .
hatch run python -m mypy src tests
hatch run python -m build
```

## License

MIT
