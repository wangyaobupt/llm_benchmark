"""Loopback-only human annotation and adjudication application.

The app deliberately uses only the Python standard library for HTTP serving.  A
server process is bound to one role so an annotator never receives the other
annotator's task order, decisions, or payloads through the application API.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from typing import Any
from urllib.parse import unquote, urlparse
import uuid

from jsonschema import Draft202012Validator, FormatChecker

from .annotation_contracts import (
    ANNOTATION_DECISION_SCHEMA_VERSION,
    ANNOTATION_PROTOCOL_VERSION,
)
from .annotation_package_audit import DECISION_SCHEMA_PATH
from .annotation_validation import SectionAnnotationValidator


ANNOTATOR_ROLES = ("annotator_a", "annotator_b")
APP_ROLES = (*ANNOTATOR_ROLES, "adjudicator")
MAX_REQUEST_BYTES = 5 * 1024 * 1024


class ReviewAccessError(PermissionError):
    """Raised when a role tries to cross a blinding or release boundary."""


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def browser_utf16_offset_to_python(
    raw_text: str, browser_text: str, utf16_offset: int
) -> int:
    """Map a DOM UTF-16 offset to a Python code-point offset.

    Browsers count astral characters as two UTF-16 code units.  DOM text can
    additionally expose CRLF as LF, so both strings are compared after newline
    normalization while the returned offset remains relative to ``raw_text``.
    """

    if not isinstance(utf16_offset, int) or utf16_offset < 0:
        raise ValueError("UTF16_OFFSET_INVALID")
    consumed_units = 0
    browser_codepoints = 0
    for character in browser_text:
        if consumed_units == utf16_offset:
            break
        units = 2 if ord(character) > 0xFFFF else 1
        if consumed_units + units > utf16_offset:
            raise ValueError("UTF16_OFFSET_SPLITS_SURROGATE_PAIR")
        consumed_units += units
        browser_codepoints += 1
    if consumed_units != utf16_offset:
        raise ValueError("UTF16_OFFSET_OUT_OF_RANGE")

    normalized_prefix_length = len(
        browser_text[:browser_codepoints].replace("\r\n", "\n").replace("\r", "\n")
    )
    normalized_count = 0
    raw_offset = 0
    while raw_offset < len(raw_text) and normalized_count < normalized_prefix_length:
        if raw_text.startswith("\r\n", raw_offset):
            raw_offset += 2
        else:
            raw_offset += 1
        normalized_count += 1
    if normalized_count != normalized_prefix_length:
        raise ValueError("BROWSER_TEXT_DOES_NOT_MATCH_RAW_TEXT")
    raw_normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    browser_normalized = browser_text.replace("\r\n", "\n").replace("\r", "\n")
    if raw_normalized != browser_normalized:
        raise ValueError("BROWSER_TEXT_DOES_NOT_MATCH_RAW_TEXT")
    return raw_offset


class ReviewStore:
    """Small fail-closed interface over one local annotation package."""

    def __init__(self, package_directory: Path, role: str):
        if role not in APP_ROLES:
            raise ValueError(f"ANNOTATION_ROLE_INVALID: {role}")
        self.package_directory = Path(package_directory).resolve()
        self.role = role
        self._lock = threading.RLock()
        self._section_validator = SectionAnnotationValidator()
        decision_schema = json.loads(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(decision_schema)
        self._decision_validator = Draft202012Validator(
            decision_schema, format_checker=FormatChecker()
        )
        self._tasks = self._load_role_tasks()
        self._tasks_by_unit = {
            task["annotation_unit_id"]: task for task in self._tasks
        }
        if len(self._tasks_by_unit) != len(self._tasks):
            raise ValueError("DUPLICATE_ANNOTATION_UNIT_ID")
        self._decisions = self._load_visible_decisions()

    def _load_role_tasks(self) -> list[dict[str, Any]]:
        if self.role in ANNOTATOR_ROLES:
            path = (
                self.package_directory
                / "calibration"
                / self.role
                / "tasks.jsonl"
            )
            tasks = _load_jsonl(path)
            for task in tasks:
                if (
                    task.get("annotator_slot") != self.role
                    or task.get("partition") != "calibration"
                    or task.get("release_status") != "released"
                ):
                    raise ReviewAccessError("ANNOTATOR_TASK_SCOPE_INVALID")
            return tasks

        # The adjudicator uses A only as the canonical task source. B's task file
        # is never merged into annotator sessions and is checked only for set parity.
        a_tasks = _load_jsonl(
            self.package_directory
            / "calibration"
            / "annotator_a"
            / "tasks.jsonl"
        )
        b_tasks = _load_jsonl(
            self.package_directory
            / "calibration"
            / "annotator_b"
            / "tasks.jsonl"
        )
        if {task["annotation_unit_id"] for task in a_tasks} != {
            task["annotation_unit_id"] for task in b_tasks
        }:
            raise ValueError("ANNOTATOR_TASK_SETS_DIFFER")
        return a_tasks

    def _decision_path(self, role: str) -> Path:
        filename = "adjudication.jsonl" if role == "adjudicator" else f"{role}.jsonl"
        return self.package_directory / "decisions" / filename

    def _load_and_validate_decisions(self, role: str) -> list[dict[str, Any]]:
        path = self._decision_path(role)
        rows = _load_jsonl(path)
        for row in rows:
            self._validate_decision_schema(row)
            if row["annotator_role"] != role:
                raise ValueError("DECISION_LOG_ROLE_MISMATCH")
        return rows

    def _load_visible_decisions(self) -> dict[str, list[dict[str, Any]]]:
        if self.role in ANNOTATOR_ROLES:
            return {self.role: self._load_and_validate_decisions(self.role)}
        return {
            role: self._load_and_validate_decisions(role)
            for role in (*ANNOTATOR_ROLES, "adjudicator")
        }

    def _refresh_visible_decisions(self) -> None:
        # A/B and adjudication normally run in separate local processes. Reload
        # the append-only logs at request boundaries so a long-running
        # adjudicator sees newly submitted A/B decisions without a restart.
        self._decisions = self._load_visible_decisions()

    def _validate_decision_schema(self, decision: dict[str, Any]) -> None:
        errors = sorted(
            self._decision_validator.iter_errors(decision),
            key=lambda error: list(error.path),
        )
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.path) or "<root>"
            raise ValueError(f"DECISION_SCHEMA_INVALID: {location}: {error.message}")

    @staticmethod
    def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task["task_id"],
            "annotation_unit_id": task["annotation_unit_id"],
            "manifest_row_id": task["manifest_row_id"],
            "source_table": task["source_table"],
            "note_type": task["note_type"],
            "section_name": task["section_name"],
            "partition": task["partition"],
            "release_status": task["release_status"],
        }

    def _decisions_for_unit(
        self, role: str, annotation_unit_id: str
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in self._decisions.get(role, [])
            if row["annotation_unit_id"] == annotation_unit_id
        ]

    def list_tasks(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_visible_decisions()
        rows = []
        for task in self._tasks:
            unit_id = task["annotation_unit_id"]
            row = self._task_summary(task)
            if self.role in ANNOTATOR_ROLES:
                own = self._decisions_for_unit(self.role, unit_id)
                row["own_decision_count"] = len(own)
                row["latest_own_decision"] = own[-1]["decision"] if own else None
            else:
                a = self._decisions_for_unit("annotator_a", unit_id)
                b = self._decisions_for_unit("annotator_b", unit_id)
                adjudicated = self._decisions_for_unit("adjudicator", unit_id)
                row["adjudication_status"] = (
                    "completed"
                    if adjudicated
                    else "ready"
                    if a and b
                    else "waiting_for_both_annotators"
                )
            rows.append(row)
        return {"role": self.role, "tasks": rows, "total": len(rows)}

    def task_detail(self, annotation_unit_id: str) -> dict[str, Any]:
        with self._lock:
            self._refresh_visible_decisions()
        task = self._tasks_by_unit.get(annotation_unit_id)
        if task is None:
            raise KeyError(annotation_unit_id)
        result: dict[str, Any] = {"task": task}
        if self.role in ANNOTATOR_ROLES:
            result["own_decisions"] = self._decisions_for_unit(
                self.role, annotation_unit_id
            )
            return result
        a = self._decisions_for_unit("annotator_a", annotation_unit_id)
        b = self._decisions_for_unit("annotator_b", annotation_unit_id)
        if not a or not b:
            raise ReviewAccessError("ADJUDICATION_REQUIRES_A_AND_B_DECISIONS")
        result["input_decisions"] = [a[-1], b[-1]]
        result["input_annotations"] = [
            self._read_payload(row) for row in result["input_decisions"]
        ]
        result["adjudication_decisions"] = self._decisions_for_unit(
            "adjudicator", annotation_unit_id
        )
        return result

    def _safe_package_path(self, relative_path: str) -> Path:
        candidate = (self.package_directory / relative_path).resolve()
        if self.package_directory != candidate and self.package_directory not in candidate.parents:
            raise ValueError("ANNOTATION_PAYLOAD_PATH_ESCAPES_PACKAGE")
        return candidate

    def _read_payload(self, decision: dict[str, Any]) -> dict[str, Any] | None:
        relative = decision.get("annotation_payload_path")
        if relative is None:
            return None
        path = self._safe_package_path(relative)
        payload_bytes = path.read_bytes()
        if _sha256_bytes(payload_bytes) != decision["annotation_payload_sha256"]:
            raise ValueError("ANNOTATION_PAYLOAD_HASH_MISMATCH")
        return json.loads(payload_bytes)

    def open_evaluation_tasks(self) -> list[dict[str, Any]]:
        path = self.package_directory / "evaluation" / "tasks.locked.jsonl"
        tasks = _load_jsonl(path)
        blocked = [
            task
            for task in tasks
            if task.get("release_status") == "blocked_pending_calibration"
        ]
        if blocked:
            raise ReviewAccessError("EVALUATION_BLOCKED_PENDING_CALIBRATION")
        return tasks

    def _validate_annotation(
        self, task: dict[str, Any], annotation: dict[str, Any]
    ) -> None:
        manifest_stub = {
            "manifest_row_id": task["manifest_row_id"],
            "document_id": task["document_id"],
            "section_id": task["section_id"],
            "span_sha256": task["section_text_sha256"],
        }
        self._section_validator.validate(
            annotation, manifest_stub, task["section_text"]
        )

    def _decision_by_id(self, decision_id: str) -> dict[str, Any] | None:
        for rows in self._decisions.values():
            for row in rows:
                if row["decision_id"] == decision_id:
                    return row
        return None

    def submit_decision(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._refresh_visible_decisions()
            unit_id = str(request.get("annotation_unit_id") or "")
            task = self._tasks_by_unit.get(unit_id)
            if task is None:
                raise KeyError(unit_id)
            annotator_id = str(request.get("annotator_id") or "").strip()
            if not annotator_id:
                raise ValueError("ANNOTATOR_ID_REQUIRED")
            decision_value = request.get("decision")
            annotation = request.get("annotation")
            if decision_value in {"accept", "correct"} and not isinstance(
                annotation, dict
            ):
                raise ValueError("ANNOTATION_PAYLOAD_REQUIRED")
            if annotation is not None:
                if not isinstance(annotation, dict):
                    raise ValueError("ANNOTATION_PAYLOAD_INVALID")
                self._validate_annotation(task, annotation)

            input_decision_ids = list(request.get("input_decision_ids") or [])
            supersedes = request.get("supersedes_decision_id")
            if self.role in ANNOTATOR_ROLES:
                if input_decision_ids:
                    raise ReviewAccessError("ANNOTATOR_CANNOT_REFERENCE_PEER_DECISIONS")
                if supersedes is not None:
                    prior = self._decision_by_id(str(supersedes))
                    if (
                        prior is None
                        or prior["annotator_role"] != self.role
                        or prior["annotation_unit_id"] != unit_id
                    ):
                        raise ValueError("SUPERSEDED_DECISION_INVALID")
            else:
                if len(input_decision_ids) != 2 or len(set(input_decision_ids)) != 2:
                    raise ValueError("ADJUDICATION_REQUIRES_EXACTLY_TWO_DECISIONS")
                inputs = [self._decision_by_id(value) for value in input_decision_ids]
                if any(value is None for value in inputs):
                    raise ValueError("ADJUDICATION_INPUT_DECISION_NOT_FOUND")
                if {
                    value["annotator_role"] for value in inputs if value is not None
                } != set(ANNOTATOR_ROLES):
                    raise ValueError("ADJUDICATION_REQUIRES_ONE_A_AND_ONE_B_DECISION")
                if any(
                    value["annotation_unit_id"] != unit_id
                    for value in inputs
                    if value is not None
                ):
                    raise ValueError("ADJUDICATION_INPUT_UNIT_MISMATCH")
                if supersedes is not None:
                    prior = self._decision_by_id(str(supersedes))
                    if (
                        prior is None
                        or prior["annotator_role"] != "adjudicator"
                        or prior["annotation_unit_id"] != unit_id
                    ):
                        raise ValueError("SUPERSEDED_DECISION_INVALID")

            token = uuid.uuid4().hex
            decision_id = f"decision:{self.role}:{token}"
            payload_relative: str | None = None
            payload_hash: str | None = None
            payload_bytes: bytes | None = None
            if annotation is not None:
                output_role = (
                    "adjudicated" if self.role == "adjudicator" else self.role
                )
                payload_relative = f"annotations/{output_role}/{token}.json"
                payload_bytes = _canonical_json_bytes(annotation)
                payload_hash = _sha256_bytes(payload_bytes)
            record = {
                "schema_version": ANNOTATION_DECISION_SCHEMA_VERSION,
                "decision_id": decision_id,
                "annotation_unit_id": unit_id,
                "manifest_row_id": task["manifest_row_id"],
                "annotator_role": self.role,
                "annotator_id": annotator_id,
                "protocol_version": ANNOTATION_PROTOCOL_VERSION,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "decision": decision_value,
                "annotation_payload_path": payload_relative,
                "annotation_payload_sha256": payload_hash,
                "reason_codes": list(request.get("reason_codes") or []),
                "comments": request.get("comments"),
                "input_decision_ids": input_decision_ids,
                "supersedes_decision_id": supersedes,
            }
            self._validate_decision_schema(record)

            if payload_bytes is not None and payload_relative is not None:
                payload_path = self._safe_package_path(payload_relative)
                payload_path.parent.mkdir(parents=True, exist_ok=True)
                with payload_path.open("xb") as handle:
                    handle.write(payload_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
            line = _canonical_json_bytes(record)
            decision_path = self._decision_path(self.role)
            decision_path.parent.mkdir(parents=True, exist_ok=True)
            with decision_path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self._decisions.setdefault(self.role, []).append(record)
            return record


INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Text NER 本地双标工具</title>
<style>
body{margin:0;font:14px system-ui;color:#17202a;background:#f4f6f8}header{padding:14px 20px;background:#14324a;color:white}
main{display:grid;grid-template-columns:280px 1fr;gap:16px;padding:16px}.panel{background:white;border:1px solid #ccd5dd;border-radius:8px;padding:14px}
#tasks{max-height:78vh;overflow:auto}.task{display:block;width:100%;padding:9px;margin:4px 0;text-align:left;border:1px solid #d8e0e6;background:white;border-radius:5px}
#sectionText{white-space:pre-wrap;line-height:1.55;padding:12px;border:1px solid #bac7d1;background:#fbfcfd;min-height:120px}.grid{display:grid;grid-template-columns:repeat(3,minmax(140px,1fr));gap:8px}
label{display:flex;flex-direction:column;gap:4px}button{cursor:pointer}.row{display:flex;gap:8px;align-items:center;margin:10px 0}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #dde4ea;padding:6px;text-align:left}.error{color:#a01818}.ok{color:#17643a}
</style></head><body><header><strong>Text NER 本地人工标注</strong> · <span id="role"></span></header>
<main><aside class="panel"><input id="annotator" placeholder="标注者 ID"><div id="tasks"></div></aside>
<section class="panel"><div id="message"></div><h2 id="title">请选择任务</h2><pre id="sectionText"></pre>
<div id="editor" hidden><h3>Mention</h3><div class="grid">
<label>类型<select id="entityType"></select></label><label>Assertion<select id="assertion"></select></label><label>Temporality<select id="temporality"></select></label>
<label>Experiencer<select id="experiencer"></select></label><label>Laterality<select id="laterality"></select></label><label>Severity<select id="severity"></select></label><label>Trend<select id="trend"></select></label><label>Quality flags（可多选）<select id="mentionFlags" multiple></select></label></div>
<div class="row"><button id="addMention">用当前选择新增 mention</button></div><table><thead><tr><th>ID</th><th>Span</th><th>文本</th><th>类型</th><th></th></tr></thead><tbody id="mentions"></tbody></table>
<h3>Relation</h3><div class="grid"><label>Source<select id="sourceMention"></select></label><label>关系<select id="relationType"></select></label><label>Target<select id="targetMention"></select></label><label>Quality flags（可多选）<select id="relationFlags" multiple></select></label></div>
<div class="row"><button id="captureEvidence">记录当前选择为 evidence span</button><span id="evidence"></span><button id="addRelation">新增 relation</button></div>
<table><thead><tr><th>ID</th><th>关系</th><th>Evidence</th><th></th></tr></thead><tbody id="relations"></tbody></table>
<h3>提交</h3><div class="grid"><label>决定<select id="decision"><option>accept</option><option>correct</option><option>reject</option><option>uncertain</option></select></label><label>原因代码（逗号分隔）<input id="reasonCodes"></label><label>备注<input id="comments"></label></div>
<div id="adjudicationInputs"></div><div class="row"><button id="submit">Schema 校验并追加决定</button></div></div></section></main>
<script>
const qualityFlags=['SPAN_AMBIGUOUS','ENTITY_TYPE_AMBIGUOUS','ASSERTION_AMBIGUOUS','TEMPORALITY_AMBIGUOUS','EXPERIENCER_AMBIGUOUS','RELATION_AMBIGUOUS','ABBREVIATION_UNRESOLVED','COREFERENCE_UNRESOLVED'];
const options={entityType:['symptom_or_sign','clinical_problem','imaging_finding','anatomical_site','procedure_or_test','device','medication_or_substance','measurement','temporal_expression'],assertion:['present','absent','possible','unknown'],temporality:['current','historical','future_planned','unclear'],experiencer:['patient','family_member','other','unknown'],laterality:['left','right','bilateral','midline','not_stated','not_applicable'],severity:['mild','moderate','severe','not_stated','not_applicable'],trend:['new','increased','decreased','stable','resolved','not_stated','not_applicable'],relationType:['located_at','has_measurement','has_temporal_context','compared_with','suggestive_of','device_positioned_at','recommendation_for'],mentionFlags:qualityFlags,relationFlags:qualityFlags};
for(const [id,values] of Object.entries(options)){const el=document.getElementById(id); for(const value of values)el.add(new Option(value,value));}
let session,current,annotation,evidenceSpan,inputDecisionIds=[];
function normalizedPrefixLength(text,utf16Offset){return Array.from(text.slice(0,utf16Offset).replace(/\r\n?/g,'\n')).length;}
function normalizedToRawCodePoint(raw,target){let count=0,rawOffset=0;const chars=Array.from(raw);while(rawOffset<chars.length&&count<target){if(chars[rawOffset]==='\r'&&chars[rawOffset+1]==='\n')rawOffset+=2;else rawOffset++;count++;}return rawOffset;}
function domUtf16ToPython(raw,dom,offset){const rawNorm=raw.replace(/\r\n?/g,'\n'),domNorm=dom.replace(/\r\n?/g,'\n');if(rawNorm!==domNorm)throw Error('显示文本与原文不一致');return normalizedToRawCodePoint(raw,normalizedPrefixLength(dom,offset));}
function selectedSpan(){const selection=getSelection(),node=document.getElementById('sectionText').firstChild;if(!node||selection.rangeCount!==1)throw Error('请先选择 exact span');const range=selection.getRangeAt(0);if(range.startContainer!==node||range.endContainer!==node||range.collapsed)throw Error('选择必须完全位于原文中');const raw=current.task.section_text,dom=node.data,start=domUtf16ToPython(raw,dom,range.startOffset),end=domUtf16ToPython(raw,dom,range.endOffset);return{start,end,text:Array.from(raw).slice(start,end).join('')};}
async function api(path,init){const response=await fetch(path,init);const value=await response.json();if(!response.ok)throw Error(value.error||response.statusText);return value;}
function message(value,ok=false){const el=document.getElementById('message');el.className=ok?'ok':'error';el.textContent=value;}
function renderAdjudicationInputs(){const root=document.getElementById('adjudicationInputs');root.replaceChildren();if(!inputDecisionIds.length)return;const heading=document.createElement('h3');heading.textContent='A/B 独立标注（裁决输入）';root.append(heading);for(let i=0;i<current.input_decisions.length;i++){const decision=current.input_decisions[i],payload=current.input_annotations[i],box=document.createElement('div'),title=document.createElement('strong'),pre=document.createElement('pre'),button=document.createElement('button');box.className='panel';title.textContent=decision.annotator_role+' · '+decision.decision+' · '+decision.decision_id;pre.textContent=payload?JSON.stringify(payload,null,2):'本决定没有 annotation payload';button.textContent='以此标注为裁决起点';button.disabled=!payload;button.onclick=()=>{annotation=structuredClone(payload);render();message('已载入 '+decision.annotator_role+' 标注作为裁决起点',true);};box.append(title,pre,button);root.append(box);}}
async function load(){session=await api('/api/session');document.getElementById('role').textContent=session.role;const value=await api('/api/tasks');const root=document.getElementById('tasks');root.innerHTML='';for(const task of value.tasks){const button=document.createElement('button');button.className='task';button.textContent=task.section_name+' · '+task.annotation_unit_id.slice(-8)+(task.adjudication_status?' · '+task.adjudication_status:'');button.onclick=()=>openTask(task.annotation_unit_id);root.append(button);}}
async function openTask(id){try{current=await api('/api/tasks/'+encodeURIComponent(id));annotation=structuredClone(current.task.annotation);inputDecisionIds=(current.input_decisions||[]).map(x=>x.decision_id);document.getElementById('title').textContent=current.task.section_name+' · '+id;document.getElementById('sectionText').textContent=current.task.section_text;document.getElementById('editor').hidden=false;renderAdjudicationInputs();evidenceSpan=null;render();message('');}catch(error){message(error.message);}}
function render(){const mentions=document.getElementById('mentions');mentions.innerHTML='';for(const m of annotation.mentions){const tr=document.createElement('tr');tr.innerHTML=`<td>${m.local_id}</td><td>${m.section_span_start}:${m.section_span_end}</td><td></td><td>${m.entity_type}</td><td><button>删除</button></td>`;tr.children[2].textContent=m.surface_text;tr.querySelector('button').onclick=()=>{annotation.mentions=annotation.mentions.filter(x=>x!==m);annotation.relations=annotation.relations.filter(x=>x.source_mention_id!==m.local_id&&x.target_mention_id!==m.local_id);render();};mentions.append(tr);}for(const id of ['sourceMention','targetMention']){const select=document.getElementById(id);select.innerHTML='';for(const m of annotation.mentions)select.add(new Option(m.local_id+' '+m.surface_text,m.local_id));}const relations=document.getElementById('relations');relations.innerHTML='';for(const r of annotation.relations){const tr=document.createElement('tr');tr.innerHTML=`<td>${r.local_id}</td><td>${r.source_mention_id} ${r.relation_type} ${r.target_mention_id}</td><td></td><td><button>删除</button></td>`;tr.children[2].textContent=r.evidence_text;tr.querySelector('button').onclick=()=>{annotation.relations=annotation.relations.filter(x=>x!==r);render();};relations.append(tr);}}
document.getElementById('addMention').onclick=()=>{try{const s=selectedSpan();annotation.mentions.push({local_id:'m'+(Math.max(0,...annotation.mentions.map(x=>+x.local_id.slice(1)))+1),surface_text:s.text,section_span_start:s.start,section_span_end:s.end,entity_type:entityType.value,assertion:assertion.value,temporality:temporality.value,experiencer:experiencer.value,laterality:laterality.value,severity:severity.value,trend:trend.value,normalization_status:'unattempted',concept_id:null,preferred_name:null,terminology:null,quality_flags:Array.from(mentionFlags.selectedOptions,x=>x.value)});render();message('Mention 已加入',true);}catch(error){message(error.message);}};
document.getElementById('captureEvidence').onclick=()=>{try{evidenceSpan=selectedSpan();document.getElementById('evidence').textContent=evidenceSpan.start+':'+evidenceSpan.end+' '+evidenceSpan.text;message('Evidence span 已记录',true);}catch(error){message(error.message);}};
document.getElementById('addRelation').onclick=()=>{try{if(!evidenceSpan)throw Error('请先记录 evidence span');annotation.relations.push({local_id:'r'+(Math.max(0,...annotation.relations.map(x=>+x.local_id.slice(1)))+1),source_mention_id:sourceMention.value,target_mention_id:targetMention.value,relation_type:relationType.value,evidence_text:evidenceSpan.text,section_evidence_start:evidenceSpan.start,section_evidence_end:evidenceSpan.end,relation_basis:'text_explicit',quality_flags:Array.from(relationFlags.selectedOptions,x=>x.value)});render();message('Relation 已加入',true);}catch(error){message(error.message);}};
document.getElementById('submit').onclick=async()=>{try{const request={annotation_unit_id:current.task.annotation_unit_id,annotator_id:document.getElementById('annotator').value,decision:decision.value,annotation:['accept','correct'].includes(decision.value)?annotation:null,reason_codes:reasonCodes.value.split(',').map(x=>x.trim()).filter(Boolean),comments:comments.value||null,input_decision_ids:inputDecisionIds,supersedes_decision_id:null};const result=await api('/api/decisions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});message('已追加决定 '+result.decision_id,true);await load();}catch(error){message(error.message);}};
load().catch(error=>message(error.message));
</script></body></html>'''


def create_server(
    package_directory: Path,
    role: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ReviewAccessError("ANNOTATION_APP_LOOPBACK_ONLY")
    store = ReviewStore(package_directory, role)

    class Handler(BaseHTTPRequestHandler):
        server_version = "TextNERAnnotation/1.0"

        def _send_json(self, status: int, value: Any) -> None:
            payload = _canonical_json_bytes(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _send_html(self) -> None:
            payload = INDEX_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, error: Exception) -> None:
            if isinstance(error, KeyError):
                status = HTTPStatus.NOT_FOUND
            elif isinstance(error, ReviewAccessError):
                status = HTTPStatus.LOCKED
            elif isinstance(error, (ValueError, json.JSONDecodeError)):
                status = HTTPStatus.BAD_REQUEST
            else:
                status = HTTPStatus.INTERNAL_SERVER_ERROR
            self._send_json(status, {"error": str(error)})

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._send_html()
                elif parsed.path == "/api/session":
                    self._send_json(
                        HTTPStatus.OK,
                        {"role": store.role, "loopback_only": True, "model_calls": 0},
                    )
                elif parsed.path == "/api/tasks":
                    self._send_json(HTTPStatus.OK, store.list_tasks())
                elif parsed.path.startswith("/api/tasks/"):
                    unit_id = unquote(parsed.path[len("/api/tasks/") :])
                    self._send_json(HTTPStatus.OK, store.task_detail(unit_id))
                elif parsed.path == "/api/evaluation":
                    self._send_json(HTTPStatus.OK, store.open_evaluation_tasks())
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
            except Exception as error:  # keep API errors structured
                self._error(error)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            try:
                if urlparse(self.path).path != "/api/decisions":
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
                    return
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("CONTENT_TYPE_MUST_BE_APPLICATION_JSON")
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("REQUEST_SIZE_INVALID")
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send_json(HTTPStatus.CREATED, store.submit_decision(request))
            except Exception as error:  # keep API errors structured
                self._error(error)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the loopback-only text NER human annotation UI."
    )
    parser.add_argument("package_directory", type=Path)
    parser.add_argument("--role", required=True, choices=APP_ROLES)
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> None:
    args = _parser().parse_args()
    server = create_server(
        args.package_directory, args.role, host=args.host, port=args.port
    )
    print(f"Text NER annotation app: http://127.0.0.1:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
