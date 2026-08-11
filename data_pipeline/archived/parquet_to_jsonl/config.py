"""Configuration: paths, ICU exclusion rules, DS section titles."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Input parquet directory (G drive episodes)
    parquet_dir: Path = Path("G:/Projects/医疗数据集评测-MIMIC/outputs/episodes")
    # patients.csv.gz for age/sex
    patients_path: Path = Path(
        "D:/Projects/llm_benchmark/data/RawData/mimic-iv-3.1/hosp/patients.csv.gz"
    )
    raw_data_root: Path = Path("D:/Projects/llm_benchmark/data/RawData")
    # Output JSONL (G drive to avoid D drive space issues)
    output_path: Path = Path(
        "G:/Projects/llm_benchmark/data/rwd_benchmark_visits.jsonl"
    )
    # Output stats JSON
    stats_path: Path = Path(
        "G:/Projects/llm_benchmark/data/extraction_stats.json"
    )
    # Batch size for DuckDB processing (episodes per batch)
    batch_size: int = 10_000
    # Optional limit on eligible episodes (0 = no limit)
    limit: int = 0

    @property
    def omr_path(self) -> Path:
        return self.raw_data_root / "mimic-iv-3.1" / "hosp" / "omr.csv.gz"

    @property
    def edstays_path(self) -> Path:
        return self.raw_data_root / "mimic-iv-ed" / "ed" / "edstays.csv.gz"

    @property
    def icustays_path(self) -> Path:
        return self.raw_data_root / "mimic-iv-3.1" / "icu" / "icustays.csv.gz"

    @property
    def radiology_detail_path(self) -> Path:
        return self.raw_data_root / "mimic-iv-note-2.2" / "note" / "radiology_detail.csv.gz"


# event_types to EXCLUDE entirely (ICU continuous monitoring)
# Exclusion is achieved at the event_type filter level: these event_types
# are never queried in any aggregator, so ICU data is naturally excluded.
ICU_EVENT_TYPES: frozenset[str] = frozenset({
    "icu_observation",
    "icu_input",
    "icu_output",
    "icu_ingredient_input",
    "icu_datetime_observation",
    "icu_procedure",
})

# Known DS section titles (for chapter parsing)
DS_SECTION_TITLES: tuple[str, ...] = (
    "Chief Complaint",
    "Major Surgical or Invasive Procedure",
    "History of Present Illness",
    "Past Medical History",
    "Social History",
    "Family History",
    "Allergies",
    "Physical Exam",
    "Pertinent Results",
    "Studies",
    "Brief Hospital Course",
    "Medications on Admission",
    "Discharge Medications",
    "Discharge Diagnosis",
    "Discharge Condition",
    "Discharge Instructions",
    "Follow-up Instructions",
    "Followup Instructions",
    "Follow Up Instructions",
)

# Target sections to extract -> (jsonl_group, jsonl_field, title_variants)
DS_SECTIONS: list[tuple[str, str, tuple[str, ...]]] = [
    ("narrative", "chief_complaint", ("Chief Complaint",)),
    ("narrative", "history_of_present_illness", ("History of Present Illness",)),
    ("narrative", "past_medical_history", ("Past Medical History",)),
    ("narrative", "social_history", ("Social History",)),
    ("narrative", "medications_on_admission", ("Medications on Admission",)),
    ("narrative", "allergies", ("Allergies",)),
    ("narrative", "physical_exam", ("Physical Exam",)),
    ("disposition", "brief_hospital_course", ("Brief Hospital Course",)),
    ("disposition", "discharge_medications", ("Discharge Medications",)),
    ("disposition", "discharge_condition", ("Discharge Condition",)),
    ("disposition", "discharge_record", ("Discharge Instructions",)),
]
