"""Turn raw MIMIC-IV POE rows into readable, traceable timeline events.

The parser deliberately keeps official source values separate from derived labels.
It never invents a test, medication, or clinical intent when the source tables do
not expose one.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


OUTPUT_SCHEMA = {"name": "mimic-poe-timeline-event", "version": "2.0.0"}

ACTION_LABELS = {
    "New": ("create", "新开"),
    "Change": ("change", "变更"),
    "D/C": ("discontinue", "停止"),
}

OFFICIAL_TRANSACTION_TYPES = frozenset({"New", "Change", "D/C", "Co", "H", "T"})

REQUIRED_POE_FIELDS = (
    "poe_id",
    "poe_seq",
    "subject_id",
    "ordertime",
    "order_type",
)

CATEGORY_LABELS_ZH = {
    "Medications": "用药",
    "Lab": "检验",
    "General Care": "一般诊疗与护理",
    "ADT orders": "入院、出院或转科",
    "IV therapy": "静脉治疗",
    "Nutrition": "营养",
    "Radiology": "影像检查",
    "Consults": "会诊",
    "Respiratory": "呼吸治疗",
    "Blood Bank": "血库",
    "Cardiology": "心脏专科",
    "Critical Care": "重症治疗",
    "TPN": "全胃肠外营养",
    "Hemodialysis": "血液透析",
    "Neurology": "神经专科",
    "OB": "产科",
}

DOCUMENTED_DETAIL_FIELDS_V2_2 = frozenset(
    {
        "Admit to",
        "Indication",
        "Code status",
        "Transfer to",
        "Admit category",
        "Consult Status",
        "Discharge When",
        "Level of Urgency",
        "Discharge Planning",
        "Consult Status Time",
        "Tubes & Drains type",
    }
)

OBSERVED_EXTENSION_DETAIL_FIELDS = frozenset({"Route"})

DETAIL_LABELS_ZH = {
    "Route": "途径",
    "Admit category": "住院类别",
    "Admit to": "收治科室",
    "Tubes & Drains type": "管路或引流类型",
    "Discharge Planning": "出院计划",
    "Discharge When": "出院时点",
    "Code status": "复苏意愿",
    "Transfer to": "转入科室",
    "Level of Urgency": "紧急程度",
    "Consult Status Time": "会诊状态时间",
    "Consult Status": "会诊状态",
    "Indication": "适应证",
}

MEDICATION_FIELDS = (
    "pharmacy_id",
    "drug_type",
    "drug",
    "prod_strength",
    "dose_val_rx",
    "dose_unit_rx",
    "route",
    "doses_per_24_hrs",
    "starttime",
    "stoptime",
    "frequency",
    "duration",
    "duration_interval",
)

MEDICATION_CLINICAL_FIELDS = (
    "drug_type",
    "drug",
    "prod_strength",
    "dose_val_rx",
    "dose_unit_rx",
    "route",
    "doses_per_24_hrs",
    "frequency",
    "starttime",
    "stoptime",
    "duration",
    "duration_interval",
)

MEDICATION_FIELD_LABELS_ZH = {
    "drug_type": "处方成分类型",
    "drug": "药名",
    "prod_strength": "制剂规格",
    "dose_val_rx": "剂量值",
    "dose_unit_rx": "剂量单位",
    "route": "给药途径",
    "doses_per_24_hrs": "每日次数",
    "frequency": "给药频次",
    "starttime": "计划开始时间",
    "stoptime": "计划停止时间",
    "duration": "持续时长",
    "duration_interval": "持续时长单位",
}


class PoeTimelineError(ValueError):
    """Raised when a raw record violates the expected archive contract."""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("subject_id")),
        str(row.get("poe_id")),
        str(row.get("poe_seq")),
    )


def _order_key(row: dict[str, Any]) -> tuple[str, int, str]:
    raw_seq = _clean(row.get("poe_seq")) or ""
    try:
        sequence = int(raw_seq)
    except ValueError:
        sequence = 2**63 - 1
    return (_clean(row.get("ordertime")) or "9999-12-31 23:59:59", sequence, str(row.get("poe_id")))


def _index_rows_by_poe_id(
    rows: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            raise PoeTimelineError("linked source rows must be objects")
        poe_id = _clean(row.get("poe_id"))
        if poe_id:
            result[poe_id].append(row)
    return result


def _validate_linked_rows(
    order: dict[str, Any], rows: Iterable[dict[str, Any]], table: str
) -> None:
    for row in rows:
        if _clean(row.get("subject_id")) != _clean(order.get("subject_id")):
            raise PoeTimelineError(f"{table} subject_id conflicts with poe_id {order.get('poe_id')}")
        if row.get("poe_seq") is not None and _clean(row.get("poe_seq")) != _clean(order.get("poe_seq")):
            raise PoeTimelineError(f"{table} poe_seq conflicts with poe_id {order.get('poe_id')}")
        if row.get("hadm_id") is not None and _clean(row.get("hadm_id")) != _clean(order.get("hadm_id")):
            raise PoeTimelineError(f"{table} hadm_id conflicts with poe_id {order.get('poe_id')}")


def _validate_archive_row_ids(
    rows: Iterable[dict[str, Any]],
    table: str,
    record_subject_id: str,
    record_hadm_id: str,
    *,
    require_hadm_id: bool,
) -> None:
    for row in rows:
        if not isinstance(row, dict):
            raise PoeTimelineError(f"{table} rows must be objects")
        subject_id = _clean(row.get("subject_id"))
        if subject_id != record_subject_id:
            raise PoeTimelineError(
                f"{table} subject_id {subject_id} conflicts with archive subject_id "
                f"{record_subject_id}"
            )
        hadm_id = _clean(row.get("hadm_id"))
        if require_hadm_id and hadm_id is None:
            raise PoeTimelineError(f"{table} row is missing required hadm_id")
        if hadm_id is not None and hadm_id != record_hadm_id:
            raise PoeTimelineError(
                f"{table} hadm_id {hadm_id} conflicts with archive hadm_id {record_hadm_id}"
            )


def _index_pharmacy_by_poe_id(
    rows: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            raise PoeTimelineError("pharmacy rows must be objects")
        poe_id = _clean(row.get("poe_id"))
        if poe_id:
            result[poe_id].append(row)
    return result


def _index_pharmacy_by_pharmacy_id(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise PoeTimelineError("pharmacy rows must be objects")
        pharmacy_id = _clean(row.get("pharmacy_id"))
        if not pharmacy_id:
            raise PoeTimelineError("pharmacy row is missing required pharmacy_id")
        if pharmacy_id in result:
            raise PoeTimelineError(f"duplicate pharmacy_id within admission: {pharmacy_id}")
        result[pharmacy_id] = row
    return result


def _pharmacy_match(
    prescription: dict[str, Any],
    pharmacy_by_id: dict[str, dict[str, Any]],
    poe_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    pharmacy_id = _clean(prescription.get("pharmacy_id"))
    if not pharmacy_id:
        raise PoeTimelineError(
            f"prescription linked to poe_id {poe_id} is missing required pharmacy_id"
        )
    pharmacy = pharmacy_by_id.get(pharmacy_id)
    if pharmacy is None:
        return None, "unresolved_pharmacy_id"
    pharmacy_poe_id = _clean(pharmacy.get("poe_id"))
    if pharmacy_poe_id and pharmacy_poe_id != poe_id:
        return None, "pharmacy_poe_id_conflict"
    return pharmacy, None


def _medications(
    prescription_rows: list[dict[str, Any]],
    pharmacy_by_id: dict[str, dict[str, Any]],
    poe_id: str,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    result: list[dict[str, Any]] = []
    quality_flags: list[str] = []
    matched_pharmacy_rows: dict[str, dict[str, Any]] = {}
    for prescription in prescription_rows:
        pharmacy, issue = _pharmacy_match(prescription, pharmacy_by_id, poe_id)
        if issue and issue not in quality_flags:
            quality_flags.append(issue)
        pharmacy = pharmacy or {}
        if pharmacy:
            matched_pharmacy_rows[str(pharmacy["pharmacy_id"])] = pharmacy
        item: dict[str, Any] = {}
        for field in MEDICATION_FIELDS:
            value = prescription.get(field)
            if value is None:
                value = pharmacy.get(field)
            item[field] = _clean(value)
        item["source_tables"] = (
            ["prescriptions", "pharmacy"] if pharmacy else ["prescriptions"]
        )
        result.append(item)
    result.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    return result, quality_flags, list(matched_pharmacy_rows.values())


def _detail_documentation_status(field_name: str | None) -> str:
    if field_name in DOCUMENTED_DETAIL_FIELDS_V2_2:
        return "documented_v2_2"
    if field_name in OBSERVED_EXTENSION_DETAIL_FIELDS:
        return "observed_extension"
    return "unclassified"


def _details(rows: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    result = [
        {
            "field_name": _clean(row.get("field_name")),
            "field_value": _clean(row.get("field_value")),
            "documentation_status": _detail_documentation_status(
                _clean(row.get("field_name"))
            ),
        }
        for row in rows
    ]
    result.sort(key=lambda row: ((row["field_name"] or ""), (row["field_value"] or "")))
    return result


def _snapshot(
    order: dict[str, Any],
    detail_rows: list[dict[str, Any]],
    prescription_rows: list[dict[str, Any]],
    pharmacy_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    poe_id = str(order["poe_id"])
    medications, quality_flags, matched_pharmacy_rows = _medications(
        prescription_rows, pharmacy_by_id, poe_id
    )
    return {
        "order_type": _clean(order.get("order_type")),
        "order_subtype": _clean(order.get("order_subtype")),
        "details": _details(detail_rows),
        "medications": medications,
    }, quality_flags, matched_pharmacy_rows


def _facts(snapshot: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    if snapshot.get("order_type"):
        facts.append(f"order_type={snapshot['order_type']}")
    if snapshot.get("order_subtype"):
        facts.append(f"order_subtype={snapshot['order_subtype']}")
    for detail in snapshot["details"]:
        facts.append(f"detail.{detail['field_name']}={detail['field_value']}")
    for index, medication in enumerate(snapshot["medications"], 1):
        prefix = f"medication[{index}]"
        for field in MEDICATION_CLINICAL_FIELDS:
            if medication.get(field):
                facts.append(f"{prefix}.{field}={medication[field]}")
    return facts


def _detail_map(snapshot: dict[str, Any]) -> dict[str, list[str | None]]:
    result: dict[str, list[str | None]] = defaultdict(list)
    for item in snapshot["details"]:
        result[item["field_name"] or "<missing>"].append(item["field_value"])
    return {name: sorted(values, key=lambda value: value or "") for name, values in result.items()}


def _medication_groups(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for medication in snapshot["medications"]:
        base = f"{medication.get('drug_type') or '?'}:{medication.get('drug') or '未给出药名'}"
        result[base].append(medication)
    return dict(result)


def _medication_clinical_view(medication: dict[str, Any]) -> dict[str, str | None]:
    return {field: medication.get(field) for field in MEDICATION_CLINICAL_FIELDS}


def _has_ambiguous_medication_pairing(
    current: dict[str, Any], predecessor: dict[str, Any] | None
) -> bool:
    if predecessor is None:
        return False
    before_groups = _medication_groups(predecessor)
    after_groups = _medication_groups(current)
    for key in set(before_groups) | set(after_groups):
        before = before_groups.get(key, [])
        after = after_groups.get(key, [])
        if before and after and (len(before) > 1 or len(after) > 1):
            before_views = sorted(
                json.dumps(_medication_clinical_view(item), sort_keys=True)
                for item in before
            )
            after_views = sorted(
                json.dumps(_medication_clinical_view(item), sort_keys=True)
                for item in after
            )
            if before_views != after_views:
                return True
    return False


def _clinical_changes(
    action: str,
    current: dict[str, Any],
    predecessor: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if action == "create":
        return [{"kind": "added_order", "label_zh": "新增医嘱", "before": None, "after": _content_text(current)}]
    if action == "discontinue":
        return [{
            "kind": "discontinued_order",
            "label_zh": "停止医嘱",
            "before": _content_text(predecessor) if predecessor else None,
            "after": None,
        }]
    if predecessor is None:
        return []

    changes: list[dict[str, Any]] = []
    for field, label in (("order_type", "医嘱类别"), ("order_subtype", "医嘱子类型")):
        if predecessor.get(field) != current.get(field):
            changes.append({
                "kind": "changed_field",
                "field": field,
                "label_zh": label,
                "before": predecessor.get(field),
                "after": current.get(field),
            })

    before_details = _detail_map(predecessor)
    after_details = _detail_map(current)
    for name in sorted(set(before_details) | set(after_details)):
        if before_details.get(name) != after_details.get(name):
            changes.append({
                "kind": "changed_detail",
                "field": f"detail.{name}",
                "label_zh": DETAIL_LABELS_ZH.get(name, name),
                "before": before_details.get(name),
                "after": after_details.get(name),
            })

    before_medications = _medication_groups(predecessor)
    after_medications = _medication_groups(current)
    for medication_key in sorted(set(before_medications) | set(after_medications)):
        before_group = before_medications.get(medication_key, [])
        after_group = after_medications.get(medication_key, [])
        representative = (after_group or before_group)[0]
        drug_name = representative.get("drug") or "未给出药名"
        if not before_group:
            for after in after_group:
                changes.append({
                    "kind": "added_medication",
                    "field": f"medication.{medication_key}",
                    "label_zh": f"新增药物 {drug_name}",
                    "before": None,
                    "after": _medication_text(after),
                })
            continue
        if not after_group:
            for before in before_group:
                changes.append({
                    "kind": "removed_medication",
                    "field": f"medication.{medication_key}",
                    "label_zh": f"移除药物 {drug_name}",
                    "before": _medication_text(before),
                    "after": None,
                })
            continue
        if len(before_group) != 1 or len(after_group) != 1:
            before_views = sorted(
                json.dumps(_medication_clinical_view(item), sort_keys=True)
                for item in before_group
            )
            after_views = sorted(
                json.dumps(_medication_clinical_view(item), sort_keys=True)
                for item in after_group
            )
            if before_views != after_views:
                changes.append({
                    "kind": "ambiguous_medication_group_change",
                    "field": f"medication.{medication_key}",
                    "label_zh": f"{drug_name}：多条同名药物记录组合变化",
                    "before": [_medication_text(item) for item in before_group],
                    "after": [_medication_text(item) for item in after_group],
                })
            continue
        before = before_group[0]
        after = after_group[0]
        for field in MEDICATION_CLINICAL_FIELDS:
            if before.get(field) != after.get(field):
                changes.append({
                    "kind": "changed_medication_field",
                    "field": f"medication.{medication_key}.{field}",
                    "label_zh": f"{drug_name}：{MEDICATION_FIELD_LABELS_ZH[field]}",
                    "before": before.get(field),
                    "after": after.get(field),
                })
    return changes


def _changes_summary_zh(action: str, changes: list[dict[str, Any]]) -> str:
    if not changes:
        if action == "change":
            return "源数据标记为变更，但可见字段未显示临床内容差异"
        return "没有足够的可见字段描述该事件的临床增量"
    pieces: list[str] = []
    for change in changes:
        before, after = change.get("before"), change.get("after")
        if change["kind"] == "added_order":
            pieces.append(f"新增：{after}")
        elif change["kind"] == "discontinued_order":
            pieces.append(f"停止：{before or '原医嘱内容不可见'}")
        elif before is None:
            pieces.append(f"{change['label_zh']}：新增 {after}")
        elif after is None:
            pieces.append(f"{change['label_zh']}：移除 {before}")
        else:
            pieces.append(f"{change['label_zh']}：{before} → {after}")
    return "；".join(pieces)


def _increment(
    action: str,
    current: dict[str, Any],
    predecessor: dict[str, Any] | None,
) -> dict[str, Any]:
    current_facts = set(_facts(current))
    predecessor_facts = set(_facts(predecessor)) if predecessor else set()
    changes = _clinical_changes(action, current, predecessor)
    if action == "discontinue":
        return {
            "comparison_basis": "linked_predecessor" if predecessor else "unresolved_predecessor",
            "added_facts": ["order_state=discontinued"],
            "removed_facts": sorted(predecessor_facts),
            "unchanged_fact_count": 0,
            "observable_content_change": bool(predecessor_facts),
            "clinical_changes": changes,
            "summary_zh": _changes_summary_zh(action, changes),
        }
    if predecessor:
        return {
            "comparison_basis": "linked_predecessor",
            "added_facts": sorted(current_facts - predecessor_facts),
            "removed_facts": sorted(predecessor_facts - current_facts),
            "unchanged_fact_count": len(current_facts & predecessor_facts),
            "observable_content_change": current_facts != predecessor_facts,
            "clinical_changes": changes,
            "summary_zh": _changes_summary_zh(action, changes),
        }
    return {
        "comparison_basis": "new_order" if action == "create" else "current_event_only",
        "added_facts": sorted(current_facts),
        "removed_facts": [],
        "unchanged_fact_count": 0,
        "observable_content_change": bool(current_facts),
        "clinical_changes": changes,
        "summary_zh": _changes_summary_zh(action, changes),
    }


def _medication_text(medication: dict[str, Any]) -> str:
    pieces = [medication.get("drug") or "未给出药名"]
    dose = " ".join(
        part for part in (medication.get("dose_val_rx"), medication.get("dose_unit_rx")) if part
    )
    if dose:
        pieces.append(dose)
    if medication.get("route"):
        pieces.append(f"途径 {medication['route']}")
    if medication.get("frequency"):
        pieces.append(f"频次 {medication['frequency']}")
    elif medication.get("doses_per_24_hrs"):
        pieces.append(f"每日 {medication['doses_per_24_hrs']} 次")
    return "，".join(pieces)


def _content_text(snapshot: dict[str, Any]) -> str:
    category = snapshot.get("order_type") or "类型缺失"
    category_zh = CATEGORY_LABELS_ZH.get(category, category)
    pieces: list[str] = [f"{category_zh}医嘱"]
    if snapshot.get("order_subtype"):
        pieces.append(str(snapshot["order_subtype"]))
    if snapshot["medications"]:
        pieces.append("；".join(_medication_text(item) for item in snapshot["medications"]))
    if snapshot["details"]:
        detail_text = "；".join(
            f"{DETAIL_LABELS_ZH.get(item['field_name'] or '', item['field_name'])}：{item['field_value']}"
            for item in snapshot["details"]
        )
        pieces.append(detail_text)
    return "，".join(pieces)


def _content_specificity(snapshot: dict[str, Any]) -> str:
    if snapshot["medications"]:
        return "entity_specific"
    if snapshot["details"]:
        return "attribute_enriched"
    if snapshot.get("order_subtype"):
        return "subtype_only"
    return "category_only"


def _resolution_sources(snapshot: dict[str, Any]) -> list[str]:
    sources = ["poe"]
    if snapshot["details"]:
        sources.append("poe_detail")
    if snapshot["medications"]:
        sources.append("prescriptions")
    if any("pharmacy" in item.get("source_tables", []) for item in snapshot["medications"]):
        sources.append("pharmacy")
    return sources


def _medication_resolution(snapshot: dict[str, Any]) -> dict[str, int]:
    medications = snapshot["medications"]
    return {
        "medication_count": len(medications),
        "with_drug": sum(bool(item.get("drug")) for item in medications),
        "with_dose": sum(
            bool(item.get("dose_val_rx") and item.get("dose_unit_rx"))
            for item in medications
        ),
        "with_route": sum(bool(item.get("route")) for item in medications),
        "with_frequency": sum(
            bool(item.get("frequency") or item.get("doses_per_24_hrs"))
            for item in medications
        ),
    }


def _root_and_position(
    order: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> tuple[str | None, int, bool, bool]:
    current = order
    seen: set[str] = set()
    position = 0
    cycle = False
    while _clean(current.get("discontinue_of_poe_id")):
        current_id = str(current.get("poe_id"))
        if current_id in seen:
            cycle = True
            return None, position, cycle, False
        seen.add(current_id)
        predecessor_id = str(current["discontinue_of_poe_id"])
        predecessor = by_id.get(predecessor_id)
        if predecessor is None:
            return None, position, cycle, False
        current = predecessor
        position += 1
    return str(current.get("poe_id")), position, cycle, True


def _validate_order(
    order: dict[str, Any], record_subject_id: str, record_hadm_id: str
) -> list[str]:
    if not isinstance(order, dict):
        raise PoeTimelineError("each poe row must be an object")
    missing = [field for field in REQUIRED_POE_FIELDS if _clean(order.get(field)) is None]
    if missing:
        raise PoeTimelineError(f"poe row is missing required fields: {', '.join(missing)}")
    subject_id = _clean(order.get("subject_id"))
    hadm_id = _clean(order.get("hadm_id"))
    if subject_id != record_subject_id:
        raise PoeTimelineError(
            f"poe subject_id {subject_id} conflicts with archive subject_id {record_subject_id}"
        )
    if hadm_id is not None and hadm_id != record_hadm_id:
        raise PoeTimelineError(
            f"poe hadm_id {hadm_id} conflicts with archive hadm_id {record_hadm_id}"
        )
    expected_poe_id = f"{subject_id}-{_clean(order.get('poe_seq'))}"
    return [] if _clean(order.get("poe_id")) == expected_poe_id else ["poe_id_format_mismatch"]


def _action_from_transaction(
    transaction_raw: str | None,
) -> tuple[str, str, list[str]]:
    if transaction_raw in ACTION_LABELS:
        action, label = ACTION_LABELS[transaction_raw]
        return action, label, []
    if transaction_raw in OFFICIAL_TRANSACTION_TYPES:
        return (
            "uninterpreted",
            f"未解释的官方操作 {transaction_raw}：",
            ["official_transaction_semantics_unresolved"],
        )
    if transaction_raw is None:
        return "unknown", "缺失操作：", ["missing_transaction_type"]
    return "unknown", f"未知操作 {transaction_raw}：", ["unknown_transaction_type"]


def _unique_rows_by_pharmacy_id(
    *row_groups: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for rows in row_groups:
        for row in rows:
            pharmacy_id = _clean(row.get("pharmacy_id"))
            if pharmacy_id:
                result[pharmacy_id] = row
    return list(result.values())


def parse_admission(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse one raw admission archive record into chronologically sorted POE events."""
    try:
        hosp = record["mimic_iv_hosp"]
        orders = hosp["poe"]
        detail_rows = hosp["poe_detail"]
        prescription_rows = hosp["prescriptions"]
        pharmacy_rows = hosp["pharmacy"]
    except (KeyError, TypeError) as exc:
        raise PoeTimelineError(f"missing raw archive field: {exc}") from exc
    if not all(isinstance(rows, list) for rows in (orders, detail_rows, prescription_rows, pharmacy_rows)):
        raise PoeTimelineError("poe, poe_detail, prescriptions, and pharmacy must be lists")

    record_subject_id = _clean(record.get("subject_id"))
    record_hadm_id = _clean(record.get("hadm_id"))
    if record_subject_id is None or record_hadm_id is None:
        raise PoeTimelineError("archive subject_id and hadm_id are required")

    order_quality_flags: dict[str, list[str]] = {}
    for order in orders:
        flags = _validate_order(order, record_subject_id, record_hadm_id)
        order_quality_flags[str(order["poe_id"])] = flags

    _validate_archive_row_ids(
        detail_rows,
        "poe_detail",
        record_subject_id,
        record_hadm_id,
        require_hadm_id=False,
    )
    _validate_archive_row_ids(
        prescription_rows,
        "prescriptions",
        record_subject_id,
        record_hadm_id,
        require_hadm_id=True,
    )
    _validate_archive_row_ids(
        pharmacy_rows,
        "pharmacy",
        record_subject_id,
        record_hadm_id,
        require_hadm_id=True,
    )

    details_by_id = _index_rows_by_poe_id(detail_rows)
    prescriptions_by_id = _index_rows_by_poe_id(prescription_rows)
    pharmacy_by_poe_id = _index_pharmacy_by_poe_id(pharmacy_rows)
    pharmacy_by_id = _index_pharmacy_by_pharmacy_id(pharmacy_rows)
    by_id = {str(order["poe_id"]): order for order in orders}
    if len(by_id) != len(orders):
        raise PoeTimelineError("duplicate poe_id within admission")

    snapshots: dict[str, dict[str, Any]] = {}
    snapshot_quality_flags: dict[str, list[str]] = {}
    sources: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for order in orders:
        poe_id = str(order["poe_id"])
        linked_details = details_by_id.get(poe_id, [])
        linked_prescriptions = prescriptions_by_id.get(poe_id, [])
        pharmacy_rows_by_poe = pharmacy_by_poe_id.get(poe_id, [])
        _validate_linked_rows(order, linked_details, "poe_detail")
        _validate_linked_rows(order, linked_prescriptions, "prescriptions")
        _validate_linked_rows(order, pharmacy_rows_by_poe, "pharmacy")
        snapshot, medication_flags, matched_pharmacy_rows = _snapshot(
            order, linked_details, linked_prescriptions, pharmacy_by_id
        )
        linked_pharmacy = _unique_rows_by_pharmacy_id(
            pharmacy_rows_by_poe, matched_pharmacy_rows
        )
        for row in matched_pharmacy_rows:
            _validate_linked_rows(order, [row], "pharmacy")
        snapshots[poe_id] = snapshot
        snapshot_quality_flags[poe_id] = [
            *order_quality_flags[poe_id],
            *medication_flags,
        ]
        sources[poe_id] = {
            "poe_detail": linked_details,
            "prescriptions": linked_prescriptions,
            "pharmacy": linked_pharmacy,
        }

    events: list[dict[str, Any]] = []
    for order in sorted(orders, key=_order_key):
        poe_id = str(order["poe_id"])
        transaction_raw = _clean(order.get("transaction_type"))
        action, action_zh, action_flags = _action_from_transaction(transaction_raw)
        predecessor_id = _clean(order.get("discontinue_of_poe_id"))
        successor_id = _clean(order.get("discontinued_by_poe_id"))
        predecessor = snapshots.get(predecessor_id) if predecessor_id else None
        current = snapshots[poe_id]
        display_snapshot = predecessor if action == "discontinue" and predecessor else current
        quality_flags: list[str] = [*snapshot_quality_flags[poe_id], *action_flags]
        if predecessor_id and predecessor is None:
            quality_flags.append("unresolved_predecessor")
        if predecessor_id and predecessor:
            predecessor_order = by_id[predecessor_id]
            if _clean(predecessor_order.get("discontinued_by_poe_id")) != poe_id:
                quality_flags.append("nonreciprocal_predecessor_link")
            if predecessor.get("order_type") != current.get("order_type"):
                quality_flags.append("predecessor_category_mismatch")
            predecessor_time = _clean(predecessor_order.get("ordertime"))
            current_time = _clean(order.get("ordertime"))
            if predecessor_time and current_time and predecessor_time > current_time:
                quality_flags.append("predecessor_time_after_current_event")
        if successor_id:
            successor_order = by_id.get(successor_id)
            if successor_order is None:
                quality_flags.append("unresolved_successor")
            else:
                if _clean(successor_order.get("discontinue_of_poe_id")) != poe_id:
                    quality_flags.append("nonreciprocal_successor_link")
                successor = snapshots[successor_id]
                if successor.get("order_type") != current.get("order_type"):
                    quality_flags.append("successor_category_mismatch")
                successor_time = _clean(successor_order.get("ordertime"))
                current_time = _clean(order.get("ordertime"))
                if successor_time and current_time and successor_time < current_time:
                    quality_flags.append("successor_time_before_current_event")
        increment = _increment(action, current, predecessor)
        if action == "change" and predecessor and not increment["observable_content_change"]:
            quality_flags.append("change_without_observable_delta")
        if action == "change" and _has_ambiguous_medication_pairing(current, predecessor):
            quality_flags.append("ambiguous_medication_pairing")
        content_specificity = _content_specificity(display_snapshot)
        if content_specificity == "category_only":
            quality_flags.append("category_only_no_specific_order_content")
        if any(
            detail.get("field_name") not in DETAIL_LABELS_ZH
            for detail in current["details"]
        ):
            quality_flags.append("unmapped_detail_field")
        root_id, chain_position, cycle, chain_complete = _root_and_position(order, by_id)
        if cycle:
            quality_flags.append("relation_cycle")

        event = {
            "schema": OUTPUT_SCHEMA,
            "subject_id": record_subject_id,
            "hadm_id": record_hadm_id,
            "event_time": _clean(order.get("ordertime")),
            "poe_id": poe_id,
            "poe_seq": _clean(order.get("poe_seq")),
            "action": action,
            "action_raw": transaction_raw,
            "order_status_raw": _clean(order.get("order_status")),
            "clinical_category": {
                "raw": current.get("order_type"),
                "zh": CATEGORY_LABELS_ZH.get(
                    current.get("order_type"), current.get("order_type")
                ),
                "subtype_raw": current.get("order_subtype"),
            },
            "display_text_zh": f"{action_zh}{_content_text(display_snapshot)}",
            "content_specificity": content_specificity,
            "resolution_sources": _resolution_sources(display_snapshot),
            "medication_resolution": _medication_resolution(display_snapshot),
            "order_content": current,
            "incremental_information": increment,
            "relations": {
                "predecessor_poe_id": predecessor_id,
                "successor_poe_id": successor_id,
                "chain_root_poe_id": root_id,
                "chain_position": chain_position,
                "chain_complete": chain_complete,
            },
            "quality_flags": list(dict.fromkeys(quality_flags)),
            "provenance": {
                "current": {"poe": order, **sources[poe_id]},
                "comparison": (
                    {"poe": by_id[predecessor_id], **sources[predecessor_id]}
                    if predecessor_id and predecessor
                    else None
                ),
            },
        }
        events.append(event)
    return events


