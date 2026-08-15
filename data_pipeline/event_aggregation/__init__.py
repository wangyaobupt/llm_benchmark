"""Lossless aggregation of normalized events and their source records."""

from .pipeline import AggregationError, build_event_aggregation

__all__ = ["AggregationError", "build_event_aggregation"]
