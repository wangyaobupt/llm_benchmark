"""Attach standardized names onto time-backfill rows. Unmatched names stay unresolved."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from data_pipeline.mcq_visit_extract.columns import MEDICATION_CORE_KEYS
from data_pipeline.mcq_visit_extract.extract import medication_core
from data_pipeline.mcq_visit_standardize.text import lookup_key


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def lab_name_index(named: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    labs = (named.get("investigations_normalized") or {}).get("laboratory") or []
    for item in labs:
        itemid = _as_str(item.get("itemid"))
        if itemid:
            index[itemid] = item
    return index


def radiology_index(named: dict[str, Any]) -> dict[tuple[str, str], deque[dict[str, Any]]]:
    buckets: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(deque)
    rows = (named.get("investigations_normalized") or {}).get("radiology") or []
    for item in rows:
        key = (
            lookup_key(item.get("source_exam_name") or item.get("standard_exam_name")) or "",
            _as_str(item.get("charttime")),
        )
        buckets[key].append(item)
    return buckets


def take_radiology(
    buckets: dict[tuple[str, str], deque[dict[str, Any]]],
    exam_name: Any,
    charttime: Any,
) -> dict[str, Any] | None:
    key = (lookup_key(exam_name) or "", _as_str(charttime))
    queue = buckets.get(key)
    if queue:
        return queue.popleft()
    fallback = (lookup_key(exam_name) or "", "")
    queue = buckets.get(fallback)
    if queue:
        return queue.popleft()
    return None


def order_index(named: dict[str, Any], section: str) -> dict[tuple[str, str], deque[dict[str, Any]]]:
    buckets: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(deque)
    rows = (named.get("investigations_normalized") or {}).get(section) or []
    for item in rows:
        key = (
            lookup_key(item.get("source_order_subtype") or item.get("standard_order_name")) or "",
            _as_str(item.get("ordertime")),
        )
        buckets[key].append(item)
    return buckets


def take_order(
    buckets: dict[tuple[str, str], deque[dict[str, Any]]],
    subtype: Any,
    ordertime: Any,
) -> dict[str, Any] | None:
    key = (lookup_key(subtype) or "", _as_str(ordertime))
    queue = buckets.get(key)
    if queue:
        return queue.popleft()
    queue = buckets.get((lookup_key(subtype) or "", ""))
    if queue:
        return queue.popleft()
    return None


def _med_key(item: dict[str, Any]) -> tuple[str, ...]:
    core = medication_core(item) if "drug" in item else {key: item.get(key) for key in MEDICATION_CORE_KEYS}
    if not core.get("drug"):
        core["drug"] = item.get("source_drug")
    return tuple(_as_str(core.get(key)) for key in MEDICATION_CORE_KEYS)


def medication_index(named: dict[str, Any], field: str) -> dict[tuple[str, ...], deque[dict[str, Any]]]:
    buckets: dict[tuple[str, ...], deque[dict[str, Any]]] = defaultdict(deque)
    rows = named.get(field) or []
    for item in rows:
        buckets[_med_key(item)].append(item)
        source_only = (_as_str(item.get("source_drug") or item.get("drug")),) + ("",) * 6
        if source_only != _med_key(item):
            buckets[source_only].append(item)
    return buckets


def take_medication(
    buckets: dict[tuple[str, ...], deque[dict[str, Any]]],
    item: dict[str, Any],
) -> dict[str, Any] | None:
    key = _med_key(item)
    queue = buckets.get(key)
    if queue:
        return queue.popleft()
    source_only = (_as_str(item.get("drug")),) + ("",) * 6
    queue = buckets.get(source_only)
    if queue:
        return queue.popleft()
    return None


def procedure_index(named: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in named.get("procedures_normalized") or []:
        key = (_as_str(item.get("icd_code")), _as_str(item.get("icd_version")))
        if key[0]:
            index[key] = item
    return index
