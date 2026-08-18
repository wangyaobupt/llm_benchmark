"""Contract-first investigation-selection rebuild modules."""

from .encounter_clock import EncounterClockResult, build_encounter_clock
from .source_grouping import GroupingResult, attach_source_groups

__all__ = [
    "EncounterClockResult",
    "GroupingResult",
    "attach_source_groups",
    "build_encounter_clock",
]

