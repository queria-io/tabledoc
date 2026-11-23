"""tabledoc: describe the tables of a dataset in YAML and Markdown, check it, and write it as the tables of the _tabledoc schema."""

from .description import Description, Options, read
from .dump import Source, dump
from .files import File
from .load import Target, load
from .report import Finding, Level, Report, SpecError

__all__ = ["Description", "File", "Finding", "Level", "Options", "Report", "Source", "SpecError", "Target", "dump", "load", "read"]
