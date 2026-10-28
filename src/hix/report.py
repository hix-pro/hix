"""Human and machine output for hix."""

from __future__ import annotations

import json
import os
import shutil
import sys

from .runner import RunResult

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"

STATUS_COLORS = {
    "ok": GREEN,
    "fail": RED,
    "error": YELLOW,
    "skipped": DIM,
}


def color_enabled(no_color: bool = False) -> bool:
    return (
        not no_color
        and "NO_COLOR" not in os.environ
        and sys.stdout.isatty()
        and os.environ.get("TERM", "") != "dumb"
    )


def paint(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{RESET}" if enabled else text


def status_label(status: str, enabled: bool) -> str:
    labels = {
        "ok": "ok",
        "fail": "fail",
        "error": "error",
        "skipped": "skipped",
    }
    return paint(labels.get(status, status), STATUS_COLORS.get(status, ""), enabled)


def _detail(result: RunResult) -> str:
    if result.status == "skipped":
        return result.reason
    if result.error:
        return result.error.splitlines()[0]
    summary = result.summary
    if result.name == "apiwatch" and summary:
        parts = []
        for key in ("breaking", "compatible", "errors"):
            value = summary.get(key)
            if isinstance(value, int) and value:
                parts.append(f"{key} {value}")
        return ", ".join(parts)
    if result.name == "envaudit" and summary:
        parts = []
        for key in ("critical", "error", "warning", "info"):
            value = summary.get(key)
            if isinstance(value, int) and value:
                parts.append(f"{key} {value}")
        return ", ".join(parts)
    if result.name == "typeshift" and summary:
        parts = []
        for key in ("breaking", "compatible"):
            value = summary.get(key)
            if isinstance(value, int) and value:
                parts.append(f"{key} {value}")
        return ", ".join(parts)
    if result.findings:
        return f"{result.findings} finding{'s' if result.findings != 1 else ''}"
    return "clean"


def print_results(results: list[RunResult], no_color: bool = False, verbose: bool = False) -> None:
    enabled = color_enabled(no_color)
    width = max([len(result.name) for result in results] + [4])
    header = f"{'TOOL':<{width}}  {'STATUS':<7}  {'FINDINGS':>8}  {'TIME':>7}  DETAIL"
    print(paint(header, DIM, enabled))
    print(paint("-" * min(100, len(header) + 20), DIM, enabled))

    for result in results:
        findings = "-" if result.status == "skipped" else str(result.findings)
        elapsed = "-" if result.status == "skipped" else f"{result.duration_ms / 1000:.1f}s"
        detail = _detail(result)
        label = result.status.ljust(7)
        colored = paint(label, STATUS_COLORS.get(result.status, ""), enabled)
        print(f"{result.name:<{width}}  {colored}  {findings:>8}  {elapsed:>7}  {detail}")
        if verbose and result.command:
            print(paint(f"{'':<{width}}  $ {result.command}", DIM, enabled))

    print()
    ok = sum(1 for result in results if result.status == "ok")
    fail = sum(1 for result in results if result.status == "fail")
    errors = sum(1 for result in results if result.status == "error")
    skipped = sum(1 for result in results if result.status == "skipped")
    findings = sum(result.findings for result in results)

    parts = [f"{len(results)} tool{'s' if len(results) != 1 else ''}", f"{ok} ok"]
    if fail:
        parts.append(paint(f"{fail} failing", RED, enabled))
    if errors:
        parts.append(paint(f"{errors} error", YELLOW, enabled))
    if skipped:
        parts.append(f"{skipped} skipped")
    parts.append(f"{findings} finding{'s' if findings != 1 else ''}")
    print(" · ".join(parts))

    if fail or errors:
        print()
        print(paint("Run a tool directly for the full report:", DIM, enabled))
        for result in results:
            if result.status in {"fail", "error"} and result.command:
                print(paint(f"  $ {result.command}", DIM, enabled))
    elif not ok:
        print()
        print(
            paint(
                "Nothing ran. Install a tool or add [checks.*] to .hix.toml.",
                DIM,
                enabled,
            )
        )


def summary_payload(results: list[RunResult]) -> dict:
    return {
        "tools": len(results),
        "ok": sum(1 for result in results if result.status == "ok"),
        "fail": sum(1 for result in results if result.status == "fail"),
        "error": sum(1 for result in results if result.status == "error"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
        "findings": sum(result.findings for result in results),
    }


def print_json(results: list[RunResult], root: str, include_report: bool = True) -> None:
    payload = {
        "schema_version": 1,
        "root": root,
        "tools": [result.to_dict(include_report=include_report) for result in results],
        "summary": summary_payload(results),
    }
    print(json.dumps(payload, indent=2, sort_keys=False))


def print_doctor(rows: list[dict[str, str]], no_color: bool = False) -> None:
    enabled = color_enabled(no_color)
    width = max([len(row["name"]) for row in rows] + [6])
    print(paint(f"{'CHECK':<{width}}  {'STATUS':<10}  DETAIL", DIM, enabled))
    print(paint("-" * 72, DIM, enabled))
    for row in rows:
        status = row["status"]
        code = GREEN if status in {"installed", "found"} else DIM
        print(f"{row['name']:<{width}}  {paint(f'{status:<10}', code, enabled)}  {row['detail']}")


def exit_code(results: list[RunResult]) -> int:
    if any(result.status in {"fail", "error"} for result in results):
        return 1
    return 0


def terminal_width(default: int = 100) -> int:
    return shutil.get_terminal_size((default, 24)).columns
