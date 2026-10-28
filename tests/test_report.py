from __future__ import annotations

import json

from hix.report import (
    exit_code,
    print_doctor,
    print_json,
    print_results,
    summary_payload,
)
from hix.runner import RunResult


def sample_results() -> list[RunResult]:
    return [
        RunResult(
            name="envaudit",
            status="fail",
            exit_code=2,
            duration_ms=1234,
            command="envaudit scan . --json --fail-on any",
            findings=2,
            summary={"total": 2, "critical": 1, "error": 1},
        ),
        RunResult(
            name="migration-guard",
            status="ok",
            exit_code=0,
            duration_ms=100,
            command="migration-guard check migrations",
            findings=0,
            summary={"findings": 0},
        ),
        RunResult(
            name="apiwatch",
            status="skipped",
            exit_code=None,
            duration_ms=0,
            command="",
            reason="no API Watch database",
            install="cargo install --git https://github.com/hix-pro/api-watch",
        ),
    ]


def test_table_columns_align(capsys) -> None:
    results = sample_results()
    print_results(results, no_color=True)
    output = capsys.readouterr().out
    lines = output.splitlines()

    width = max(len(result.name) for result in results)
    assert lines[0] == f"{'TOOL':<{width}}  {'STATUS':<7}  {'FINDINGS':>8}  {'TIME':>7}  DETAIL"
    assert lines[2] == (
        f"{'envaudit':<{width}}  {'fail':<7}  {'2':>8}  {'1.2s':>7}  critical 1, error 1"
    )
    assert lines[3] == (f"{'migration-guard':<{width}}  {'ok':<7}  {'0':>8}  {'0.1s':>7}  clean")
    assert lines[4] == (
        f"{'apiwatch':<{width}}  {'skipped':<7}  {'-':>8}  {'-':>7}  no API Watch database"
    )


def test_table_summary_and_rerun_hint(capsys) -> None:
    print_results(sample_results(), no_color=True)
    output = capsys.readouterr().out

    assert "3 tools · 1 ok · 1 failing · 1 skipped · 2 findings" in output
    assert "Run a tool directly for the full report:" in output
    assert "  $ envaudit scan . --json --fail-on any" in output


def test_verbose_prints_command(capsys) -> None:
    print_results(sample_results(), no_color=True, verbose=True)
    output = capsys.readouterr().out

    assert "$ migration-guard check migrations" in output


def test_all_skipped_explains_nothing_ran(capsys) -> None:
    results = [
        RunResult(
            name="envaudit",
            status="skipped",
            exit_code=None,
            duration_ms=0,
            command="",
            reason="envaudit is not on PATH",
        )
    ]
    print_results(results, no_color=True)
    output = capsys.readouterr().out

    assert "1 tool · 0 ok · 1 skipped · 0 findings" in output
    assert "Nothing ran. Install a tool or add [checks.*] to .hix.toml." in output


def test_summary_payload() -> None:
    assert summary_payload(sample_results()) == {
        "tools": 3,
        "ok": 1,
        "fail": 1,
        "error": 0,
        "skipped": 1,
        "findings": 2,
    }


def test_json_output_shape(capsys) -> None:
    print_json(sample_results(), root=".", include_report=True)
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == 1
    assert payload["root"] == "."
    assert [tool["name"] for tool in payload["tools"]] == [
        "envaudit",
        "migration-guard",
        "apiwatch",
    ]
    assert payload["tools"][2]["reason"] == "no API Watch database"
    assert payload["summary"]["findings"] == 2


def test_json_output_can_omit_reports(capsys) -> None:
    results = sample_results()
    results[0].report = {"summary": {"total": 2}}
    print_json(results, root=".", include_report=False)
    payload = json.loads(capsys.readouterr().out)

    assert "report" not in payload["tools"][0]


def test_exit_code_semantics() -> None:
    ok = RunResult("x", "ok", 0, 1, "x")
    fail = RunResult("y", "fail", 2, 1, "y", findings=1)
    error = RunResult("z", "error", 1, 1, "z")
    skipped = RunResult("s", "skipped", None, 0, "")

    assert exit_code([ok, skipped]) == 0
    assert exit_code([ok, fail]) == 1
    assert exit_code([ok, error]) == 1


def test_doctor_table(capsys) -> None:
    rows = [
        {"name": "envaudit", "status": "installed", "detail": "/usr/bin/envaudit"},
        {"name": "apiwatch", "status": "missing", "detail": "cargo install ..."},
        {"name": "config", "status": "none", "detail": "run `hix init`"},
    ]
    print_doctor(rows, no_color=True)
    output = capsys.readouterr().out

    assert "CHECK" in output
    assert "envaudit" in output
    assert "installed" in output
    assert "cargo install ..." in output


def test_color_is_off_when_not_a_tty(capsys, monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    print_results(sample_results())
    output = capsys.readouterr().out

    assert "\033[" not in output
