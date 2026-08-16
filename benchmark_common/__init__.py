"""Shared infrastructure for benchmark task construction.

Provides chief-complaint normalization, statistical helpers, and input
verification reused by each task package (investigation_selection,
clinical_diagnosis, ...).
"""
from .conditions import normalize_condition, extract_conditions
from .stats import wilson_lower, binomial_greater_pvalue, benjamini_hochberg
from .io import _sha256_file, _verify_normalized_events

__all__ = [
    "normalize_condition", "extract_conditions",
    "wilson_lower", "binomial_greater_pvalue", "benjamini_hochberg",
    "_sha256_file", "_verify_normalized_events",
]
