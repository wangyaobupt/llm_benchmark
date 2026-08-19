"""Contract-first investigation-selection rebuild modules."""

from .actions import ActionResult, project_actions_from_facts, project_investigation_actions
from .facts import FactResult, build_investigation_facts, first_wave_facts
from .eligibility import EligibilityPolicy, load_eligibility_policy
from .encounter_clock import EncounterClockResult, build_encounter_clock
from .query import (
    InvestigationAtTime,
    VisibleFactsAtTime,
    build_timepoint_trace,
    list_investigations_at,
    list_visible_facts,
)
from .episodes import EpisodeResult, build_investigation_episodes
from .source_grouping import GroupingResult, attach_source_groups
from .snapshot_adapter import SnapshotAdapter, normalize_discharge_ner_records
from .decision_documents import DecisionDocumentResult, build_decision_documents
from .retrieval import RetrievalContractError, RetrievalIndex, RetrievalQueryResult, eligible_features
from .ranking import ContingencyTable, RankingContractError, benjamini_hochberg, contingency, statistics, subject_bootstrap_units
from .cohort import CohortContractError, DiagnosisMapping, audit_domains, map_diagnosis, select_domains
from .question_release import QuestionReleaseError, QuestionValidation, build_candidate_question, release_gold, review_record, validate_question

__all__ = [
    "ActionResult",
    "FactResult",
    "build_investigation_facts",
    "first_wave_facts",
    "project_actions_from_facts",
    "EligibilityPolicy",
    "EncounterClockResult",
    "EpisodeResult",
    "GroupingResult",
    "InvestigationAtTime",
    "VisibleFactsAtTime",
    "attach_source_groups",
    "build_encounter_clock",
    "build_investigation_episodes",
    "build_timepoint_trace",
    "list_investigations_at",
    "list_visible_facts",
    "load_eligibility_policy",
    "project_investigation_actions",
    "SnapshotAdapter",
    "normalize_discharge_ner_records",
    "DecisionDocumentResult",
    "build_decision_documents",
    "RetrievalContractError",
    "RetrievalIndex",
    "RetrievalQueryResult",
    "eligible_features",
    "ContingencyTable",
    "RankingContractError",
    "benjamini_hochberg",
    "contingency",
    "statistics",
    "subject_bootstrap_units",
    "CohortContractError",
    "DiagnosisMapping",
    "audit_domains",
    "map_diagnosis",
    "select_domains",
    "QuestionReleaseError",
    "QuestionValidation",
    "build_candidate_question",
    "release_gold",
    "review_record",
    "validate_question",
]
