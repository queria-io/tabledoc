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


@pytest.fixture
def lake(tmp_path: Path):
    """lake(sql) -> (catalog, data path): a DuckLake catalog after ``sql`` (on ``lake``)."""

    def _lake(sql: str) -> tuple[str, str]:
        from tabledoc.load import attached

        path = tmp_path / "lake" / "work.sqlite"
        data = tmp_path / "lake" / "data"
        data.mkdir(parents=True)
        with attached(str(path), data.as_posix() + "/") as con:
            con.execute(sql)
        return str(path), data.as_posix() + "/"

    return _lake
