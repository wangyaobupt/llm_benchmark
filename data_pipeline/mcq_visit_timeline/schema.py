"""Visit timeline schema. Clocks from time-backfill, names from standardize."""

from __future__ import annotations

import pyarrow as pa

SCHEMA_NAME = "mcq_visit_timeline"
SCHEMA_VERSION = "1.0.0"

EVENT_KINDS: tuple[str, ...] = (
    "lab_resulted",
    "radiology_reported",
    "cardiology_ordered",
    "respiratory_ordered",
    "poe_lab_imaging",
    "medication_prescribed",
    "procedure_recorded",
    "medrecon",
    "transfer",
    "service_transfer",
    "encounter_admit",
    "encounter_discharge",
    "encounter_ed_in",
    "encounter_ed_out",
    "rhythm_charted",
    "vitals_triage",
    "complaint_bound",
)

EVENT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "subject_id",
    "hadm_id",
    "event_kind",
    "domain",
    "fact_type",
    "occurrence_time",
    "occurrence_basis",
    "available_time",
    "available_basis",
    "hours_from_admit",
    "hours_from_presentation",
    "time_precision",
    "time_missing",
    "standard_name",
    "source_name",
    "mapping_status",
    "itemid",
    "source_field",
    "category_only",
    "valuenum",
    "flag",
)

EVENT_ARROW_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("event_kind", pa.string()),
        ("domain", pa.string()),
        ("fact_type", pa.string()),
        ("occurrence_time", pa.string()),
        ("occurrence_basis", pa.string()),
        ("available_time", pa.string()),
        ("available_basis", pa.string()),
        ("hours_from_admit", pa.float64()),
        ("hours_from_presentation", pa.float64()),
        ("time_precision", pa.string()),
        ("time_missing", pa.bool_()),
        ("standard_name", pa.string()),
        ("source_name", pa.string()),
        ("mapping_status", pa.string()),
        ("itemid", pa.string()),
        ("source_field", pa.string()),
        ("category_only", pa.bool_()),
        ("valuenum", pa.float64()),
        ("flag", pa.string()),
    ]
)

FROZEN_TIMES_SHA256 = "943B7B74CA99D8214481DB2D91C2D22366473563CCE2BA6B805956C6DB36FF07"
FROZEN_STANDARDIZED_SHA256 = "F69328CABC63D3E228B8E7922E6DDEF2239B50D3BFD6C174FABB3FAC33453EBA"
