"""Where `fdl clone` keeps its state beside a working metadata file."""

from __future__ import annotations

from pathlib import Path


def note(catalog: str) -> Path | None:
    """The state `fdl clone` wrote beside ``catalog``, or None when fdl did not make it.

    fdl keeps it in ``<catalog>.fdl/state.json``; fdl 0.34 and earlier kept it
    in ``<catalog>.fdl.json``.
    """
    path = catalog.removeprefix("ducklake:")
    found = (Path(f"{path}.fdl") / "state.json", Path(f"{path}.fdl.json"))
    return next((candidate for candidate in found if candidate.is_file()), None)
