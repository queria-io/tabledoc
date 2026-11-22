from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def write(tmp_path: Path):
    """Write files under tmp_path: write({"a/b.yml": "..."}) -> tmp_path."""

    def _write(files: dict[str, str | bytes]) -> Path:
        for path, content in files.items():
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")
        return tmp_path

    return _write


def fdl_run(*args: object) -> str:
    """Run the fdl CLI in this process; its output."""
    from fdl.cli import app
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, [str(a) for a in args])
    assert result.exit_code == 0, result.output
    return result.output


@pytest.fixture
def lake(tmp_path: Path):
    """lake(sql) -> fdl's working metadata, cloned from a new repository, after ``sql`` (on ``lake``)."""

    def _lake(sql: str) -> Path:
        import duckdb
        from fdl import catalog, repo
        from fdl.stores import LocalStore

        remote, working = tmp_path / "remote", tmp_path / "work" / "lake.sqlite"
        fdl_run("init", remote)
        fdl_run("clone", remote, working)
        con = duckdb.connect()
        for statement in catalog.attach_sql(working, alias="lake", data_path=repo.data_url(LocalStore(remote))):
            if statement:
                con.execute(statement)
        con.execute(sql)
        con.close()
        return working

    return _lake
