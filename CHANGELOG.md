# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [0.1.9] - 2026-04-21

### Added
- Added graph-level metadata helpers: `get_graph_size()`, `get_graph_version()`, and `bump_graph_version()`.
- Added `incr_active_versions()` to bulk-increment only active member versions in a graph.
- Added comprehensive unit-test coverage for graph metadata, graph-version bumping, active-only bulk version increments, and updated removal/versioning behavior.
- Added PyPI and GitHub wheel installation guidance to the documentation.
- Added badges and PyPI project links to the project documentation.

### Changed
- Updated `remove_connection()` to support bidirectional soft deletion by default, while preserving explicit hard-delete behavior.
- Updated `incr_version()` so only existing active members can be incremented.
- Updated `get_graph_size()` to count only active entries with scores greater than `0`.
- Updated `bump_graph_version()` to reject non-positive increment values.
- Updated CI coverage configuration to scope coverage reporting to the `redisgraph` package.
- Refreshed README and Sphinx docs to document the new graph metadata and versioning APIs.

### Fixed
- Corrected graph-version handling for bulk active-version bumps so the returned graph version remains consistent when no active members exist.
- Brought tests and documentation in line with the latest graph versioning and soft-deletion semantics.
