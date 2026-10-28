"""Discover tools, migration directories, and build the run plan."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = {
    "envaudit": {
        "binary": "envaudit",
        "install": "cargo install --git https://github.com/hix-pro/env-audit",
    },
    "migration-guard": {
        "binary": "migration-guard",
        "install": "cargo install --git https://github.com/hix-pro/migration-guard",
    },
    "apiwatch": {
        "binary": "apiwatch",
        "install": "cargo install --git https://github.com/hix-pro/api-watch",
    },
    "typeshift": {
        "binary": "typeshift",
        "install": (
            "git clone https://github.com/hix-pro/typeshift && cd typeshift "
            "&& npm ci && npm run build && npm link"
        ),
    },
}

MIGRATION_DIRS = (
    "migrations",
    "db/migrate",
    "database/migrations",
    "prisma/migrations",
    "supabase/migrations",
    "alembic/versions",
)


@dataclass
class PlanItem:
    """A tool that will run, or a reason it will not."""

    name: str
    argv: list[str] | None = None
    reason: str | None = None
    install: str = ""
    cwd: Path = field(default_factory=Path)

    @property
    def runs(self) -> bool:
        return self.argv is not None

    def display_command(self) -> str:
        if not self.argv:
            return ""
        return " ".join(shlex.quote(part) for part in self.argv)


def find_config(root: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    for name in (".hix.toml", "hix.toml"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def find_migrations(root: Path) -> Path | None:
    for relative in MIGRATION_DIRS:
        candidate = root / relative
        if not candidate.is_dir():
            continue
        if any(candidate.rglob("*.sql")):
            return candidate
    return None


def load_config(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"could not read {path}: {error}") from error


def _config_plan(root: Path, path: Path) -> list[PlanItem]:
    data = load_config(path)
    checks = data.get("checks")
    if not isinstance(checks, dict):
        raise RuntimeError(f"{path} has no [checks] table")

    plan: list[PlanItem] = []
    for name, entry in checks.items():
        if not isinstance(entry, dict):
            continue
        install = TOOLS.get(name, {}).get("install", "")
        if entry.get("enabled", True) is False:
            plan.append(PlanItem(name=name, reason="disabled in config", install=install))
            continue
        command = entry.get("command")
        if not isinstance(command, str) or not command.strip():
            plan.append(PlanItem(name=name, reason="no command in config", install=install))
            continue
        cwd = (root / str(entry.get("cwd", "."))).resolve()
        plan.append(
            PlanItem(
                name=name,
                argv=shlex.split(command),
                install=install,
                cwd=cwd,
            )
        )
    return plan


def _which(binary: str) -> str | None:
    return shutil.which(binary)


def auto_plan(root: Path) -> list[PlanItem]:
    plan: list[PlanItem] = []

    for name in ("envaudit", "migration-guard", "apiwatch"):
        info = TOOLS[name]
        if not _which(info["binary"]):
            plan.append(
                PlanItem(
                    name=name,
                    reason=f"{info['binary']} is not on PATH",
                    install=info["install"],
                )
            )

    envaudit = _which("envaudit")
    if envaudit:
        plan.append(
            PlanItem(
                name="envaudit",
                argv=["envaudit", "scan", ".", "--json", "--fail-on", "any"],
                cwd=root,
                install=TOOLS["envaudit"]["install"],
            )
        )

    guard = _which("migration-guard")
    if guard:
        migrations = find_migrations(root)
        if migrations:
            plan.append(
                PlanItem(
                    name="migration-guard",
                    argv=[
                        "migration-guard",
                        "check",
                        str(migrations.relative_to(root)),
                        "--format",
                        "json",
                        "--fail-on",
                        "risky",
                    ],
                    cwd=root,
                    install=TOOLS["migration-guard"]["install"],
                )
            )
        else:
            plan.append(
                PlanItem(
                    name="migration-guard",
                    reason="no migrations directory found",
                    install=TOOLS["migration-guard"]["install"],
                )
            )

    apiwatch = _which("apiwatch")
    if apiwatch:
        db = Path(os.environ.get("APIWATCH_DB", "~/.apiwatch/apiwatch.db")).expanduser()
        if db.is_file():
            plan.append(
                PlanItem(
                    name="apiwatch",
                    argv=["apiwatch", "check", "--json", "--fail-on-breaking"],
                    cwd=root,
                    install=TOOLS["apiwatch"]["install"],
                )
            )
        else:
            plan.append(
                PlanItem(
                    name="apiwatch",
                    reason="no API Watch database; run `apiwatch add` first",
                    install=TOOLS["apiwatch"]["install"],
                )
            )

    typeshift = _which("typeshift")
    plan.append(
        PlanItem(
            name="typeshift",
            reason=(
                "needs a source pair; add [checks.typeshift] to .hix.toml"
                if typeshift
                else "typeshift is not on PATH"
            ),
            install=TOOLS["typeshift"]["install"],
        )
    )

    return plan


def build_plan(
    root: Path,
    config_path: str | None = None,
    only: list[str] | None = None,
) -> tuple[list[PlanItem], Path | None]:
    root = root.resolve()
    config = find_config(root, config_path)
    if config_path and config is None:
        raise RuntimeError(f"config not found: {config_path}")
    plan = _config_plan(root, config) if config else auto_plan(root)

    if only:
        wanted = {name.strip() for name in only if name.strip()}
        plan = [item for item in plan if item.name in wanted]

    return plan, config


def tool_version(binary: str) -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    line = (result.stdout or result.stderr).strip().splitlines()
    return line[0] if line else "unknown"


def doctor(root: Path, config_path: str | None = None) -> list[dict[str, str]]:
    root = root.resolve()
    config = find_config(root, config_path)
    migrations = find_migrations(root)
    db = Path(os.environ.get("APIWATCH_DB", "~/.apiwatch/apiwatch.db")).expanduser()
    rows: list[dict[str, str]] = []

    for name, info in TOOLS.items():
        path = _which(info["binary"])
        rows.append(
            {
                "name": name,
                "status": "installed" if path else "missing",
                "detail": f"{path} · {tool_version(path)}" if path else info["install"],
            }
        )

    rows.append(
        {
            "name": "config",
            "status": "found" if config else "none",
            "detail": str(config) if config else "run `hix init` to create .hix.toml",
        }
    )
    rows.append(
        {
            "name": "migrations",
            "status": "found" if migrations else "none",
            "detail": str(migrations.relative_to(root))
            if migrations
            else "no .sql migrations detected",
        }
    )
    rows.append(
        {
            "name": "apiwatch db",
            "status": "found" if db.is_file() else "none",
            "detail": str(db),
        }
    )
    return rows


def init_config(root: Path) -> str:
    root = root.resolve()
    plan = auto_plan(root)
    lines = [
        "# hix check configuration",
        "# Docs: https://github.com/hix-pro/hix",
        "# Commands run from the repository root unless `cwd` is set.",
        "",
    ]

    written = False
    for item in plan:
        if not item.runs:
            continue
        argv = list(item.argv or [])
        binary = TOOLS.get(item.name, {}).get("binary")
        if binary and argv and Path(argv[0]).name == binary:
            argv[0] = binary
        command = " ".join(shlex.quote(part) for part in argv)
        lines.extend(
            [
                f"[checks.{item.name}]",
                f"command = {json.dumps(command)}",
                "enabled = true",
                "",
            ]
        )
        written = True

    if not written:
        lines.extend(
            [
                "# No hix tools were found on PATH.",
                "# Install one, then run `hix init` again.",
                "",
            ]
        )

    lines.extend(
        [
            "# TypeShift needs an explicit source pair.",
            "# [checks.typeshift]",
            '# command = "typeshift compare ./types/v1 ./types/v2 '
            '--from 1.2.3 --to 1.3.0 --json --fail-on-breaking"',
            "# enabled = true",
            "",
        ]
    )
    return "\n".join(lines)
