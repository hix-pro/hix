"""Run one tool and normalize its report."""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from .tools import PlanItem


@dataclass
class RunResult:
    name: str
    status: str
    exit_code: int | None
    duration_ms: int
    command: str
    findings: int = 0
    summary: dict = field(default_factory=dict)
    report: dict | list | None = None
    error: str = ""
    reason: str = ""
    install: str = ""

    def to_dict(self, include_report: bool = True) -> dict:
        payload = {
            "name": self.name,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "command": self.command,
            "findings": self.findings,
            "summary": self.summary,
            "error": self.error,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.install:
            payload["install"] = self.install
        if include_report and self.report is not None:
            payload["report"] = self.report
        return payload


def _parse_json(stdout: str) -> dict | list | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # A tool may print a warning before the JSON document. Use the first
        # balanced object only when the document clearly starts with one.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def summarize(name: str, report: dict | list | None) -> tuple[int, dict]:
    if not isinstance(report, dict):
        return 0, {}

    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}

    if name == "envaudit":
        return int(summary.get("total", 0)), summary
    if name == "migration-guard":
        return int(summary.get("findings", 0)), summary
    if name == "apiwatch":
        targets = report.get("targets")
        changes = 0
        if isinstance(targets, list):
            changes = sum(
                len(target.get("changes", [])) for target in targets if isinstance(target, dict)
            )
        else:
            changes = int(summary.get("breaking", 0)) + int(summary.get("compatible", 0))
        return changes, summary
    if name == "typeshift":
        return int(summary.get("total", 0)), summary

    findings = report.get("findings")
    if isinstance(findings, list):
        return len(findings), summary
    changes = report.get("changes")
    if isinstance(changes, list):
        return len(changes), summary
    if "findings" in summary:
        return int(summary.get("findings", 0)), summary
    if "total" in summary:
        return int(summary.get("total", 0)), summary
    return 0, summary


def _classify(exit_code: int | None, findings: int, timed_out: bool) -> str:
    if timed_out:
        return "error"
    if exit_code == 0:
        return "ok"
    if findings > 0:
        return "fail"
    return "error"


def _tail(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "…" + text[-limit:]


def run_item(item: PlanItem, timeout: float = 300.0) -> RunResult:
    if not item.runs:
        return RunResult(
            name=item.name,
            status="skipped",
            exit_code=None,
            duration_ms=0,
            command="",
            reason=item.reason or "not configured",
            install=item.install,
        )

    argv = list(item.argv or [])
    command = item.display_command()
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=item.cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        duration = int((time.perf_counter() - started) * 1000)
        report = _parse_json(completed.stdout)
        findings, summary = summarize(item.name, report)
        status = _classify(completed.returncode, findings, timed_out=False)
        error = "" if status != "error" else _tail(completed.stderr or completed.stdout)
        return RunResult(
            name=item.name,
            status=status,
            exit_code=completed.returncode,
            duration_ms=duration,
            command=command,
            findings=findings,
            summary=summary,
            report=report,
            error=error,
            install=item.install,
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - started) * 1000)
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        report = _parse_json(stdout)
        findings, summary = summarize(item.name, report)
        return RunResult(
            name=item.name,
            status="error",
            exit_code=None,
            duration_ms=duration,
            command=command,
            findings=findings,
            summary=summary,
            report=report,
            error=f"timed out after {timeout:g}s. {_tail(stderr)}".strip(),
            install=item.install,
        )
    except OSError as exc:
        duration = int((time.perf_counter() - started) * 1000)
        return RunResult(
            name=item.name,
            status="error",
            exit_code=None,
            duration_ms=duration,
            command=command,
            error=str(exc),
            install=item.install,
        )


def run_plan(
    plan: list[PlanItem],
    timeout: float = 300.0,
    jobs: int = 1,
    fail_fast: bool = False,
) -> list[RunResult]:
    """Run a plan, optionally in parallel, and return results in plan order."""

    if jobs <= 1 or len(plan) <= 1:
        results: list[RunResult] = []
        for item in plan:
            result = run_item(item, timeout=timeout)
            results.append(result)
            if fail_fast and result.status in {"fail", "error"}:
                break
        return results

    results: list[RunResult | None] = [None] * len(plan)
    pending = list(enumerate(plan))
    futures: dict = {}

    with ThreadPoolExecutor(max_workers=jobs) as executor:

        def submit_next() -> None:
            index, item = pending.pop(0)
            futures[executor.submit(run_item, item, timeout)] = index

        for _ in range(min(jobs, len(pending))):
            submit_next()

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                index = futures.pop(future)
                result = future.result()
                results[index] = result
                if fail_fast and result.status in {"fail", "error"}:
                    for other in futures:
                        other.cancel()
                    return [item for item in results if item is not None]
                if pending:
                    submit_next()

    return [item for item in results if item is not None]
