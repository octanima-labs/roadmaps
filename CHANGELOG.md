# Changelog

## [Unreleased]

## [1.1.0] - 2026-09-11

### Added

- Add a TUI `c` shortcut to copy the focused or marked row descriptions to the clipboard.
- Show a warning toast when `ctrl+c` is pressed, guiding users to exit with `ctrl+q`, and list `Q / Ctrl+Q` as Exit in the TUI cheatsheet.

### Fixed

- Rename the installed CLI command from `roadmap` to `roadmaps` to match the package name.

## [1.0.0] - 2026-08-09

### Added

- Add the core `Roadmap`, `TaskGroup`, and `Task` data model with ordering, priority, optionality, milestones, completion, next-step selection, filtering, and task/group conversion helpers.
- Add custom text roadmap parsing and rendering, including nested ordered and unordered tasks, metadata markers, comments, multiline descriptions, and canonical output.
- Add strict JSON serialization and deserialization with validation errors, plus optional PyYAML-backed YAML support using the same schema.
- Add strict roadmap-shaped Markdown parsing and rendering, including task-list status markers, compact metadata tuples, and larger-document Roadmap heading extraction.
- Add the `roadmap` CLI for validation, next-step output, stats, format export, search, roadmap initialization, and noninteractive task editing commands.
- Add shared document helpers for CLI and editor file loading, format inference, rendering, saving, missing-file initialization, and Markdown Roadmap heading preservation.
- Add the optional Textual roadmap editor with table navigation, description editing, task insertion, status cycling, metadata prompts, completion shortcuts, row movement, nesting, grouping, collapse controls, save prompts, dirty-exit handling, deletion, and the F1 cheatsheet.
- Add TUI visual polish for progress bars, priority coloring, roman milestones, tree-prefixed multiline descriptions, selected-row styling, configurable row spacing, and toast notifications.

### Changed

- Split the original core implementation into focused modules for models, validation, parsing, rendering, serialization, document helpers, editor state, and Textual integration.
- Refine CLI command naming and task command structure in preparation for the stable release.

### Fixed

- Preserve selected editor rows across table mutations and description edits.
- Preserve TUI tree prefixes for multiline rows.
- Fix TUI shortcut conflicts, switched sibling insertion shortcuts, `ctrl+shift+t` expand-all behavior, and grouping behavior for tasks without descriptions.
