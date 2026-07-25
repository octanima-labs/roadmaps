# roadmaps

`roadmaps` is a Python library for structured, human-editable roadmap files.

It models roadmap items as `Roadmap`, `TaskGroup`, and `Task` objects with status, ordering, priority, optionality, milestones, completion, next-step selection, custom text parsing/rendering, Markdown parsing/rendering, JSON round-trips, and a CLI.

The current package is alpha software. The CLI can inspect, convert, initialize, and append top-level tasks to roadmap files.

## Installation

This package is not published yet. Install it from a local clone:

```bash
python -m pip install /path/to/roadmaps/public
```

Or install it editable while developing:

```bash
python -m pip install -e /path/to/roadmaps/public
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
print([task.description for task in roadmap.next_step()])
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

## JSON Round-Trips

Use JSON when a stable machine-readable representation is needed.

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

JSON deserialization is strict. Decode errors include line and column details, and schema errors include JSON paths such as `$.steps[0].tasks[1].priority`.

Leaf task `completion` is loaded for ongoing tasks. Not-started tasks must use `0.0`, completed tasks must use `100.0`, and ongoing tasks may use `0.0` or a one-decimal value from `1.0` through `99.0`. Group and roadmap completion values are derived from children and recomputed on load.

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
- `Roadmap.from_dict(data)` and `roadmap.to_dict()`
- `Roadmap.from_markdown(source)` and `roadmap.to_markdown()`
- `roadmap.next_step()` for incomplete leaf tasks ordered by priority/status/order
- `roadmap.milestones()` for leaf tasks grouped by milestone
- `Task.to_group()` and `TaskGroup.to_task()` for low-level task/group conversion
- `roadmap.task_to_group(task)` and `roadmap.group_to_task(group)` for in-place identity-based conversion, including nested items
- `Task`, `TaskGroup`, and `Roadmap` for direct object construction

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

The `roadmaps` command infers input format from `.roadmap`, `.txt`, `.json`, `.md`, and `.markdown` extensions, or accepts `--format text|json|markdown`.

Validate a file:

```bash
roadmaps validate roadmap.roadmap
```

Show next-step tasks in the source format:

```bash
roadmaps next roadmap.md
```

Render between formats:

```bash
roadmaps render roadmap.roadmap --to markdown
```

Show completion and task counts:

```bash
roadmaps stats roadmap.json
```

Create a new empty roadmap file:

```bash
roadmaps init roadmap.roadmap
roadmaps init --format json roadmap.data
roadmaps init --example roadmap.md
```

`init` refuses to overwrite existing files. Unknown extensions default to text unless `--format` is provided. Use `--example` to create a feature-rich starter roadmap.

Append a top-level task or add a nested child by 1-based dotted path:

```bash
roadmaps add-task roadmap.roadmap -d "docs: publish examples" --urgent --milestone 1
roadmaps add-task roadmap.json -d "core: partial work" --status ongoing --completion 50.0
roadmaps add-task roadmap.roadmap --parent 1.2 -d "nested child"
```

`add-task` supports `--order`, `--priority`, `--urgent`, `--optional`, `--milestone`, `--status not-started|ongoing|completed`, and `--completion`. With `--parent`, the parent path counts all siblings at each level, leaf parents are converted to groups, child order is assigned automatically, and omitted milestones inherit from the parent.

Interactive editing is planned for a future `roadmaps editor` command. Editor dependencies will be optional and installable with `roadmaps[editor]`.

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
