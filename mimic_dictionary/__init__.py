"""Build compact, query-ready dictionaries from licensed MIMIC source files."""

from .builder import build_dictionaries
from .decode_archive import decode_file

__all__ = ["build_dictionaries", "decode_file"]
