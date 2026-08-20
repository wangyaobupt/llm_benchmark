# File layout

Canonical spec (Chinese, wins on conflict): [`文件保存规范.md`](文件保存规范.md)

Agents and humans must follow the root spec for every new file. Do not keep a second copy under `docs/`.

## Status of trees

| Status | Paths | New formal work |
|---|---|---|
| Active | `data_pipeline/` (not phenotype), `evaluation_pipeline/`, `config/`, `schemas/`, `tests/`, `scripts/`, `docs/`, `eda/`, `mcq_generation/` | Yes, in the matching folder |
| Frozen | `versions/v1-template-stem/`, `benchmark_common/` | No |
| Invalidated (audit only) | `data_pipeline/archived/phenotype/`, `versions/v2-llm-stem/` | No |
| Historical / out of this round | `rwd_pipeline/`, `data_pipeline/archived/mimic_episode/`, `archived/parquet_to_jsonl/` | No |
| Local, never commit | `data/`, `handoffs/`, `.venv/`, `.env` | Artifacts only |

`data_pipeline.phenotype` is not importable. Audit code uses `data_pipeline.archived.phenotype`. Formal generation is still rejected by `assert_legacy_phenotype_formal_forbidden`.

## Root files allowed

`README.md`, `AGENTS.md`, `BenchMark-进展梳理.md` (sole status snapshot), `文件保存规范.md`, `FILE_LAYOUT.md`, `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `.env.example`.

Do not add other markdown, data, or scripts at repo root. Do not keep a second progress document.

## Where code goes

- Cleaning stations: `data_pipeline/{mimic_raw_archive,clean_clinical_archive,event_pipeline,event_aggregation}/`
- Investigation-selection rebuild: `data_pipeline/investigation_selection/`
- Five-type MCQ visit extract: `data_pipeline/mcq_visit_extract/` (direct MIMIC CSV.GZ → 10k-row visits; resumable; not gold)
- Five-type MCQ visit standardize: `data_pipeline/mcq_visit_standardize/` (terms/units/chief-complaint concepts; does not overwrite extract; not gold)
- Five-type MCQ visit NER: `data_pipeline/mcq_visit_ner/` (span NER on frozen `visits.json` discharge summaries via OpenAI-compatible API; dry-run default; not gold)
- Five-type MCQ visit timeline: `data_pipeline/mcq_visit_timeline/` (merge backfilled clocks with standardized names into a visit event timeline; does not overwrite extract/standardize; not gold)
- Five-type MCQ visit mining: `data_pipeline/mcq_visit_mining/` (X→y rules on the 10k visits; strict gates; no question generation; not gold)
- Text NER: `data_pipeline/text_ner_v2/` (`text_ner/` is v1, do not extend; reads aggregation events, not visit rows)
- Eval chain: `evaluation_pipeline/` — no parallel contract/time/grouping packages
- Scientific protocol and locks: `config/investigation-selection/` (runtime knobs stay out of protocol YAML)
- Tests: `tests/test_<module>.py`
- Repeatable entry: `python -m data_pipeline.<module>`
- One-off tools: `scripts/`; temp debug `_*.py` then delete
- Unimplemented MCQ type specs: `mcq_generation/` (do not recreate root `tasks/`)

## Where docs go

| Folder | Content |
|---|---|
| `docs/design/` | How we build it |
| `docs/methods/` | How we lock/validate |
| `docs/plans/` | Execution plans and gates (v3.1 is the contract) |
| `docs/reports/` | What the result was |
| `docs/reference/` | MIMIC field reference |
| `docs/guides/` | How to run it |
| `docs/literature/` | Literature reviews |
| `docs/review/` | Human-review runbooks |
| `docs/_archive/` | Superseded notes, chat dumps |

Do not recreate `docs/P-2026-LLMBenchwork/`. Patient-level `hadm-*.json` must not be committed.

## `data/` (gitignored)

Do **not** rename existing hardcoded paths this round: `data/RawData`, `data/test_1000_0812`, `data/ner_v2_v2`, `data/phenotype`. New writes go under `data/derived/<stage>/<run>/` or `data/archives/...`. See the Chinese spec for the full tree. Design docs and scripts do not belong in `data/`.

## Decision tree

1. Patient data / model text output → `data/` (untracked)
2. Data-layer code → matching active `data_pipeline/` station
3. Eval-layer code → `evaluation_pipeline/`
4. Protocol / lock → `config/`; schema → `schemas/`
5. Test → `tests/`
6. One-off script → `scripts/`
7. Design / plan / report / literature / runbook → `docs/<bucket>/`
8. Unimplemented question-type spec → `mcq_generation/`
9. Module spec → live with the module
10. Scratch → `_*.py`, then delete
11. None of the above → edit the spec first

## Gitignore additions

`data/`, `*.csv`, `*.parquet`, `*.pdf`, `docs/reports/hadm-*.json`, `.env`, `handoffs/`, `__pycache__/`, `.pytest_cache/`, `.uv-cache/`, `.uv-cache-v2/`, `%SystemDrive%/`.
