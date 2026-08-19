"""Invalidated visit-level phenotype layer (audit only).

W0 retired this package. Do not feed it into new gold, review, or release.
Formal generation remains fail-closed via
``evaluation_pipeline.governance.legacy.assert_legacy_phenotype_formal_forbidden``.
The live import path ``data_pipeline.phenotype`` is a stub that raises.

Historical role: visit-level typed condition features (age_band, sex, symptom,
sign, physiologic_flag, past_condition, medication, absent) from
``normalized_events.parquet`` plus a demographics sidecar, feeding the v2
rule miner.
"""