def _empty_metrics(input_path: Path) -> dict[str, Any]:
    return {
        "schema": {"name": "mimic-poe-timeline-quality-report", "version": "2.0.0"},
        "input": str(input_path.resolve()),
        "admissions": 0,
        "events": 0,
        "action_counts": {},
        "category_counts": {},
        "content_specificity_counts": {},
        "quality_flag_counts": {},
        "detail_field_counts": {},
        "detail_documentation_status_counts": {},
        "unmapped_detail_field_counts": {},
        "events_with_poe_detail": 0,
        "events_with_linked_prescriptions": 0,
        "events_with_linked_pharmacy": 0,
        "events_with_predecessor": 0,
        "change_events_with_observable_delta": 0,
    }


def _update_metrics(metrics: dict[str, Any], event: dict[str, Any]) -> None:
    metrics["events"] += 1
    for metric, value in (
        ("action_counts", event["action"]),
        ("category_counts", event["clinical_category"]["raw"]),
        ("content_specificity_counts", event["content_specificity"]),
    ):
        metrics[metric][str(value)] += 1
    for flag in event["quality_flags"]:
        metrics["quality_flag_counts"][flag] += 1
    for detail in event["order_content"]["details"]:
        field_name = detail.get("field_name") or "<missing>"
        metrics["detail_field_counts"][field_name] += 1
        metrics["detail_documentation_status_counts"][
            detail["documentation_status"]
        ] += 1
        if field_name not in DETAIL_LABELS_ZH:
            metrics["unmapped_detail_field_counts"][field_name] += 1
    current_provenance = event["provenance"]["current"]
    metrics["events_with_poe_detail"] += bool(current_provenance["poe_detail"])
    metrics["events_with_linked_prescriptions"] += bool(
        current_provenance["prescriptions"]
    )
    metrics["events_with_linked_pharmacy"] += any(
        "pharmacy" in medication.get("source_tables", [])
        for medication in event["order_content"]["medications"]
    )
    metrics["events_with_predecessor"] += bool(event["relations"]["predecessor_poe_id"])
    if event["action"] == "change":
        metrics["change_events_with_observable_delta"] += bool(
            event["incremental_information"]["observable_content_change"]
        )


