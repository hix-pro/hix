from __future__ import annotations

import json
import sys
from pathlib import Path

from hix.runner import (
    RunResult,
    _classify,
    _parse_json,
    run_item,
    run_plan,
    summarize,
)
from hix.tools import PlanItem


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_parse_json_accepts_plain_document() -> None:
    assert _parse_json('{"summary": {"total": 1}}') == {"summary": {"total": 1}}


def test_parse_json_skips_leading_warning() -> None:
    assert _parse_json('warning: something\n{"a": 1}\n') == {"a": 1}


def test_parse_json_returns_none_for_empty_or_garbage() -> None:
    assert _parse_json("") is None
    assert _parse_json("   ") is None
    assert _parse_json("not json") is None
    assert _parse_json("{broken") is None


def test_summarize_envaudit() -> None:
    findings, summary = summarize("envaudit", {"summary": {"total": 3, "error": 1}})
    assert findings == 3
    assert summary["error"] == 1


def test_summarize_migration_guard() -> None:
    assert summarize("migration-guard", {"summary": {"findings": 2}})[0] == 2


def test_summarize_typeshift() -> None:
    assert summarize("typeshift", {"summary": {"total": 4}})[0] == 4


def test_summarize_apiwatch_counts_target_changes() -> None:
    report = {
        "targets": [
            {"changes": [{"kind": "breaking"}, {"kind": "compatible"}]},
            {"changes": [{"kind": "breaking"}]},
        ],
        "summary": {"breaking": 9, "compatible": 7},
    }
    assert summarize("apiwatch", report)[0] == 3


def test_summarize_apiwatch_falls_back_to_summary() -> None:
    report = {"summary": {"breaking": 2, "compatible": 1}}
    assert summarize("apiwatch", report)[0] == 3


def test_summarize_unknown_report_shapes() -> None:
    assert summarize("other", {"findings": [{}, {}]})[0] == 2
    assert summarize("other", {"changes": [{}]})[0] == 1
    assert summarize("other", {"summary": {"findings": 5}})[0] == 5
    assert summarize("other", {"summary": {"total": 6}})[0] == 6
    assert summarize("other", {"summary": {"nothing": 1}})[0] == 0
    assert summarize("other", None) == (0, {})
    assert summarize("other", []) == (0, {})


def test_classify_distinguishes_fail_from_error() -> None:
    assert _classify(0, 5, False) == "ok"
    assert _classify(2, 1, False) == "fail"
    assert _classify(2, 0, False) == "error"
    assert _classify(None, 0, True) == "error"


def test_skipped_item_never_claims_success(tmp_path: Path) -> None:
    item = PlanItem(
        name="envaudit",
        reason="envaudit is not on PATH",
        install="cargo install --git https://github.com/hix-pro/env-audit",
        cwd=tmp_path,
    )
    result = run_item(item)

    assert result.status == "skipped"
    assert result.findings == 0
    assert result.reason == "envaudit is not on PATH"
    assert result.exit_code is None


def test_run_item_ok(tmp_path: Path) -> None:
    item = PlanItem(
        name="envaudit",
        argv=python('print(\'{"summary": {"total": 2}}\')'),
        cwd=tmp_path,
    )
    result = run_item(item)

    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.findings == 2
    assert result.report == {"summary": {"total": 2}}


def test_run_item_fail_when_findings_and_nonzero_exit(tmp_path: Path) -> None:
    code = 'import json, sys; print(json.dumps({"summary": {"total": 2}})); sys.exit(2)'
    item = PlanItem(name="envaudit", argv=python(code), cwd=tmp_path)
    result = run_item(item)

    assert result.status == "fail"
    assert result.findings == 2
    assert result.exit_code == 2
    assert result.error == ""


def test_run_item_error_when_nonzero_exit_without_findings(tmp_path: Path) -> None:
    code = 'import sys; sys.stderr.write("boom\\n"); sys.exit(2)'
    item = PlanItem(name="envaudit", argv=python(code), cwd=tmp_path)
    result = run_item(item)

    assert result.status == "error"
    assert result.findings == 0
    assert result.error == "boom"


def test_run_item_timeout(tmp_path: Path) -> None:
    item = PlanItem(
        name="envaudit",
        argv=python("import time; time.sleep(2)"),
        cwd=tmp_path,
    )
    result = run_item(item, timeout=0.1)

    assert result.status == "error"
    assert result.exit_code is None
    assert "timed out after 0.1s" in result.error


def test_run_item_missing_binary(tmp_path: Path) -> None:
    item = PlanItem(name="envaudit", argv=[str(tmp_path / "nope")], cwd=tmp_path)
    result = run_item(item)

    assert result.status == "error"
    assert result.exit_code is None
    assert "nope" in result.error


def test_run_plan_keeps_plan_order_when_parallel(tmp_path: Path) -> None:
    plan = [
        PlanItem(name="slow", argv=python("import time; time.sleep(0.3)"), cwd=tmp_path),
        PlanItem(name="fast", argv=python("import time; time.sleep(0.05)"), cwd=tmp_path),
        PlanItem(name="medium", argv=python("import time; time.sleep(0.15)"), cwd=tmp_path),
    ]
    results = run_plan(plan, jobs=3)

    assert [result.name for result in results] == ["slow", "fast", "medium"]
    assert all(result.status == "ok" for result in results)


def test_run_plan_fail_fast_stops_after_failure(tmp_path: Path) -> None:
    code = 'import json, sys; print(json.dumps({"summary": {"total": 1}})); sys.exit(2)'
    plan = [
        PlanItem(name="bad", argv=python(code), cwd=tmp_path),
        PlanItem(name="never", argv=python("print('{}')"), cwd=tmp_path),
    ]
    results = run_plan(plan, jobs=1, fail_fast=True)

    assert len(results) == 1
    assert results[0].name == "bad"
    assert results[0].status == "fail"


def test_result_to_dict_includes_reason_and_install() -> None:
    result = RunResult(
        name="typeshift",
        status="skipped",
        exit_code=None,
        duration_ms=0,
        command="",
        reason="needs a source pair",
        install="npm install",
    )
    payload = result.to_dict()

    assert payload["reason"] == "needs a source pair"
    assert payload["install"] == "npm install"
    assert payload["exit_code"] is None


def test_result_to_dict_can_omit_report() -> None:
    result = RunResult(
        name="envaudit",
        status="ok",
        exit_code=0,
        duration_ms=12,
        command="envaudit scan .",
        report={"summary": {"total": 0}},
    )
    assert "report" not in result.to_dict(include_report=False)
    assert result.to_dict()["report"] == {"summary": {"total": 0}}


def test_report_is_serializable(tmp_path: Path) -> None:
    item = PlanItem(name="envaudit", argv=python("print('{\"ok\": true}')"), cwd=tmp_path)
    result = run_item(item)
    assert json.loads(json.dumps(result.to_dict()))["report"] == {"ok": True}
