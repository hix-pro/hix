# Changelog

All notable changes to `hix` are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-28

### Added

- `hix check` runs EnvAudit, Migration Guard, API Watch, and TypeShift from one plan.
- Auto-detection for installed tools, SQL migration directories, and the API Watch database.
- `.hix.toml` configuration with per-check `command`, `enabled`, and `cwd`.
- `hix init` writes a config from the detected plan; `--print` and `--force` supported.
- `hix doctor` reports tool paths, versions, config, migrations, and database state.
- `hix version` with optional JSON.
- One table with per-tool status, finding count, duration, and detail.
- Parallel execution with `--jobs`, per-tool `--timeout`, `--only`, and `--fail-fast`.
- Versioned JSON output with nested tool reports and a summary.
- Distinct `fail` and `error` states; missing tools are `skipped`, never `ok`.
- Python 3.11+ package, typed public modules, MIT license.

[0.1.0]: https://github.com/hix-pro/hix/releases/tag/v0.1.0
