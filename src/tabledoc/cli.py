"""tabledoc validate | build | push."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import build as building
from .build import Options
from .push import PushError, push
from .report import Level, Report, SpecError

DEFAULT_OUT = Path("target") / "tabledoc.json"


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path.cwd(), help="the folder of tabledoc.yml (default: here)")
    p.add_argument("--manifest", type=Path, default=None, help="dbt's manifest.json (default: target/manifest.json)")
    p.add_argument("--profiles", type=Path, default=None, help="dbt's profiles.yml (default: DBT_PROFILES_DIR, else the root)")
    p.add_argument("--quiet", action="store_true", help="hide info findings")
    p.add_argument("--strict", action="store_true", help="fail on warnings too")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tabledoc", description="Check a dataset's description and build tabledoc.json from it.")
    p.add_argument("--version", action="version", version=building.generator())
    commands = p.add_subparsers(dest="command", required=True)
    _common(commands.add_parser("validate", help="check the description"))
    p_build = commands.add_parser("build", help=f"check the description and write {DEFAULT_OUT}")
    _common(p_build)
    p_build.add_argument("--out", type=Path, default=None, help=f"where to write (default: {DEFAULT_OUT} under the root)")
    p_push = commands.add_parser("push", help="send tabledoc.json and the files it lists")
    p_push.add_argument("url", help="where to send it, such as https://queria.io/api/datasets/<handle>/<name>/metadata")
    p_push.add_argument("--root", type=Path, default=Path.cwd(), help="the folder of tabledoc.yml (default: here)")
    p_push.add_argument("--file", type=Path, default=None, help=f"the tabledoc.json to send (default: {DEFAULT_OUT} under the root)")
    p_push.add_argument("--token", default=None, help="Bearer token (default: TABLEDOC_TOKEN)")
    return p


def _finish(report: Report, args: argparse.Namespace) -> bool:
    rendered = report.render(show_info=not args.quiet)
    if rendered:
        print(rendered, file=sys.stderr)
    warnings = report.of(Level.WARNING)
    print(f"error {len(report.of(Level.ERROR))} / warning {len(warnings)}", file=sys.stderr)
    return not (report.failed or (args.strict and warnings))


def _check(args: argparse.Namespace) -> int:
    report = Report()
    try:
        built = building.build(Options(args.root, args.manifest, args.profiles), report)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not _finish(report, args):
        return 1
    if args.command == "build":
        out = args.out or args.root / DEFAULT_OUT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(building.to_json(built.document), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    return 0


def _push(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("TABLEDOC_TOKEN")
    if not token:
        print("error: give a token with --token or TABLEDOC_TOKEN", file=sys.stderr)
        return 2
    try:
        document = building.read(args.file or args.root / DEFAULT_OUT)
        reply = push(args.url, document, args.root.resolve(), token, log=lambda m: print(m, file=sys.stderr))
    except (SpecError, PushError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("unchanged" if reply.status == 200 else "created", reply.body, file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return _push(args) if args.command == "push" else _check(args)


if __name__ == "__main__":
    sys.exit(main())
