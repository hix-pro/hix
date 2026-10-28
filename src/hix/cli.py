"""Command line entry point for hix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .report import (
    DIM,
    GREEN,
    color_enabled,
    exit_code,
    paint,
    print_doctor,
    print_json,
    print_results,
)
from .runner import run_plan
from .tools import build_plan, doctor, init_config


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="repository to inspect (default: .)",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="use this .hix.toml instead of searching the repository",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write one JSON document to stdout",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors (NO_COLOR is also honored)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hix",
        description="One command to run the hix tools suite.",
        epilog=(
            "Docs: https://github.com/hix-pro/hix  ·  Tools: https://github.com/topics/hix-tools"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"hix {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    check = subparsers.add_parser(
        "check",
        help="run every detected check",
        description=(
            "Run the checks for this repository. Without a config, hix detects "
            "installed tools and builds a plan; with .hix.toml, the configured "
            "commands are used verbatim."
        ),
    )
    _common(check)
    check.add_argument(
        "--only",
        action="append",
        metavar="TOOL",
        help="run only this tool; repeat to select several",
    )
    check.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        metavar="SECONDS",
        help="per-tool timeout (default: 300)",
    )
    check.add_argument(
        "--jobs",
        type=int,
        default=0,
        metavar="N",
        help="run up to N tools at once (default: 4)",
    )
    check.add_argument(
        "--no-report",
        action="store_true",
        help="omit nested tool reports from --json output",
    )
    check.add_argument(
        "--verbose",
        action="store_true",
        help="print the exact command for each tool",
    )
    check.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop after the first failing selected tool",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="show what hix found on this machine",
        description=(
            "Check for each tool on PATH, the config file, a migrations "
            "directory, and the API Watch database."
        ),
    )
    _common(doctor_parser)

    init_parser = subparsers.add_parser(
        "init",
        help="write a .hix.toml from detected tools",
        description=(
            "Create .hix.toml with the checks hix would run today. Existing "
            "configs are never overwritten unless --force is passed."
        ),
    )
    init_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="repository to write into (default: .)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing .hix.toml",
    )
    init_parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="print the config instead of writing it",
    )

    version_parser = subparsers.add_parser(
        "version",
        help="print the hix version",
    )
    version_parser.add_argument(
        "--json",
        action="store_true",
        help="write JSON instead of plain text",
    )

    return parser


def _config_error(message: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"error": message}, indent=2))
    else:
        print(f"hix: {message}", file=sys.stderr)
    return 2


def cmd_check(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.is_dir():
        return _config_error(f"not a directory: {args.path}", args.json)

    try:
        plan, config = build_plan(root, args.config, args.only)
    except RuntimeError as error:
        return _config_error(str(error), args.json)

    if args.only and not plan:
        return _config_error(
            f"no checks matched: {', '.join(args.only)}",
            args.json,
        )

    if not plan:
        if args.json:
            print_json([], str(root), include_report=False)
        else:
            enabled = color_enabled(args.no_color)
            print(paint("No checks selected.", DIM, enabled))
        return 0

    jobs = args.jobs if args.jobs and args.jobs > 0 else min(4, len(plan))
    results = run_plan(
        plan,
        timeout=args.timeout,
        jobs=jobs,
        fail_fast=args.fail_fast,
    )

    if args.json:
        print_json(results, str(root), include_report=not args.no_report)
    else:
        enabled = color_enabled(args.no_color)
        if config:
            print(paint(f"config  {config}", DIM, enabled))
        print_results(results, no_color=args.no_color, verbose=args.verbose)

    return exit_code(results)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.is_dir():
        return _config_error(f"not a directory: {args.path}", args.json)

    rows = doctor(root, args.config)

    if args.json:
        print(json.dumps({"root": str(root), "checks": rows}, indent=2))
    else:
        print_doctor(rows, no_color=args.no_color)

    required = {
        "envaudit",
        "migration-guard",
        "apiwatch",
        "typeshift",
        "locklens",
        "planguard",
    }
    missing = [
        row["name"] for row in rows if row["name"] in required and row["status"] == "missing"
    ]
    if not args.json:
        enabled = color_enabled(args.no_color)
        print()
        if missing:
            label = "tool" if len(missing) == 1 else "tools"
            print(
                paint(
                    f"{len(missing)} {label} missing: {', '.join(missing)}. "
                    "Install commands are listed above.",
                    DIM,
                    enabled,
                )
            )
        else:
            print(paint("All six tools are installed.", GREEN, enabled))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.is_dir():
        print(f"hix: not a directory: {args.path}", file=sys.stderr)
        return 2

    target = root.resolve() / ".hix.toml"
    try:
        content = init_config(root)
    except RuntimeError as error:
        print(f"hix: {error}", file=sys.stderr)
        return 2

    if args.print_only:
        print(content, end="")
        return 0

    if target.exists() and not args.force:
        print(
            f"hix: {target} already exists. Use --force to overwrite it.",
            file=sys.stderr,
        )
        return 1

    target.write_text(content, encoding="utf-8")
    print(f"wrote {target}")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({"name": "hix", "version": __version__}, indent=2))
    else:
        print(f"hix {__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "check": cmd_check,
        "doctor": cmd_doctor,
        "init": cmd_init,
        "version": cmd_version,
    }
    return handlers[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
