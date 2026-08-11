"""Build an auditable field dictionary from the frozen archive contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from data_pipeline.mimic_episode.source_catalog import SOURCE_BY_KEY

from .catalog import ARCHIVE_SOURCES, REFERENCE_SOURCE_KEYS
from .schema import TOP_LEVEL_FIELDS


class FieldDictionaryError(ValueError):
    pass


MODULE_DIR = {
    "mimic_iv_hosp": "hosp",
    "mimic_iv_icu": "icu",
    "mimic_iv_ed": "ed",
    "mimic_iv_note": "note",
}

REFERENCE_MODULE = {
    "d_labitems": "mimic_iv_hosp",
    "d_icd_diagnoses": "mimic_iv_hosp",
    "d_icd_procedures": "mimic_iv_hosp",
    "d_hcpcs": "mimic_iv_hosp",
    "provider": "mimic_iv_hosp",
    "d_items": "mimic_iv_icu",
    "caregiver": "mimic_iv_icu",
}

TOP_LEVEL_DEFINITIONS = {
    "schema": ("object", "NOT NULL", "归档格式标识，固定为 mimic_admission_raw 1.0.0。"),
    "subject_id": ("string", "NOT NULL", "原始患者标识，来自 admissions.subject_id。"),
    "hadm_id": ("string", "NOT NULL", "原始住院标识；一行 JSON 对应一个 hadm_id。"),
    "mimic_iv_hosp": ("object", "NOT NULL", "HOSP 模块容器，内部固定包含16张源表数组。"),
    "mimic_iv_icu": ("object", "NOT NULL", "ICU 模块容器，内部固定包含6张源表数组，不含 chartevents。"),
    "mimic_iv_ed": ("object", "NOT NULL", "ED 模块容器，内部固定包含6张经 edstays 原生关联的源表数组。"),
    "mimic_iv_note": ("object", "NOT NULL", "NOTE 模块容器，内部固定包含4张文书源表数组。"),
}

IDENTIFIER_FIELDS = {
    "subject_id", "hadm_id", "stay_id", "transfer_id", "labevent_id",
    "specimen_id", "microevent_id", "micro_specimen_id", "poe_id", "poe_seq",
    "pharmacy_id", "emar_id", "emar_seq", "note_id", "note_seq", "orderid",
    "linkorderid", "caregiver_id", "provider_id", "admit_provider_id",
    "order_provider_id", "enter_provider_id", "itemid", "spec_itemid", "test_itemid",
    "org_itemid", "ab_itemid", "field_ordinal", "parent_field_ordinal", "seq_num",
}

EVENT_TIME_FIELDS = {
    "admittime", "dischtime", "deathtime", "edregtime", "edouttime", "intime",
    "outtime", "transfertime", "charttime", "chartdate", "starttime", "endtime",
    "ordertime", "scheduletime", "stoptime", "dod", "expirationdate",
}

RECORDED_TIME_FIELDS = {"storetime", "storedate", "entertime", "verifiedtime"}

POST_HOC_TABLES = {
    "diagnoses_icd", "diagnosis", "procedures_icd", "hcpcsevents", "drgcodes",
    "discharge", "discharge_detail",
}
ADMINISTRATIVE_END_FIELDS = {
    "dischtime", "deathtime", "discharge_location", "hospital_expire_flag", "dod",
}

MARKDOWN_ROW = re.compile(
    r"^\|\s*`(?P<field>[^`]+)`\s*\|\s*(?P<type>[^|]+?)\s*\|"
    r"\s*(?P<constraint>[^|]+?)\s*\|\s*(?P<description>[^|]+?)\s*\|\s*$"
)


def parse_schema_table(text: str) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = MARKDOWN_ROW.match(line)
        if not match:
            continue
        values = {key: value.strip() for key, value in match.groupdict().items()}
        fields[values["field"]] = values
    return fields


def archive_type(constraint: str) -> str:
    return "string" if "NOT NULL" in constraint.upper() else "string | null"


def key_role(field: str, table: str) -> str:
    if field == "subject_id":
        return "患者连接键"
    if field == "hadm_id":
        return "住院连接键" if table != "admissions" else "住院主键"
    if field == "stay_id":
        return "ED/ICU stay连接键"
    if field in IDENTIFIER_FIELDS or field.endswith("_id"):
        return "源记录标识或连接键"
    return "非键字段"


def time_semantics(field: str) -> str:
    if field in RECORDED_TIME_FIELDS:
        return "recorded/available time：系统记录、存储、录入或核验时间"
    if field in EVENT_TIME_FIELDS:
        return "event time：事件发生、开始、结束或临床标记时间"
    if field.endswith("time") or field.endswith("date"):
        return "源时间字段：使用前须按源表确认事件/可用语义"
    return "非时间字段"


def information_phase(table: str, field: str) -> str:
    if table in POST_HOC_TABLES:
        return "post_hoc（后验资料）"
    if table == "patients" and field != "dod":
        return "baseline（患者背景）"
    if table == "edstays" and field in {"outtime", "disposition"}:
        return "clinical_end（急诊结局）"
    if field in ADMINISTRATIVE_END_FIELDS:
        return "administrative_end（住院结局）"
    if field in IDENTIFIER_FIELDS or field.endswith("_id"):
        return "identifier（连接/审计）"
    return "source_event（按源事件时间判断）"


def benchmark_restriction(table: str, field: str, phase: str) -> str:
    if phase.startswith("post_hoc") or phase.startswith("administrative_end"):
        return "禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。"
    if phase.startswith("clinical_end"):
        return "仅在决策时点已到相应临床阶段时可见；更早快照必须屏蔽。"
    if phase.startswith("baseline"):
        return "可作为患者背景；年龄须在清洗sidecar中按住院时点解释。"
    if phase.startswith("identifier"):
        return "仅用于连接、去重和审计，不进入模型题干。"
    if field in RECORDED_TIME_FIELDS:
        return "用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。"
    if field in EVENT_TIME_FIELDS or field.endswith("time") or field.endswith("date"):
        return "事件时间与可用时间均不晚于决策时点时，才可进入题型快照。"
    if field == "text" or "comment" in field:
        return "按决策时点截取；患者原文不得发送到未经批准的外部API。"
    return "随所属源行执行决策时点过滤和未来信息泄漏测试。"


def _reference_path(reference_root: Path, module: str, source_key: str) -> Path:
    filename = "diagnosis.md" if source_key == "ed_diagnosis" else f"{source_key}.md"
    return reference_root / MODULE_DIR[module] / filename


def _source_rows(
    *, source_key: str, output_key: str, module: str, scope: str,
    reference_root: Path,
) -> list[dict[str, Any]]:
    spec = SOURCE_BY_KEY[source_key]
    path = _reference_path(reference_root, module, source_key)
    if not path.exists():
        raise FieldDictionaryError(f"缺少字段参考文档: {path}")
    reference_fields = parse_schema_table(path.read_text(encoding="utf-8"))
    missing = [field for field in spec.header if field not in reference_fields]
    extra = [field for field in reference_fields if field not in spec.header]
    if missing or extra:
        raise FieldDictionaryError(
            f"{source_key} 参考表结构与实际表头不一致; missing={missing}; extra={extra}"
        )
    rows: list[dict[str, Any]] = []
    for field in spec.header:
        ref = reference_fields[field]
        phase = information_phase(output_key, field)
        rows.append({
            "scope": scope,
            "module": module,
            "table": output_key,
            "json_path": (
                f"{module}.{output_key}[].{field}"
                if scope == "archive"
                else f"references.{output_key}[].{field}"
            ),
            "field": field,
            "archive_type": archive_type(ref["constraint"]),
            "source_type": ref["type"],
            "source_constraint": ref["constraint"],
            "description_zh": ref["description"],
            "key_role": key_role(field, output_key),
            "time_semantics": time_semantics(field),
            "information_phase": phase,
            "benchmark_restriction": benchmark_restriction(output_key, field, phase),
        })
    return rows


def build_field_dictionary(reference_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field in TOP_LEVEL_FIELDS:
        source_type, constraint, description = TOP_LEVEL_DEFINITIONS[field]
        phase = "identifier（连接/审计）" if field in {"subject_id", "hadm_id"} else "archive_structure"
        rows.append({
            "scope": "top_level", "module": "root", "table": "root",
            "json_path": field, "field": field, "archive_type": source_type,
            "source_type": source_type, "source_constraint": constraint,
            "description_zh": description, "key_role": key_role(field, "root"),
            "time_semantics": "非时间字段", "information_phase": phase,
            "benchmark_restriction": (
                "仅用于连接、去重和审计，不进入模型题干。"
                if field in {"subject_id", "hadm_id"}
                else "归档结构字段，不作为临床证据。"
            ),
        })
    for source in ARCHIVE_SOURCES:
        rows.extend(_source_rows(
            source_key=source.key, output_key=source.output_key, module=source.module,
            scope="archive", reference_root=reference_root,
        ))
    for source_key in REFERENCE_SOURCE_KEYS:
        module = REFERENCE_MODULE[source_key]
        rows.extend(_source_rows(
            source_key=source_key, output_key=source_key, module=module,
            scope="external_reference", reference_root=reference_root,
        ))
    return rows


def validate_dictionary(rows: list[dict[str, Any]]) -> None:
    paths = [row["json_path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise FieldDictionaryError("字段字典存在重复 JSON 路径")
    if any(not row["description_zh"].strip() for row in rows):
        raise FieldDictionaryError("字段字典存在空中文说明")
    archive_paths = {row["json_path"] for row in rows if row["scope"] == "archive"}
    expected = {
        f"{source.module}.{source.output_key}[].{field}"
        for source in ARCHIVE_SOURCES for field in source.source.header
    }
    if archive_paths != expected:
        raise FieldDictionaryError(
            f"归档字段覆盖不完整: missing={sorted(expected-archive_paths)}; "
            f"extra={sorted(archive_paths-expected)}"
        )
