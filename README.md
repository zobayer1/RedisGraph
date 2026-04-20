# Redis Graph Connection Manager

Redis Graph Connection Manager (module name: **redisgraph**) is a Python module designed to efficiently manage and query domain-to-member **edge** graphs using Redis as the backend.

[![Python](https://img.shields.io/badge/python-3.8%2B-blueviolet?logo=python&logoColor=green)](https://www.python.org)
[![Pre-Commit](https://img.shields.io/badge/pre--commit-enabled-blue?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code Style: Black](https://img.shields.io/badge/code%20style-Black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-ff69b4.svg)](https://github.com/zobayer1/RedisGraph/blob/main/LICENSE)\
[![Tests](https://github.com/zobayer1/RedisGraph/actions/workflows/python-package.yml/badge.svg?branch=main)](https://github.com/zobayer1/RedisGraph/actions/workflows/python-package.yml)
[![PyPi Publish](https://github.com/zobayer1/RedisGraph/actions/workflows/python-publish.yml/badge.svg)](https://github.com/zobayer1/RedisGraph/actions/workflows/python-publish.yml)
[![Codecov](https://codecov.io/github/zobayer1/RedisGraph/graph/badge.svg?token=oTgbo2idT1)](https://codecov.io/github/zobayer1/RedisGraph)
[![Read the Docs](https://img.shields.io/readthedocs/redisgraph?logo=readthedocs&labelColor=blue)](https://redisgraph.readthedocs.io/en/latest)

## PyPI Project Page

[https://pypi.org/project/graphconnectionmanager/](https://pypi.org/project/graphconnectionmanager/)

## Online Documentation

[https://redisgraph.readthedocs.io/en/latest/](https://redisgraph.readthedocs.io/en/latest/)

## Dependencies

- Python 3.8 or above
- Redis server (for backend storage)
- `redis` Python client library (install via `pip install redis`)

## Features

| Feature                  | Description                                                                        |
|--------------------------|------------------------------------------------------------------------------------|
| Add Edge                 | Add outgoing and incoming edges between domains and subjects.                      |
| Add Multiple Edges       | Efficiently add multiple outgoing edges from a domain to a list of subjects.       |
| Paginated Edge Retrieval | Retrieve active and removed edges with pagination support.                         |
| All Active Edges         | Fetch all active outgoing edges for a domain without version tracking.             |
| Active Graph Size        | Count only active edges in a graph; soft-deleted entries are excluded.             |
| Graph Version Query      | Read the current graph version counter, defaulting to zero when uninitialized.     |
| Graph Version Bump       | Increment a graph version counter directly, with validation against non-positive bumps. |
| Bulk Active Version Bump | Increment all active edge versions while leaving soft-deleted entries untouched.    |
| Intersection Query       | Find common members between two domain graphs.                                     |
| Incremental Versioning   | Maintain atomic version numbers for domains and subjects for tracking changes.     |
| Version Tracking         | Track and retrieve the version (score) of each edge.                               |
| Active-Only Version Bump | Increment versions only for existing active edges; removed or missing edges raise errors. |
| Soft Delete Edges        | Soft-delete outgoing and incoming edges with negative versions for historical tracking. |
| Remove Domain            | Remove all outgoing and incoming edges for a domain                                |
| Redis Backend            | All operations are backed by a Redis server for performance and scalability.       |

## Algorithm Overview

### Add Edge

When adding an edge from a domain entity (e.g., `user1`) to a subject (e.g., `subject1`):

```
- add_connection(domain, subject):
  1. Add `subject1` to the outgoing set of `user1` with the next atomic domain version number.
  2. Add `user1` to the incoming set of `subject1` with the next atomic subject version number.
```

This ensures that both outgoing and incoming relationships are tracked and versioned for efficient querying and higher-level historical tracking. This also serves the purpose of updating the edge graph in both directions for existing entries.

### Increment Edge Version

When incrementing the version of an existing edge:

```
- incr_version(domain, subject):
  1. Read the current score for `subject` from the selected graph of `domain`.
  2. If the edge is missing or has a negative score, raise `ValueError`.
  3. Fetch the next atomic version number for the graph.
  4. Update the existing edge with `ZADD XX` so only an already-present edge is modified.
```

This keeps version bumps limited to active edges. Removed edges and never-seen edges must be re-added with `add_connection(...)` before they can be incremented.

### Get Graph Size and Version

When reading graph-level metadata:

```
- get_graph_size(domain, graph_type=outgoing):
  1. Count only members whose scores are greater than `0`.
  2. Exclude soft-deleted members with negative scores.

- get_graph_version(domain, graph_type=outgoing):
  1. Read the graph's version key.
  2. Return `0` when the version key has not been created yet.

- incr_active_versions(domain, graph_type=outgoing, value=1):
  1. Reject zero or negative increment values with `ValueError`.
  2. Increment only members whose scores are greater than `0`.
  3. Leave soft-deleted members unchanged.
  4. Return the current graph version after the update.

- bump_graph_version(domain, graph_type=outgoing, value=1):
  1. Reject zero or negative bump values with `ValueError`.
  2. Increment the graph version key by `value`.
  3. Return the new graph version.
```

`get_graph_size(...)` reports the active graph size, `get_graph_version(...)` reports the latest version counter used for that graph direction, `incr_active_versions(...)` bulk-bumps only active members, and `bump_graph_version(...)` advances the graph-level counter directly when needed.

### Remove Edge

When removing an edge from a domain entity (e.g., `user1`) to a subject (e.g., `subject1`):

```
- remove_connection(domain, subject, soft=True):
  1. Fetch the next atomic version number for the domain: `dv`.
  2. Add `subject1` to the outgoing set of `user1` with `(-1)*dv` (soft delete).
  3. Fetch the next atomic version number for the subject's incoming graph: `sv`.
  4. Add `user1` to the incoming set of `subject1` with `(-1)*sv` (soft delete).

- remove_connection(domain, subject, soft=False):
  1. Remove `subject1` from the outgoing set of `user1` (hard delete).
  2. Remove `user1` from the incoming set of `subject1` (hard delete).
```

The default behavior preserves deletion history in both directions. Use `soft=False` when the edge should be removed entirely without retaining historical markers.

### Get Edges

When retrieving a paginated list of active edges and all removed (soft-deleted) edges for a given domain:

```
- get_connections(domain_id, graph_type=outgoing, size=100, cut_off=0):
  - Fetch Active Edges:
    - Query the `graph_type` edge set for `domain_id` to fetch up to `size` items with version scores
      - Query range `(cut_off, +inf]` (exclusive lower bound).
    - Collect the list of active edge IDs and their scores.
  - Determine Score Range:
    - If the active list is not empty, set `max_score` to the highest score among the fetched items.
    - If the active list is empty, set `max_score` to the current domain version value.
  - Fetch Removed Edges:
    - Query the same set for items with negative scores
      - Query range `[-max_score, -cut_off)` (inclusive lower, exclusive upper bound).
    - Collect the list of removed (soft-deleted) edge IDs.
  - Return Results:
    - Return the list of active edge IDs, the list of removed edge IDs, and the `max_score` value
    - use as the `cut_off` in the next page query.
```

This approach enables efficient pagination of active edges and retrieval of all removed edges within the same score window. The caller needs to handle the `next_page` logic by passing the `max_score` as the new `cut_off`. The caller may stop pagination when the `next_page` does not change from the previous call. Only the active edges are paginated, while all removed edges within the range are fetched in one go. Only ascending order of score is supported as the pagination order.

## Build

To build the package, ensure you have `setuptools`, `wheel`, and `build` installed. Run the build command in the root

```bash
rm -rf build dist *.egg-info
python -m pip install --upgrade build
python -m build --wheel
```

To clean built files in your Python project, you should remove the following directories and files:

- build/
- dist/
- *.egg-info/ (e.g., src/redisgraph.egg-info/)

Note: as part of the rename, the egg-info directory will move from the old project name to the new one (e.g., src/redisgraph.egg-info/).

## Installation

You can install the Redis Graph Connection Manager in one of the following ways:

### 1. Install from PyPI (recommended)

The distribution name on PyPI is `graphconnectionmanager`, but you import it in Python as `redisgraph`.

```bash
python -m pip install --upgrade pip
python -m pip install graphconnectionmanager
```

### 2. Install a wheel from a GitHub Release

If you prefer not to install from PyPI, you can download the wheel (`.whl`) from the GitHub Releases page and install it locally.

1. Download the appropriate wheel file, for example:

   - `graphconnectionmanager-<version>-py3-none-any.whl`

2. Install it with pip:

```bash
python -m pip install --upgrade pip
python -m pip install ./graphconnectionmanager-<version>-py3-none-any.whl
```

### 3. Manual installation (copy into your project)

- Copy the `redisgraph` package directory into your project.
- Ensure your project can import the `redisgraph` module as needed.

## Example Usage

An example code which initializes the manager, adds an edge, and retrieves edges.

```python
from redisgraph import GraphManager
import redis

# Initialize Redis client and GraphManager
redis_client = redis.Redis(host="localhost", port=6379, db=0)
manager = GraphManager(redis_client, prefix="graph", namespace="phonebook")

# Add an edge from domain 'room:1' to member 'user:42'
manager.add_connection("user_1", "8801791223344")

# Retrieve all active edges for 'room:1'
edges, removed, next_page = manager.get_connections("user_1")
print(edges, removed, next_page)
```

For more examples and advanced usage, explore the [tests](./tests/test_graph_manager.py) package in this repository.

## Documentation

The project includes Sphinx-based documentation under the `docs/` directory.

To build the HTML documentation:

```bash
cd docs
sphinx-build -b html . _build/html
```

If you have a `make`-based environment set up, you can alternatively run:

```bash
cd docs
make html
```

After a successful build, open the generated documentation by pointing your browser to:

```bash
xdg-open _build/html/index.html
```

(or open `_build/html/index.html` manually in your browser).

## Testing

### Default (recommended): in-memory Redis via `fakeredis`

By default, the test suite uses an in-memory Redis implementation (`fakeredis`), so you **don't** need a Redis server running locally.

When you run the tests you'll see a one-line banner like:

- `[redisgraph tests] redis backend: fakeredis (in-memory, db=0)`

Run tests:

```bash
pytest
```

### Tox: run the test suite on multiple Python versions

This repository includes a `tox.ini` that runs the test suite on Linux for:

- Python 3.8 (`py38`)
- Python 3.11 (`py311`)
- Python 3.14 (`py314`)

Run all environments (will skip any missing interpreters):

```bash
tox
```

Run a specific Python version:

```bash
tox -e py311
```

If you are using Poetry:

```bash
poetry run tox
```

To run tox against a real Redis server (optional), set the same env vars used by pytest:

```bash
GRAPH_TEST_USE_REAL_REDIS=1 tox -e py311
```

### Optional: run tests against a real Redis server

If you want to validate behavior against a real Redis server, set:

- `GRAPH_TEST_USE_REAL_REDIS=1`

By default, it connects to `localhost:6379`, but you can override:

- `GRAPH_TEST_REDIS_HOST` (default: `localhost`)
- `GRAPH_TEST_REDIS_PORT` (default: `6379`)

Notes:

- `db=0` and `decode_responses=True` are intentionally fixed for the test suite.
- Tests clean up only the keys they create (scoped to the GraphManager's key patterns).

Example:

```bash
GRAPH_TEST_USE_REAL_REDIS=1 \
GRAPH_TEST_REDIS_HOST=localhost \
GRAPH_TEST_REDIS_PORT=6379 \
pytest
```

### Coverage

To generate coverage statistics (requires the `pytest-cov` plugin):

```bash
pytest --cov=redisgraph --cov-report=term-missing
```

To generate coverage statistics (requires the `pytest-cov` plugin):

```bash
pytest --cov=redisgraph --cov-report=term-missing
```

You can also generate an HTML coverage report. This will create an `htmlcov` directory with detailed coverage reports.

```bash
pytest --cov=redisgraph --cov-report=html:htmlcov
xdg-open htmlcov/index.html
```

For more details and advanced test scenarios, see the [tests](./tests/test_graph_manager.py) package in this repository.

## Code Style

Use [Black](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html) with pre-commit hooks for automatic formatting and linting. Ensure you have pre-commit installed and configured in your project. See the [.pre-commit-config.yaml](./.pre-commit-config.yaml) file for details. Trigger manually with:

```bash
git add . --all
pre-commit run  # Optionally use `--all-files` flag for the first time
```

## License

This is a demonstration project for educational purposes. It is provided "as is" without any warranties. Licensed under the MIT License. See [LICENSE](./LICENSE) for details.
