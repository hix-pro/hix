# Changelog

All notable changes to `hix` are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-28

### Added

- PlanGuard support: the auto plan runs `planguard review` with `--fail-on error` when `.planguard/plan.json`, `plan.json`, or `tfplan.json` exists.
- `hix doctor` reports PlanGuard and whether a Terraform plan JSON file was found.
- `hix init` writes an active `[checks.planguard]` entry when a plan exists and a commented example otherwise.
- README examples now show the six-tool plan and the PlanGuard count mapping.

## [0.2.0] - 2026-10-28

### Added

- LockLens support: `hix doctor` reports it, the auto plan explains when it needs an explicit pair, and `hix init` writes a commented `[checks.locklens]` example.
- README examples now show the five-tool plan and the LockLens count mapping.

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

[0.3.0]: https://github.com/hix-pro/hix/releases/tag/v0.3.0
[0.2.0]: https://github.com/hix-pro/hix/releases/tag/v0.2.0
[0.1.0]: https://github.com/hix-pro/hix/releases/tag/v0.1.0
