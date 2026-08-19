"""Extract every normalized event for one hospitalization into an auditable JSON."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


FIELD_COMMENTS = {
    "schema_version": "该事件记录遵循的 clinical_event schema 版本。",
    "cleaning_status": "清洗流程对该事件的处理状态，例如 accepted 表示通过清洗门禁。",
    "event_id": "规范化流程生成的事件唯一标识。",
    "entity_id": "该事件所对应实体的稳定标识；可用于跨事件关联同一临床实体。",
    "source_row_id": "原始来源表行的稳定标识，用于追溯回源数据。",
    "subject_id": "患者主体标识；MIMIC 中为去标识化患者 ID。",
    "hadm_id": "一次住院/住院记录标识。",
    "encounter_id": "就诊或 encounter 标识；当前示例中由 hadm 关联生成。",
    "event_kind": "规范化后的事件类型，例如 laboratory_resulted 或 clinical_ordered。",
    "lifecycle_action": "事件生命周期动作，例如 create、change、discontinue；为空表示该事件没有该语义。",
    "status": "来源系统提供的状态值，例如 Active、Inactive、Administered。",
    "assertion": "该事件对临床事实的断言状态，例如 present 表示事实存在。",
    "event_time": "临床事件实际发生、采集、执行或订单创建的时间；检验结果通常对应 charttime。",
    "source_available_time": "原始来源系统声明该信息可见或存储的时间；保留源端原值。",
    "available_time": "经过防泄漏处理后，下游模型最早允许使用该信息的时间。",
    "recorded_time": "系统录入、核验、签署或记录完成的时间，用于审计记录过程。",
    "time_resolution_status": "事件时间是否已可靠解析，例如 resolved、partially_resolved、unresolved。",
    "time_precision": "时间精度，例如 date、second 或 subsecond。",
    "time_policy_id": "生成 event_time/available_time 的版本化时间策略。",
    "time_resolution_reasons": "时间解析、推导或拒绝原因列表。",
    "evidence_phase": "事件在证据链中的阶段；source_event 表示源事件，post_hoc 表示后验记录。",
    "source_concept_id": "来源系统原始概念、项目或代码标识。",
    "concept_id": "术语映射后的标准化概念标识；为空通常表示尚未解析。",
    "preferred_name": "标准化概念的人类可读名称。",
    "source_label": "来源数据中的原始标签或名称。",
    "entity_type": "事件对应的实体类型，例如 laboratory_test、imaging_study 或 clinical_order。",
    "normalization_status": "概念标准化状态，例如 mapped 或 unresolved。",
    "terminology_mapping_version": "使用的术语映射规则版本。",
    "content_specificity": "内容具体程度，例如 entity_specific 表示已达到实体级。",
    "value_numeric": "来源事件中的原始数值结果。",
    "value_text": "来源事件中的原始文本结果。",
    "value_structured_json": "来源事件中的结构化 JSON 值；没有时为 null。",
    "unit": "原始结果单位。",
    "abnormal_flag": "来源系统提供的异常标记。",
    "normalized_value_numeric": "单位标准化后的数值结果。",
    "normalized_value_text": "标准化后的文本结果。",
    "normalized_unit": "标准化后的结果单位。",
    "unit_normalization_status": "单位标准化状态，例如 mapped、unresolved、not_applicable。",
    "source_module": "事件所属的原始数据模块。",
    "source_table": "事件所属的原始来源表。",
    "source_array_index": "事件在原始 JSON 数组或嵌套数组中的位置。",
    "jsonl_line_number": "事件在原始 JSONL 文件中的行号。",
    "raw_row_ref": "可定位到原始文件、表和数组位置的完整引用。",
    "source_action": "来源数据中的原始动作字段；没有时为 null。",
    "quality_flags": "质量检查标记列表。",
    "supporting_source_row_ids": "支持当前事件判定的其他来源行 ID 列表。",
    "supporting_raw_row_refs": "支持当前事件判定的其他原始行引用列表。"
}


def sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("available_time") or ""), str(row.get("event_time") or ""), str(row.get("event_id") or ""))


def extract(source_root: Path, hadm_id: str) -> dict[str, Any]:
    parquet = source_root / "normalized_events.parquet"
    manifest_path = source_root / "normalization_manifest.json"
    if not parquet.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"normalization source incomplete: {source_root}")
    table = pq.read_table(parquet, filters=[("hadm_id", "=", str(hadm_id))])
    events = [dict(row) for row in table.to_pylist()]
    events.sort(key=sort_key)
    subjects = sorted({str(event.get("subject_id")) for event in events if event.get("subject_id") not in (None, "")})
    encounters = sorted({str(event.get("encounter_id")) for event in events if event.get("encounter_id") not in (None, "")})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "extraction_schema": "normalized-hadm-event-bundle/1.0.0",
        "extracted_at_utc": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_root": source_root.as_posix(),
        "source_file": "normalized_events.parquet",
        "source_output_sha256_from_manifest": manifest.get("output_sha256", {}).get("normalized_events.parquet"),
        "hadm_id": str(hadm_id),
        "subject_ids": subjects,
        "encounter_ids": encounters,
        "event_count": len(events),
        "event_fields": table.column_names,
        "field_comments": {field: FIELD_COMMENTS[field] for field in table.column_names},
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--hadm-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = extract(args.source_root, args.hadm_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "hadm_id": bundle["hadm_id"], "event_count": bundle["event_count"], "event_fields": len(bundle["event_fields"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
