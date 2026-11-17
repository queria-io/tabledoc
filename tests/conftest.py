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
