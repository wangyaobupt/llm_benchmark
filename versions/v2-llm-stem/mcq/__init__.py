"""v2 MCQ generation pipeline (clinical investigation selection).

Implements the full decision chain from ``mcq_generation/question_generation_logic.md``:

    统计定答案 → 程序锁选项 → LLM 只写题干 → 三道门禁才进 gold

The pipeline is deterministic through the statistical layer (rule mining, option
locking), calls a structured LLM client only for ``stem``/``rationale`` (generation)
and a strictly isolated review verdict (auto review), and exports gold only when
every gate — source rule accepted, 12 program checks passed, 9-item auto review
passed, human decision approved, non-exploratory profile — is satisfied
(fail-closed).
"""

from .constants import (
    PIPELINE_VERSION,
    SCHEMA_VERSION,
    RULE_VERSION,
    PROMPT_VERSION,
    GENERATION_ERROR_CODES,
    REJECTION_REASON_CODES,
)

__version__ = PIPELINE_VERSION

__all__ = [
    "PIPELINE_VERSION",
    "SCHEMA_VERSION",
    "RULE_VERSION",
    "PROMPT_VERSION",
    "GENERATION_ERROR_CODES",
    "REJECTION_REASON_CODES",
]
