"""Contract-first investigation-selection rebuild modules."""

from .encounter_clock import EncounterClockResult, build_encounter_clock
from .source_grouping import GroupingResult, attach_source_groups
from .snapshot_adapter import SnapshotAdapter, normalize_discharge_ner_records
from .decision_documents import DecisionDocumentResult, build_decision_documents
from .retrieval import RetrievalContractError, RetrievalIndex, RetrievalQueryResult, eligible_features

__all__ = [
    "EncounterClockResult",
    "GroupingResult",
    "attach_source_groups",
    "build_encounter_clock",
    "SnapshotAdapter",
    "normalize_discharge_ner_records",
    "DecisionDocumentResult",
    "build_decision_documents",
    "RetrievalContractError",
    "RetrievalIndex",
    "RetrievalQueryResult",
    "eligible_features",
]
