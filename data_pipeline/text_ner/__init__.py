"""Traceable preparation of text inputs for clinical NER."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS = {
    "SectionAnnotationValidator": (
        ".annotation_validation",
        "SectionAnnotationValidator",
    ),
    "audit_annotation_package": (
        ".annotation_package_audit",
        "audit_annotation_package",
    ),
    "audit_manifest": (".audit", "audit_manifest"),
    "prepare_annotation_package": (
        ".annotation_package",
        "prepare_annotation_package",
    ),
    "prepare_manifest": (".manifest", "prepare_manifest"),
    "rehearse_scope": (".scope_rehearsal", "rehearse_scope"),
}

__all__ = [
    "SectionAnnotationValidator",
    "audit_annotation_package",
    "audit_manifest",
    "prepare_annotation_package",
    "prepare_manifest",
    "rehearse_scope",
]


def __getattr__(name: str) -> Any:
    """Load Parquet-dependent public helpers only when callers request them."""

    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
