from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from hix.tools import (
    PlanItem,
    build_plan,
    doctor,
    find_config,
    find_migrations,
    find_plan,
    init_config,
    load_config,
    tool_version,
)


def test_find_migrations_requires_sql_files(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "README.md").write_text("notes", encoding="utf-8")
    assert find_migrations(tmp_path) is None

    (tmp_path / "migrations" / "001_init.sql").write_text("select 1;", encoding="utf-8")
    assert find_migrations(tmp_path) == tmp_path / "migrations"


def test_find_migrations_prefers_earlier_known_directory(tmp_path: Path) -> None:
    (tmp_path / "db" / "migrate").mkdir(parents=True)
    (tmp_path / "db" / "migrate" / "001.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("select 1;", encoding="utf-8")

    assert find_migrations(tmp_path) == tmp_path / "migrations"


def test_find_plan_prefers_the_tool_directory(tmp_path: Path) -> None:
    assert find_plan(tmp_path) is None

    (tmp_path / "plan.json").write_text("{}", encoding="utf-8")
    assert find_plan(tmp_path) == tmp_path / "plan.json"

    (tmp_path / ".planguard").mkdir()
    (tmp_path / ".planguard" / "plan.json").write_text("{}", encoding="utf-8")
    assert find_plan(tmp_path) == tmp_path / ".planguard" / "plan.json"

    (tmp_path / ".planguard" / "plan.json").unlink()
    (tmp_path / "plan.json").unlink()
    (tmp_path / "tfplan.json").write_text("{}", encoding="utf-8")
    assert find_plan(tmp_path) == tmp_path / "tfplan.json"


def test_find_config_prefers_dot_hix(tmp_path: Path) -> None:
    (tmp_path / "hix.toml").write_text("[checks]\n", encoding="utf-8")
    (tmp_path / ".hix.toml").write_text("[checks]\n", encoding="utf-8")

    assert find_config(tmp_path) == tmp_path / ".hix.toml"


def test_find_config_explicit_missing_returns_none(tmp_path: Path) -> None:
    assert find_config(tmp_path, str(tmp_path / "missing.toml")) is None


def test_load_config_reports_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / ".hix.toml"
    path.write_text("[checks.envaudit\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="could not read"):
        load_config(path)


def test_build_plan_uses_config_commands_and_cwd(tmp_path: Path) -> None:
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / ".hix.toml").write_text(
        """
[checks.envaudit]
command = "envaudit scan . --json --fail-on any"
enabled = true

[checks.migration-guard]
command = "migration-guard check db/migrations --format json"
cwd = "services/api"

[checks.typeshift]
enabled = false
""",
        encoding="utf-8",
    )

    plan, config = build_plan(tmp_path)

    assert config == tmp_path / ".hix.toml"
    assert [item.name for item in plan] == [
        "envaudit",
        "migration-guard",
        "typeshift",
    ]
    assert plan[0].argv == ["envaudit", "scan", ".", "--json", "--fail-on", "any"]
    assert plan[0].cwd == tmp_path
    assert plan[1].argv[0] == "migration-guard"
    assert plan[1].cwd == (tmp_path / "services" / "api").resolve()
    assert not plan[2].runs
    assert plan[2].reason == "disabled in config"


def test_build_plan_only_filters(tmp_path: Path) -> None:
    (tmp_path / ".hix.toml").write_text(
        """
[checks.one]
command = "one"
[checks.two]
command = "two"
""",
        encoding="utf-8",
    )

    plan, _ = build_plan(tmp_path, only=["two"])
    assert [item.name for item in plan] == ["two"]


def test_build_plan_missing_explicit_config_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="config not found"):
        build_plan(tmp_path, config_path="nope.toml")


