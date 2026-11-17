"""tabledoc validate."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .description import Options, read
from .report import Level, Report, SpecError


def _version() -> str:
    try:
        return f"tabledoc {version('tabledoc')}"
    except PackageNotFoundError:
        return "tabledoc"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tabledoc", description="Check a dataset's description.")
    p.add_argument("--version", action="version", version=_version())
    commands = p.add_subparsers(dest="command", required=True)
    v = commands.add_parser("validate", help="check the description")
    v.add_argument("--root", type=Path, default=Path.cwd(), help="the folder of tabledoc.yml (default: here)")
    v.add_argument("--manifest", type=Path, default=None, help="dbt's manifest.json (default: target/manifest.json)")
    v.add_argument("--profiles", type=Path, default=None, help="dbt's profiles.yml (default: DBT_PROFILES_DIR, else the root)")
    v.add_argument("--quiet", action="store_true", help="hide info findings")
    v.add_argument("--strict", action="store_true", help="fail on warnings too")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = Report()
    try:
        read(Options(args.root, args.manifest, args.profiles, with_source=False), report)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rendered = report.render(show_info=not args.quiet)
    if rendered:
        print(rendered, file=sys.stderr)
    warnings = report.of(Level.WARNING)
    print(f"error {len(report.of(Level.ERROR))} / warning {len(warnings)}", file=sys.stderr)
    return 1 if report.failed or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
