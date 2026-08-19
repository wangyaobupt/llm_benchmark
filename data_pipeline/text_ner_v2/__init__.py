"""Clean, resumable two-stage clinical NER + relation extraction.

This package is a deliberately simpler re-implementation of the text NER
interface. It reads the accepted `event_pipeline_output/aggregation` package,
extracts entity mentions and explicit text relations through an
OpenAI-compatible chat-completions API (configured via the repository `.env`),
and compiles grounded entity/relation sidecars. It avoids the fragile
exact-offset and recursive-split machinery of the previous implementation.
"""

from __future__ import annotations

__all__ = ["PIPELINE_VERSION"]

PIPELINE_VERSION = "text-ner-v2/1.0.0"