def _serializable_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    result = dict(metrics)
    for name in (
        "action_counts",
        "category_counts",
        "content_specificity_counts",
        "quality_flag_counts",
        "detail_field_counts",
        "detail_documentation_status_counts",
        "unmapped_detail_field_counts",
    ):
        result[name] = dict(sorted(metrics[name].items(), key=lambda item: (-item[1], item[0])))
    events = metrics["events"]
    result["rates"] = {
        "poe_detail_coverage": metrics["events_with_poe_detail"] / events if events else 0.0,
        "linked_prescription_coverage": metrics["events_with_linked_prescriptions"] / events if events else 0.0,
        "linked_pharmacy_enrichment_coverage": metrics["events_with_linked_pharmacy"] / events if events else 0.0,
        "specific_content_coverage": (
            1
            - metrics["content_specificity_counts"].get("category_only", 0) / events
            if events
            else 0.0
        ),
        "resolved_predecessor_rate": (
            1 - metrics["quality_flag_counts"].get("unresolved_predecessor", 0)
            / metrics["events_with_predecessor"]
            if metrics["events_with_predecessor"]
            else 1.0
        ),
        "observable_delta_rate_among_changes": (
            metrics["change_events_with_observable_delta"]
            / metrics["action_counts"].get("change", 0)
            if metrics["action_counts"].get("change", 0)
            else 0.0
        ),
        "detail_field_mapping_coverage": (
            1
            - sum(metrics["unmapped_detail_field_counts"].values())
            / sum(metrics["detail_field_counts"].values())
            if metrics["detail_field_counts"]
            else 1.0
        ),
    }
    return result


