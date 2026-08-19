"""Removed package path. Formal generation is forbidden.

Audit-only code lives at ``data_pipeline.archived.phenotype``. Importing this
path is treated as a formal-path failure.
"""

from evaluation_pipeline.governance.legacy import (
    LEGACY_PHENOTYPE_FORMAL_FORBIDDEN,
    LegacyArtifactError,
)

raise LegacyArtifactError(
    "data_pipeline.phenotype is not an importable package; "
    "audit-only code is data_pipeline.archived.phenotype; "
    f"formal generation is forbidden: {LEGACY_PHENOTYPE_FORMAL_FORBIDDEN}"
)
