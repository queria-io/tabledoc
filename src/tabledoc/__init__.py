"""tabledoc: describe the tables of a dataset in YAML and Markdown, and read it back checked."""

from .description import Description, Options, read
from .files import File
from .report import Finding, Level, Report, SpecError

__all__ = ["Description", "File", "Finding", "Level", "Options", "Report", "SpecError", "read"]