def test_config_without_checks_table_raises(tmp_path: Path) -> None:
    (tmp_path / ".hix.toml").write_text('title = "x"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="no \\[checks\\] table"):
        build_plan(tmp_path)


def test_auto_plan_skips_missing_tools(tmp_path: Path) -> None:
    with patch("hix.tools._which", return_value=None):
        plan, config = build_plan(tmp_path)

    assert config is None
    assert [item.name for item in plan] == [
        "envaudit",
        "migration-guard",
        "apiwatch",
        "planguard",
        "typeshift",
        "locklens",
    ]
    assert all(not item.runs for item in plan)
    assert "not on PATH" in (plan[0].reason or "")
    assert "not on PATH" in (plan[3].reason or "")
    assert "not on PATH" in (plan[4].reason or "")
    assert "not on PATH" in (plan[5].reason or "")


def test_auto_plan_detects_installed_tools(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("select 1;", encoding="utf-8")
    db = tmp_path / "apiwatch.db"
    db.write_text("", encoding="utf-8")

    def fake_which(binary: str) -> str | None:
        return f"/usr/local/bin/{binary}"

    with (
        patch("hix.tools._which", side_effect=fake_which),
        patch.dict(os.environ, {"APIWATCH_DB": str(db)}),
    ):
        plan, _ = build_plan(tmp_path)

    by_name = {item.name: item for item in plan}
    assert by_name["envaudit"].argv == [
        "envaudit",
        "scan",
        ".",
        "--json",
        "--fail-on",
        "any",
    ]
    assert by_name["migration-guard"].argv is not None
    assert "migrations" in by_name["migration-guard"].argv
    assert by_name["apiwatch"].argv is not None
    assert "--fail-on-breaking" in by_name["apiwatch"].argv
    assert not by_name["planguard"].runs
    assert "Terraform plan" in (by_name["planguard"].reason or "")
    assert not by_name["typeshift"].runs
    assert not by_name["locklens"].runs
    assert "checks.locklens" in (by_name["locklens"].reason or "")


def test_auto_plan_runs_planguard_when_a_plan_exists(tmp_path: Path) -> None:
    (tmp_path / ".planguard").mkdir()
    (tmp_path / ".planguard" / "plan.json").write_text("{}", encoding="utf-8")

    with patch("hix.tools._which", return_value="/usr/bin/planguard"):
        plan, _ = build_plan(tmp_path)

    planguard = next(item for item in plan if item.name == "planguard")
    assert planguard.argv == [
        "planguard",
        "review",
        ".planguard/plan.json",
        "--json",
        "--fail-on",
        "error",
    ]
    assert planguard.cwd == tmp_path.resolve()


def test_auto_plan_skips_migrations_without_sql(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "notes.md").write_text("x", encoding="utf-8")

    with patch("hix.tools._which", return_value="/usr/bin/migration-guard"):
        plan, _ = build_plan(tmp_path)

    guard = next(item for item in plan if item.name == "migration-guard")
    assert not guard.runs
    assert guard.reason == "no migrations directory found"


def test_auto_plan_skips_apiwatch_without_database(tmp_path: Path) -> None:
    with (
        patch("hix.tools._which", return_value="/usr/bin/apiwatch"),
        patch.dict(os.environ, {"APIWATCH_DB": str(tmp_path / "missing.db")}),
    ):
        plan, _ = build_plan(tmp_path)

    apiwatch = next(item for item in plan if item.name == "apiwatch")
    assert not apiwatch.runs
    assert "apiwatch add" in (apiwatch.reason or "")


def test_init_config_uses_short_binary_names(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("select 1;", encoding="utf-8")
    db = tmp_path / "apiwatch.db"
    db.write_text("", encoding="utf-8")

    def fake_which(binary: str) -> str | None:
        return f"/opt/hix/bin/{binary}"

    with (
        patch("hix.tools._which", side_effect=fake_which),
        patch.dict(os.environ, {"APIWATCH_DB": str(db)}),
    ):
        content = init_config(tmp_path)

    assert "[checks.envaudit]" in content
    assert '[checks.envaudit]\ncommand = "envaudit scan . --json --fail-on any"' in content
    assert "/opt/hix/bin" not in content
    assert "# [checks.typeshift]" in content
    assert "typeshift compare" in content
    assert "\n[checks.typeshift]\n" not in content
    assert "# [checks.locklens]" in content
    assert "locklens diff" in content
    assert "\n[checks.locklens]\n" not in content
    assert "# [checks.planguard]" in content
    assert "planguard review" in content
    assert "\n[checks.planguard]\n" not in content


def test_init_config_without_tools_explains_what_to_do(tmp_path: Path) -> None:
    with patch("hix.tools._which", return_value=None):
        content = init_config(tmp_path)

    assert "No hix tools were found on PATH." in content
    assert "run `hix init` again" in content


def test_doctor_reports_missing_tools_and_state(tmp_path: Path) -> None:
    with (
        patch("hix.tools._which", return_value=None),
        patch.dict(os.environ, {"APIWATCH_DB": str(tmp_path / "missing.db")}),
    ):
        rows = doctor(tmp_path)

    by_name = {row["name"]: row for row in rows}
    assert by_name["envaudit"]["status"] == "missing"
    assert "cargo install" in by_name["envaudit"]["detail"]
    assert by_name["config"]["status"] == "none"
    assert by_name["migrations"]["status"] == "none"
    assert by_name["plan"]["status"] == "none"
    assert by_name["apiwatch db"]["status"] == "none"


def test_doctor_reports_found_entries(tmp_path: Path) -> None:
    (tmp_path / ".hix.toml").write_text("[checks]\n", encoding="utf-8")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "plan.json").write_text("{}", encoding="utf-8")
    db = tmp_path / "apiwatch.db"
    db.write_text("", encoding="utf-8")

    with (
        patch("hix.tools._which", return_value="/usr/bin/envaudit"),
        patch("hix.tools.tool_version", return_value="envaudit 0.3.1"),
        patch.dict(os.environ, {"APIWATCH_DB": str(db)}),
    ):
        rows = doctor(tmp_path)

    by_name = {row["name"]: row for row in rows}
    assert by_name["envaudit"]["status"] == "installed"
    assert "0.3.1" in by_name["envaudit"]["detail"]
    assert by_name["config"]["status"] == "found"
    assert by_name["migrations"]["status"] == "found"
    assert by_name["plan"]["status"] == "found"
    assert by_name["plan"]["detail"] == "plan.json"
    assert by_name["apiwatch db"]["status"] == "found"


def test_tool_version_handles_unknown_binary(tmp_path: Path) -> None:
    assert tool_version(str(tmp_path / "does-not-exist")) == "unknown"


def test_plan_item_display_command_quotes_spaces(tmp_path: Path) -> None:
    item = PlanItem(name="x", argv=["tool", "path with spaces"], cwd=tmp_path)
    assert item.display_command() == "tool 'path with spaces'"
