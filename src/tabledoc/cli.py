"""tabledoc validate, load and dump."""

from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .description import Options, read
from .dump import Source, dump
from .load import Target, load
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
    _common(v)
    w = commands.add_parser("load", help="check the description and write it into a DuckLake catalog")
    _common(w)
    w.add_argument("--ducklake", default=None, help="the DuckLake catalog, such as fdl's working metadata (default: FDL_WORKING)")
    w.add_argument(
        "--data-path", default=None, help="where new data files go (default: FDL_DATA_PATH, else fdl clone's note)"
    )
    w.add_argument("--schema", default=None, help="the schema to write into (default: tabledoc.yml's schema, else _tabledoc)")
    w.add_argument("--out", type=Path, default=None, help="also write the files for fdl commit --assets here")
    w.add_argument("--assets", type=Path, default=None, help="files of the asset columns, linked into --out")
    w.add_argument("--unlisted", action="store_true", help="write the tables with no description as not published")
    d = commands.add_parser("dump", help="write the files of the description a DuckLake catalog holds")
    d.add_argument("--ducklake", default=None, help="the DuckLake catalog, such as fdl's working metadata (default: FDL_WORKING)")
    d.add_argument("--schema", default="_tabledoc", help="the schema the description is in (default: _tabledoc)")
    d.add_argument("--out", type=Path, default=Path.cwd(), help="the folder to write into (default: here)")
    d.add_argument("--files", default=None, help="where the files are, as <files>/<sha256> (default: the repository's assets)")
    d.add_argument("--name", default=None, help="the dataset's name (default: the repository's)")
    d.add_argument("--force", action="store_true", help="replace the files already there")
    return p


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path.cwd(), help="the folder of tabledoc.yml (default: here)")
    p.add_argument("--manifest", type=Path, default=None, help="dbt's manifest.json (default: target/manifest.json)")
    p.add_argument("--profiles", type=Path, default=None, help="dbt's profiles.yml (default: DBT_PROFILES_DIR, else the root)")
    p.add_argument("--quiet", action="store_true", help="hide info findings")
    p.add_argument("--strict", action="store_true", help="fail on warnings too")


def _catalog(given: str | None) -> str:
    catalog = given or os.environ.get("FDL_WORKING")
    if not catalog:
        raise SpecError("give the catalog: --ducklake or FDL_WORKING")
    return catalog


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "dump":
        try:
            written = dump(Source(_catalog(args.ducklake), args.files, args.name, args.schema), args.out, force=args.force)
        except SpecError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {len(written)} files in {args.out}", file=sys.stderr)
        return 0
    report = Report()
    options = Options(args.root, args.manifest, args.profiles, with_source=args.command == "load")
    try:
        if args.command == "validate":
            read(options, report)
        else:
            catalog = _catalog(args.ducklake)
            data = args.data_path or os.environ.get("FDL_DATA_PATH")
            if args.assets and not args.out:
                raise SpecError("--assets links its files into --out's assets/; give --out too")
            target = Target(catalog, data, args.out, args.assets, args.unlisted, args.schema)
            if load(options, target, report, strict=args.strict) is not None:
                print(f"wrote {target.catalog}" + (f" and {target.out}" if target.out else ""), file=sys.stderr)
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
