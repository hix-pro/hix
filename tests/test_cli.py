from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hix.cli import main


def python_command(script: Path) -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    ok = write_script(
        tmp_path / "ok.py",
        'import json\nprint(json.dumps({"summary": {"total": 0}}))\n',
    )
    bad = write_script(
        tmp_path / "bad.py",
        "import json, sys\n"
        'print(json.dumps({"summary": {"total": 2, "critical": 1}}))\n'
        "sys.exit(2)\n",
    )
    (tmp_path / ".hix.toml").write_text(
        "\n".join(
            [
                "[checks.fake-ok]",
                f"command = {json.dumps(python_command(ok))}",
                "",
                "[checks.fake-bad]",
                f"command = {json.dumps(python_command(bad))}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_version_plain(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == "hix 0.1.0"


def test_version_json(capsys) -> None:
    assert main(["version", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"name": "hix", "version": "0.1.0"}


def test_no_command_prints_help(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "usage: hix" in output
    assert "check" in output


def test_check_reports_failure(project: Path, capsys) -> None:
    assert main(["check", str(project), "--no-color"]) == 1
    output = capsys.readouterr().out

    assert "fake-ok" in output
    assert "fake-bad" in output
    assert "1 failing" in output
    assert "2 findings" in output


def test_check_only_selects_one_tool(project: Path, capsys) -> None:
    assert main(["check", str(project), "--only", "fake-ok", "--no-color"]) == 0
    output = capsys.readouterr().out

    assert "fake-ok" in output
    assert "fake-bad" not in output
    assert "1 tools" not in output


def test_check_only_unknown_is_usage_error(project: Path, capsys) -> None:
    assert main(["check", str(project), "--only", "nope"]) == 2
    assert "no checks matched: nope" in capsys.readouterr().err


def test_check_json_output(project: Path, capsys) -> None:
    assert main(["check", str(project), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == 1
    assert [tool["name"] for tool in payload["tools"]] == ["fake-ok", "fake-bad"]
    assert payload["tools"][1]["status"] == "fail"
    assert payload["tools"][1]["findings"] == 2
    assert payload["tools"][1]["report"]["summary"]["critical"] == 1
    assert payload["summary"]["fail"] == 1


def test_check_json_no_report(project: Path, capsys) -> None:
    assert main(["check", str(project), "--json", "--no-report"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert "report" not in payload["tools"][0]
    assert payload["summary"]["findings"] == 2


def test_check_missing_path(capsys) -> None:
    assert main(["check", "/definitely/not/here"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_check_missing_config(project: Path, capsys) -> None:
    assert main(["check", str(project), "--config", "nope.toml"]) == 2
    assert "config not found" in capsys.readouterr().err


def test_check_invalid_config_json(project: Path, capsys) -> None:
    (project / ".hix.toml").write_text("[checks.bad\n", encoding="utf-8")
    assert main(["check", str(project), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "could not read" in payload["error"]


def test_doctor_json(project: Path, capsys) -> None:
    assert main(["doctor", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["root"] == str(project)
    names = [row["name"] for row in payload["checks"]]
    assert names[:4] == ["envaudit", "migration-guard", "apiwatch", "typeshift"]
    assert "config" in names
    assert "migrations" in names
    assert "apiwatch db" in names


def test_doctor_plain(project: Path, capsys) -> None:
    assert main(["doctor", str(project), "--no-color"]) == 0
    output = capsys.readouterr().out
    assert "CHECK" in output
    assert "envaudit" in output


def test_doctor_missing_path(capsys) -> None:
    assert main(["doctor", "/definitely/not/here"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_init_writes_config(tmp_path: Path, capsys) -> None:
    with patch("hix.cli.init_config", return_value="# generated\n"):
        assert main(["init", str(tmp_path)]) == 0

    target = tmp_path / ".hix.toml"
    assert target.read_text(encoding="utf-8") == "# generated\n"
    assert "wrote" in capsys.readouterr().out


def test_init_refuses_to_overwrite(tmp_path: Path, capsys) -> None:
    (tmp_path / ".hix.toml").write_text("old\n", encoding="utf-8")

    with patch("hix.cli.init_config", return_value="new\n"):
        assert main(["init", str(tmp_path)]) == 1

    assert (tmp_path / ".hix.toml").read_text(encoding="utf-8") == "old\n"
    assert "already exists" in capsys.readouterr().err


def test_init_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / ".hix.toml").write_text("old\n", encoding="utf-8")

    with patch("hix.cli.init_config", return_value="new\n"):
        assert main(["init", str(tmp_path), "--force"]) == 0

    assert (tmp_path / ".hix.toml").read_text(encoding="utf-8") == "new\n"


def test_init_print_does_not_write(tmp_path: Path, capsys) -> None:
    with patch("hix.cli.init_config", return_value="# generated\n"):
        assert main(["init", str(tmp_path), "--print"]) == 0

    assert not (tmp_path / ".hix.toml").exists()
    assert capsys.readouterr().out == "# generated\n"


def test_init_missing_path(capsys) -> None:
    assert main(["init", "/definitely/not/here"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_init_uses_detected_tools(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("select 1;", encoding="utf-8")
    db = tmp_path / "apiwatch.db"
    db.write_text("", encoding="utf-8")

    def fake_which(binary: str) -> str | None:
        return f"/opt/hix/{binary}"

    with (
        patch("hix.tools._which", side_effect=fake_which),
        patch.dict(os.environ, {"APIWATCH_DB": str(db)}),
    ):
        assert main(["init", str(tmp_path)]) == 0

    content = (tmp_path / ".hix.toml").read_text(encoding="utf-8")
    assert "[checks.envaudit]" in content
    assert "[checks.migration-guard]" in content
    assert "[checks.apiwatch]" in content
    assert "# [checks.typeshift]" in content
