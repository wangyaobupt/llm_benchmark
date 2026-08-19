"""P0 — decision-time gate: index time and prospective feature availability.

The index time is the FIRST investigation order of the visit (the moment before
which the "presentation" must be fully known). A feature event is available iff
it occurred strictly before the index AND is a ``source_event`` (not post_hoc).
"""
from __future__ import annotations

import pandas as pd

# Investigation ORDER events define the index. laboratory_ordered is the true
# order event; laboratory_resulted is the result (later in time) and must NOT
# define the index.
ORDER_EVENT_KINDS = ("imaging_ordered", "clinical_ordered", "laboratory_ordered")


def index_times(events: pd.DataFrame) -> pd.DataFrame:
    """Return hadm_id -> index_time (min order event_time)."""
    orders = events[
        events["event_kind"].isin(ORDER_EVENT_KINDS)
        & events["event_time"].notna()
    ]
    if orders.empty:
        return pd.DataFrame(columns=["hadm_id", "index_time"])
    idx = (
        orders.groupby("hadm_id", sort=True)["event_time"]
        .min()
        .reset_index(name="index_time")
    )
    return idx


def is_available(event_time, evidence_phase: str, index_time) -> bool:
    """True when a feature event is prospectively available at the index.

    Post-hoc events are never available. A source event with an unknown
    ``event_time`` (e.g. the ED chief complaint, whose triage timestamp is not
    recorded) is treated as available — it is part of the presenting state and
    precedes any investigation order. Otherwise the event must occur before the
    index.
    """
    if evidence_phase != "source_event":
        return False
    if event_time is None or (isinstance(event_time, float) and pd.isna(event_time)):
        return True
    if index_time is None:
        return False
    return str(event_time).replace("T", " ") < str(index_time).replace("T", " ")


def gate_events(events: pd.DataFrame, index_map: pd.DataFrame) -> pd.DataFrame:
    """Return only events that were available before each visit's index time.

    Events with a missing index are dropped (fail-closed). Identity/demographic
    rows that carry no time (age/sex) are supplied separately, not here.
    """
    if events.empty or index_map.empty:
        return events.iloc[0:0]
    merged = events.merge(index_map, on="hadm_id", how="inner")
    et = merged["event_time"].astype(str).str.replace("T", " ")
    it = merged["index_time"].astype(str).str.replace("T", " ")
    keep = (
        (merged["evidence_phase"] == "source_event")
        & (merged["event_time"].isna() | (et < it))
    )
    cols = [c for c in events.columns if c != "index_time"]
    return merged.loc[keep, cols]
