# roadmaps

`roadmaps` is a Python library for structured, human-editable roadmap files.

It models roadmap items as `Roadmap`, `TaskGroup`, and `Task` objects with status, ordering, priority, optionality, milestones, completion, next-step selection, custom text parsing/rendering, and JSON round-trips.

The current package is an alpha library. A CLI may come later, but no CLI commands are implemented yet.

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
  1. [ ]^900 parser: implement text format
  - [ ]? docs: add public examples
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
  - [ ]? optional child
- [ ] unordered task
```

Syntax summary:

- Use exactly two spaces per nesting level.
- Use `-` for unordered items or `1.`, `2.`, `3.` for numbered sibling items.
- Use `[ ]`, `[~]`, and `[x]` for not-started, ongoing, and completed status.
- Omitted status is accepted as not started, but rendering always emits status.
- Use `!` for urgent priority and `^N` for numeric priority; larger numbers are higher priority.
- Use `?` for optional tasks; optionality and priority are mutually exclusive.
- Use `(N)` for positive-integer milestones.
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

## Core API

Useful entry points:

- `Roadmap.from_text(source)` and `roadmap.to_text()`
- `Roadmap.from_json(source)` and `roadmap.to_json()`
- `Roadmap.from_dict(data)` and `roadmap.to_dict()`
- `roadmap.next_step()` for incomplete leaf tasks ordered by priority/status/order
- `roadmap.milestones()` for leaf tasks grouped by milestone
- `Task`, `TaskGroup`, and `Roadmap` for direct object construction

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
