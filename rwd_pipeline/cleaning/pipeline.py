from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import openai
from openai import OpenAI

from .prompts import PROMPTS


MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
CLEANED_FIELDS = tuple(PROMPTS)
OUTPUT_COLUMNS = (
    "subject_id",
    "hadm_id",
    "age_at_encounter",
    "sex",
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "medications_on_admission",
    "investigation_orders",
    "investigation_reports",
    "primary_icd_code",
    "primary_diagnosis_name",
    "primary_icd_version",
    "other_diagnoses",
    "medication_prescriptions",
    "procedures",
    "discharge_record",
)
COPIED_FIELDS = tuple(column for column in OUTPUT_COLUMNS if column not in CLEANED_FIELDS)
CHECKPOINT_CONFIG_HASH = hashlib.sha256(
    json.dumps(
        {
            "model": MODEL,
            "thinking": {"type": "disabled"},
            "input_preprocessing": "remove_deidentification_placeholders_v1",
            "prompts": PROMPTS,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

_DEIDENTIFICATION = re.compile(r"\[\*\*.*?\*\*\]|_{3,}", re.DOTALL)
_FORMAT_ONLY = re.compile(r"[\s\W_]+", re.UNICODE)
_NO_ENTITY_TEXT = {
    "past_medical_history": {"none", "no past medical history", "unknown", "unable to obtain"},
    "medications_on_admission": {"none", "no medications", "unknown", "unable to obtain"},
}

_RETRY_INSTRUCTION = """The previous response was invalid or truncated.
Return one complete JSON object and nothing else. Deduplicate entities before
writing the response, never repeat an entity, and keep only distinct clinical
entities that satisfy the original rules. Keep the response concise and ensure
the JSON array and object are both closed."""


class CleaningError(RuntimeError):
    pass


class ResponseError(CleaningError):
    pass


@dataclass(frozen=True)
class CleaningTask:
    row_index: int
    field: str
    text: str
    input_hash: str


@dataclass(frozen=True)
class CleaningSummary:
    row_count: int
    api_requests: int
    checkpoint_reused: int
    skipped_empty: int
    entity_counts: Mapping[str, int]
    empty_counts: Mapping[str, int]
    output_path: Path
    elapsed_seconds: float


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_entities(value: object) -> List[str]:
    if not isinstance(value, dict) or set(value) != {"entities"}:
        raise ResponseError("LLM response must contain exactly one 'entities' property")
    entities = value["entities"]
    if not isinstance(entities, list) or not all(isinstance(item, str) for item in entities):
        raise ResponseError("LLM response 'entities' must be an array of strings")

    result: List[str] = []
    seen = set()
    for item in entities:
        if _DEIDENTIFICATION.search(item):
            raise ResponseError("LLM response contains a de-identification placeholder")
        cleaned = re.sub(r"\s+", " ", item.strip())
        if not cleaned:
            raise ResponseError("LLM response contains an empty entity")
        comparison = cleaned.casefold()
        if comparison not in seen:
            seen.add(comparison)
            result.append(cleaned)
    return result


def _prepare_llm_text(text: str) -> str:
    without_placeholders = _DEIDENTIFICATION.sub(" ", text)
    return re.sub(r"[ \t]+", " ", without_placeholders).strip()


def _is_effectively_empty(field: str, text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    without_placeholders = _DEIDENTIFICATION.sub("", stripped)
    if not _FORMAT_ONLY.sub("", without_placeholders):
        return True
    normalized = re.sub(r"\s+", " ", stripped).casefold()
    return normalized in _NO_ENTITY_TEXT.get(field, set())


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: int = 180,
        max_attempts: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise CleaningError("DEEPSEEK_API_KEY is empty")
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.client = OpenAI(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def extract(self, field: str, text: str) -> List[str]:
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._request_once(field, text, corrective_retry=attempt > 1)
            except openai.APIStatusError as exc:
                if exc.status_code not in {408, 429} and exc.status_code < 500:
                    raise CleaningError(
                        f"DeepSeek API returned HTTP {exc.status_code}"
                    ) from exc
                last_error = exc
            except (openai.APIConnectionError, ResponseError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                self.sleep(float(2 ** (attempt - 1)))
        raise CleaningError(
            f"DeepSeek request failed after {self.max_attempts} attempts: {last_error}"
        ) from last_error

    def _request_once(
        self, field: str, text: str, corrective_retry: bool = False
    ) -> List[str]:
        messages = [
            {"role": "system", "content": PROMPTS[field]},
            {
                "role": "user",
                "content": json.dumps({field: text}, ensure_ascii=False, separators=(",", ":")),
            },
        ]
        if corrective_retry:
            messages.append({"role": "system", "content": _RETRY_INSTRUCTION})
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=8192,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
        try:
            choice = response.choices[0]
            content = choice.message.content
            if choice.finish_reason == "length":
                raise ResponseError(
                    "DeepSeek response was truncated (finish_reason=length)"
                )
            if not isinstance(content, str) or not content.strip():
                raise ResponseError(
                    f"DeepSeek response has no content (finish_reason={choice.finish_reason})"
                )
            parsed = json.loads(content)
        except ResponseError:
            raise
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
            finish_reason = None
            try:
                finish_reason = response.choices[0].finish_reason
            except (AttributeError, IndexError, TypeError):
                pass
            raise ResponseError(
                f"DeepSeek API returned invalid JSON (finish_reason={finish_reason})"
            ) from exc
        return _normalize_entities(parsed)


def _load_checkpoint(path: Path) -> Dict[Tuple[int, str], Tuple[str, List[str]]]:
    if not path.exists():
        return {}
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    results: Dict[Tuple[int, str], Tuple[str, List[str]]] = {}
    offset = 0
    for index, encoded_line in enumerate(lines):
        line_start = offset
        offset += len(encoded_line)
        if not encoded_line.strip():
            continue
        try:
            line = encoded_line.decode("utf-8")
            item = json.loads(line)
            if item.get("config_sha256") != CHECKPOINT_CONFIG_HASH:
                continue
            row_index = item["row_index"]
            field = item["field"]
            input_hash = item["input_sha256"]
            entities = _normalize_entities({"entities": item["entities"]})
            if not isinstance(row_index, int) or field not in CLEANED_FIELDS:
                raise ValueError
            if not isinstance(input_hash, str) or len(input_hash) != 64:
                raise ValueError
        except (UnicodeDecodeError, KeyError, TypeError, ValueError, json.JSONDecodeError, ResponseError) as exc:
            if index == len(lines) - 1:
                with path.open("r+b") as checkpoint:
                    checkpoint.truncate(line_start)
                break
            raise CleaningError(f"Invalid checkpoint record at line {index + 1}") from exc
        results[(row_index, field)] = (input_hash, entities)
    return results


def _read_tasks(
    input_path: Path,
    checkpoint: Mapping[Tuple[int, str], Tuple[str, List[str]]],
) -> Tuple[int, List[CleaningTask], Dict[Tuple[int, str], List[str]], int, int]:
    tasks: List[CleaningTask] = []
    results: Dict[Tuple[int, str], List[str]] = {}
    skipped_empty = 0
    reused = 0
    with input_path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise CleaningError("Input CSV does not match the required 17-column schema")
        row_count = 0
        for row_count, row in enumerate(reader, start=1):
            row_index = row_count - 1
            for field in CLEANED_FIELDS:
                source_text = row[field]
                text = _prepare_llm_text(source_text)
                if _is_effectively_empty(field, text):
                    results[(row_index, field)] = []
                    skipped_empty += 1
                    continue
                digest = _input_hash(source_text)
                cached = checkpoint.get((row_index, field))
                if cached is not None and cached[0] == digest:
                    results[(row_index, field)] = list(cached[1])
                    reused += 1
                else:
                    tasks.append(CleaningTask(row_index, field, text, digest))
    return row_count, tasks, results, skipped_empty, reused


def _append_checkpoint(handle, task: CleaningTask, entities: Sequence[str]) -> None:
    record = {
        "row_index": task.row_index,
        "field": task.field,
        "input_sha256": task.input_hash,
        "config_sha256": CHECKPOINT_CONFIG_HASH,
        "entities": list(entities),
    }
    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()


def _execute_tasks(
    tasks: Sequence[CleaningTask],
    results: Dict[Tuple[int, str], List[str]],
    checkpoint_path: Path,
    client: DeepSeekClient,
    workers: int,
) -> int:
    if not tasks:
        return 0
    completed = 0
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as checkpoint_handle:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            task_iterator = iter(tasks)
            pending: Dict[Future[List[str]], CleaningTask] = {}

            def submit_next() -> bool:
                try:
                    task = next(task_iterator)
                except StopIteration:
                    return False
                pending[executor.submit(client.extract, task.field, task.text)] = task
                return True

            for _ in range(workers * 2):
                if not submit_next():
                    break
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    task = pending.pop(future)
                    entities = _normalize_entities({"entities": future.result()})
                    results[(task.row_index, task.field)] = entities
                    _append_checkpoint(checkpoint_handle, task, entities)
                    completed += 1
                    if completed % 100 == 0 or completed == len(tasks):
                        print(f"[cleaning] completed={completed}/{len(tasks)}", flush=True)
                    submit_next()
    return completed


def _write_and_validate_output(
    input_path: Path,
    output_path: Path,
    results: Mapping[Tuple[int, str], Sequence[str]],
    expected_rows: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=output_path.parent, delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
            writer = csv.DictWriter(temporary, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            with input_path.open("r", encoding="utf-8", newline="") as source:
                for row_index, row in enumerate(csv.DictReader(source)):
                    for field in CLEANED_FIELDS:
                        row[field] = json.dumps(
                            list(results[(row_index, field)]),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    writer.writerow(row)

        with input_path.open("r", encoding="utf-8", newline="") as original_handle, temp_path.open(
            "r", encoding="utf-8", newline=""
        ) as cleaned_handle:
            original = csv.DictReader(original_handle)
            cleaned = csv.DictReader(cleaned_handle)
            if tuple(cleaned.fieldnames or ()) != OUTPUT_COLUMNS:
                raise CleaningError("Cleaned CSV columns do not match the required schema")
            row_count = 0
            for row_count, (before, after) in enumerate(zip(original, cleaned), start=1):
                for field in COPIED_FIELDS:
                    if before[field] != after[field]:
                        raise CleaningError(f"Copied field changed at row {row_count}: {field}")
                for field in CLEANED_FIELDS:
                    try:
                        entities = json.loads(after[field])
                    except json.JSONDecodeError as exc:
                        raise CleaningError(
                            f"Invalid cleaned JSON at row {row_count}: {field}"
                        ) from exc
                    if not isinstance(entities, list) or not all(
                        isinstance(entity, str) for entity in entities
                    ):
                        raise CleaningError(
                            f"Cleaned field is not a string array at row {row_count}: {field}"
                        )
            if next(original, None) is not None or next(cleaned, None) is not None:
                raise CleaningError("Input and cleaned CSV row counts differ")
            if row_count != expected_rows:
                raise CleaningError("Cleaned CSV row count does not match the input")
        os.replace(temp_path, output_path)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def run_cleaning(
    input_path: Path,
    output_path: Path,
    checkpoint_path: Optional[Path] = None,
    workers: int = 64,
    client: Optional[DeepSeekClient] = None,
) -> CleaningSummary:
    started = time.monotonic()
    input_path = Path(input_path)
    output_path = Path(output_path)
    checkpoint_path = checkpoint_path or output_path.parent / "rwd_benchmark_cleaning_checkpoint.jsonl"
    if not input_path.is_file():
        raise FileNotFoundError(f"Input CSV does not exist: {input_path}")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    checkpoint = _load_checkpoint(checkpoint_path)
    row_count, tasks, results, skipped_empty, reused = _read_tasks(input_path, checkpoint)
    print(
        f"[input] rows={row_count}, requests={len(tasks)}, "
        f"checkpoint_reused={reused}, skipped_empty={skipped_empty}",
        flush=True,
    )
    if tasks and client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise CleaningError("DEEPSEEK_API_KEY is not set")
        client = DeepSeekClient(api_key)
    api_requests = _execute_tasks(tasks, results, checkpoint_path, client, workers) if tasks else 0

    expected_results = row_count * len(CLEANED_FIELDS)
    if len(results) != expected_results:
        raise CleaningError(f"Expected {expected_results} cleaned fields, found {len(results)}")
    _write_and_validate_output(input_path, output_path, results, row_count)

    entity_counts = {
        field: sum(len(results[(row_index, field)]) for row_index in range(row_count))
        for field in CLEANED_FIELDS
    }
    empty_counts = {
        field: sum(not results[(row_index, field)] for row_index in range(row_count))
        for field in CLEANED_FIELDS
    }
    return CleaningSummary(
        row_count=row_count,
        api_requests=api_requests,
        checkpoint_reused=reused,
        skipped_empty=skipped_empty,
        entity_counts=entity_counts,
        empty_counts=empty_counts,
        output_path=output_path.resolve(),
        elapsed_seconds=time.monotonic() - started,
    )
