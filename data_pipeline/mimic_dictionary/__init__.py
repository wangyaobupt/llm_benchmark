"""Build compact, query-ready dictionaries from licensed MIMIC source files."""

from typing import TYPE_CHECKING, Any

from .builder import build_dictionaries

if TYPE_CHECKING:
    from .decode_archive import decode_file

__all__ = ["build_dictionaries", "decode_file"]


def __getattr__(name: str) -> Any:
    if name == "decode_file":
        from .decode_archive import decode_file

        return decode_file
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
