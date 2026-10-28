# hix

[![CI](https://github.com/hix-pro/hix/actions/workflows/ci.yml/badge.svg)](https://github.com/hix-pro/hix/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-3fb950.svg)](LICENSE)

**One command to run the [hix tools](https://github.com/topics/hix-tools) suite.**

`hix` is a small Python CLI that finds the hix tools installed on your machine, builds a check plan for the current repository, runs them, and gives you one table and one exit code. It does not install anything, call a server, or send telemetry.

```console
$ hix check
TOOL             STATUS   FINDINGS     TIME  DETAIL
----------------------------------------------------------------------
envaudit         fail            1     0.2s  critical 1
migration-guard  ok              0     0.1s  clean
apiwatch         skipped         -        -  no API Watch database; run `apiwatch add` first
typeshift        skipped         -        -  needs a source pair; add [checks.typeshift] to .hix.toml
locklens         skipped         -        -  needs a source pair; add [checks.locklens] to .hix.toml

5 tools · 1 ok · 1 failing · 3 skipped · 1 finding

Run a tool directly for the full report:
  $ envaudit scan . --json --fail-on any
```

## Install

From source:

```bash
pipx install git+https://github.com/hix-pro/hix.git
```

After the first PyPI release:

```bash
pipx install hix-cli
```

`pipx` keeps the CLI isolated. Plain `pip` works too:

```bash
python3 -m pip install --user git+https://github.com/hix-pro/hix.git
```

For development:

```bash
git clone https://github.com/hix-pro/hix
cd hix
python3 -m pip install -e ".[dev]"
```

Requires Python 3.11 or newer. No runtime dependencies.

## Quick start

```console
$ cd your-repo
$ hix doctor          # what is installed and what hix can see
$ hix check           # run the detected checks
$ hix init            # write .hix.toml from the current plan
```

Run `hix check` before `.hix.toml` exists to see the auto-detected plan. Commit the generated config when you want the plan to be explicit and reproducible.

## What runs by default

Without a config file, `hix` looks for five tools on `PATH` and applies these rules:

| Tool | Runs when | Command |
| --- | --- | --- |
| `envaudit` | always, if installed | `envaudit scan . --json --fail-on any` |
| `migration-guard` | a migrations directory contains `.sql` files | `migration-guard check <dir> --format json --fail-on risky` |
| `apiwatch` | an API Watch database exists | `apiwatch check --json --fail-on-breaking` |
| `typeshift` | only from `.hix.toml` | needs an explicit old/new pair |
| `locklens` | only from `.hix.toml` | needs an explicit old/new lockfile pair |

Migration directories are searched in this order: `migrations`, `db/migrate`, `database/migrations`, `prisma/migrations`, `supabase/migrations`, `alembic/versions`.

API Watch uses `~/.apiwatch/apiwatch.db` unless `APIWATCH_DB` points elsewhere. If no database exists, the check is skipped with the command to create one.

TypeShift and LockLens cannot guess which two versions or lockfiles to compare, so `hix init` leaves commented examples instead of inventing them.

## Configuration

`.hix.toml` is optional. When present, hix runs the commands exactly as written and does not auto-detect anything.

```toml
# .hix.toml
[checks.envaudit]
command = "envaudit scan . --json --fail-on any"
enabled = true

[checks.migration-guard]
command = "migration-guard check db/migrations --format json --fail-on risky"
enabled = true
cwd = "services/api"

[checks.typeshift]
command = "typeshift compare ./types/v1 ./types/v2 --from 1.2.3 --to 1.3.0 --json --fail-on-breaking"
enabled = true

[checks.locklens]
command = "locklens diff .locklens/base/package-lock.json package-lock.json --fail-on warning --json"
enabled = true
```

| Key | Default | Meaning |
| --- | --- | --- |
| `command` | required | Shell-like command line, parsed with POSIX quoting rules |
| `enabled` | `true` | Set to `false` to keep a check documented but skipped |
| `cwd` | repository root | Working directory, relative to the repository |

Commands are executed directly, not through a shell. Pipes, redirects, and `&&` are not interpreted; put those in a script and call the script instead.

`hix init` writes the detected commands, then adds commented TypeShift and LockLens examples. Existing configs are never overwritten unless you pass `--force`.

## Commands

### `hix check [PATH]`

Run the plan for `PATH` (default `.`).

| Option | Meaning |
| --- | --- |
| `--config FILE` | Use this config instead of searching for `.hix.toml` or `hix.toml` |
| `--only TOOL` | Run only this tool; repeat for several |
| `--timeout SECONDS` | Per-tool timeout (default `300`) |
| `--jobs N` | Run up to `N` tools at once (default `4`) |
| `--fail-fast` | Stop after the first failing or errored tool |
| `--json` | Write one JSON document to stdout |
| `--no-report` | Omit nested tool reports from `--json` output |
| `--verbose` | Print the exact command for each tool |
| `--no-color` | Disable ANSI colors |

Tools run in parallel by default. Results are always printed in plan order, not completion order.

### `hix doctor [PATH]`

Show each tool's path and version, whether a config was found, whether a migrations directory was found, and whether the API Watch database exists.

```console
$ hix doctor
CHECK            STATUS      DETAIL
------------------------------------------------------------------------
envaudit         installed   /usr/local/bin/envaudit · envaudit 0.3.1
migration-guard  installed   /usr/local/bin/migration-guard · migration-guard 0.2.0
apiwatch         missing     cargo install --git https://github.com/hix-pro/api-watch
typeshift        missing     git clone https://github.com/hix-pro/typeshift && cd typeshift && npm ci && npm run build && npm link
locklens         missing     cargo install --git https://github.com/hix-pro/locklens
config           none        run `hix init` to create .hix.toml
migrations       found       db/migrations
apiwatch db      none        /home/you/.apiwatch/apiwatch.db
```

`--json` is available for scripts.

### `hix init [PATH]`

Write `.hix.toml` from the auto-detected plan. `--print` writes the config to stdout instead. `--force` overwrites an existing file.

### `hix version`

Print `hix 0.2.0`. `--json` returns `{"name": "hix", "version": "0.2.0"}`.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Every selected tool passed, or was skipped |
| `1` | At least one tool failed or errored |
| `2` | Usage, config, or path error |

`fail` means the tool exited non-zero and its report contained findings. `error` means the tool exited non-zero without a parseable finding count, timed out, or could not start. The distinction matters: a broken tool should not look like a clean repository.

## JSON output

`hix check --json` writes one stable document to stdout. Diagnostics go to stderr.

```json
{
  "schema_version": 1,
  "root": ".",
  "tools": [
    {
      "name": "envaudit",
      "status": "fail",
      "exit_code": 2,
      "duration_ms": 184,
      "command": "envaudit scan . --json --fail-on any",
      "findings": 1,
      "summary": {
        "total": 1,
        "critical": 0,
        "error": 1,
        "warning": 0,
        "info": 0
      },
      "error": ""
    },
    {
      "name": "apiwatch",
      "status": "skipped",
      "exit_code": null,
      "duration_ms": 0,
      "command": "",
      "findings": 0,
      "summary": {},
      "error": "",
      "reason": "no API Watch database; run `apiwatch add` first",
      "install": "cargo install --git https://github.com/hix-pro/api-watch"
    }
  ],
  "summary": {
    "tools": 2,
    "ok": 0,
    "fail": 1,
    "error": 0,
    "skipped": 1,
    "findings": 1
  }
}
```

Finding counts are read from each tool's own summary:

| Tool | Count |
| --- | --- |
| EnvAudit | `summary.total` |
| Migration Guard | `summary.findings` |
| API Watch | total `changes` across targets, or `breaking + compatible` |
| TypeShift | `summary.total` |
| LockLens | `summary.total` |

An unrecognized report falls back to counting `findings` or `changes` arrays. If none of those exist, the tool's exit code still decides between `ok` and `error`.

## In CI

```yaml
name: hix

on:
  push:
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: dtolnay/rust-toolchain@stable
      - run: cargo install --git https://github.com/hix-pro/env-audit --locked
      - run: cargo install --git https://github.com/hix-pro/migration-guard --locked

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pipx install git+https://github.com/hix-pro/hix.git

      - run: hix check --json | tee hix-report.json

      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: hix-report
          path: hix-report.json
```

Cache the Cargo installs in a real workflow; the example is shortened for readability. Each underlying tool also ships its own composite GitHub Action if you only need one check.

## Design

- **Local-first.** No backend, account, telemetry, or network call of its own.
- **One exit code.** The suite fails when any selected check fails, not when the first one does.
- **Honest status.** A missing tool is `skipped`, not `ok`.
- **No hidden installs.** `hix` prints the install command and moves on.
- **Stable output.** JSON is versioned and sorted by the plan, not by completion time.

## Related

- [EnvAudit](https://github.com/hix-pro/env-audit) — env vars that are missing, unused, undocumented, or hiding a secret
- [Migration Guard](https://github.com/hix-pro/migration-guard) — destructive SQL and blocking DDL before it reaches a database
- [API Watch](https://github.com/hix-pro/api-watch) — OpenAPI and JSON contract diffs
- [TypeShift](https://github.com/hix-pro/typeshift) — semantic TypeScript declaration diffs
- [LockLens](https://github.com/hix-pro/locklens) — lockfile upgrades, downgrades, and checksum or source drift
- [All hix tools](https://github.com/topics/hix-tools)

## License

MIT. See [LICENSE](LICENSE).