def _atomic_text_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    )


def run(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Stream admission JSONL and prepare both outputs before replacing each destination."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    report_path = Path(report_path)
    resolved_paths = {
        input_path.resolve(),
        output_path.resolve(),
        report_path.resolve(),
    }
    if len(resolved_paths) != 3:
        raise PoeTimelineError("input, output, and report paths must be different")
    metrics = _empty_metrics(input_path)
    for name in (
        "action_counts",
        "category_counts",
        "content_specificity_counts",
        "quality_flag_counts",
        "detail_field_counts",
        "detail_documentation_status_counts",
        "unmapped_detail_field_counts",
    ):
        metrics[name] = Counter()

    output_tmp = _atomic_text_writer(output_path)
    report_tmp = None
    try:
        with output_tmp, input_path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if limit is not None and metrics["admissions"] >= limit:
                    break
                try:
                    record = json.loads(line)
                    events = parse_admission(record)
                except (json.JSONDecodeError, PoeTimelineError) as exc:
                    raise PoeTimelineError(f"input line {line_number}: {exc}") from exc
                metrics["admissions"] += 1
                for event in events:
                    output_tmp.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                    _update_metrics(metrics, event)
        result = _serializable_metrics(metrics)
        report_tmp = _atomic_text_writer(report_path)
        with report_tmp:
            json.dump(result, report_tmp, ensure_ascii=False, indent=2)
            report_tmp.write("\n")
        os.replace(output_tmp.name, output_path)
        os.replace(report_tmp.name, report_path)
    except Exception:
        for temporary in (output_tmp, report_tmp):
            if temporary is None:
                continue
            try:
                os.unlink(temporary.name)
            except FileNotFoundError:
                pass
        raise
    return result
