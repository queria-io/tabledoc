"""tabledoc: describe the tables of a dataset in YAML and Markdown, check it, and write it into a DuckLake catalog's tables (_tabledoc by default)."""

from .description import Description, Options, read
from .dump import Source, dump
from .files import File
from .load import Target, load
from .report import Finding, Level, Report, SpecError

__all__ = ["Description", "File", "Finding", "Level", "Options", "Report", "Source", "SpecError", "Target", "dump", "load", "read"]
