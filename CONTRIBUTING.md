# Contributing to hix

Thanks for taking the time to improve `hix`.

## Setup

```bash
git clone https://github.com/hix-pro/hix
cd hix
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Requires Python 3.11 or newer.

## Checks

Run the same checks CI runs:

```bash
ruff check .
ruff format --check .
pytest -q
```

Apply formatting with `ruff format .`.

## What belongs here

`hix` is the umbrella runner, not a reimplementation of the tools. Good changes:

- Better detection of an existing tool, config, or migration layout
- Clearer status, table, or JSON output
- Safer process handling: timeouts, signals, missing binaries
- Tests for every new branch in plan building or report classification

Out of scope:

- Installing tools automatically
- Network calls, telemetry, accounts, or a backend
- Guessing which TypeShift versions to compare
- Hiding a failing tool behind a zero exit code

## Pull requests

- Keep a change focused and add tests.
- Update `README.md` when behavior or output changes.
- Add an entry under `Unreleased` in `CHANGELOG.md` for user-visible changes.
- Run `ruff check .`, `ruff format --check .`, and `pytest -q` before opening the PR.

## Releasing

1. Update the version in `pyproject.toml` and `src/hix/__init__.py`.
2. Move the changelog entries under the new version and date.
3. Commit, tag `vX.Y.Z`, and push the tag.
4. Publish a GitHub release. `.github/workflows/publish.yml` builds the sdist and wheel and uploads them to PyPI with trusted publishing.

The first release needs a pending publisher on PyPI for `hix-cli`, owned by `hix-pro`, repository `hix`, workflow `publish.yml`, environment `pypi`. No API token is stored in the repository.
