# Repository Guidelines

## Project Structure

The active data path is `data_pipeline/`. Two parallel tracks: (1) five-type MCQ V3 extracts **directly from MIMIC CSV.GZ** via `mcq_visit_extract` → standardize → timeline → mining (does not read event Parquet or the coronary archive); (2) coronary investigation-selection continues as raw archive → clinical decoding/POE timelines → event cleaning and normalization → lossless aggregation, then `data_pipeline/investigation_selection/` and `evaluation_pipeline/` (split, snapshot, journey, legacy gates). `versions/v1-template-stem/` is a frozen exploratory baseline (the old root `tasks/` tree was merged here and the duplicate removed). `data_pipeline/archived/phenotype/` and `versions/v2-llm-stem/` are invalidated audit material and must not feed the new gold or release chain. Shared tests are in `tests/`, design and operational documents are in `docs/` and `mcq_generation/`, and utility entry points are in `scripts/`. Treat `rwd_pipeline/` as historical handoff material, not as an active implementation or source for current guidance. New files must follow [`文件保存规范.md`](文件保存规范.md) ([English jump](FILE_LAYOUT.md)).

Current-status summary: [`BenchMark-进展梳理.md`](BenchMark-进展梳理.md). Execution contract: [`docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md`](docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md).

## Development and Test Commands

Use Python 3.12 from the repository root. Install locked dependencies with `uv sync` when the environment needs provisioning. Run focused checks with, for example:

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_event_pipeline tests.test_event_aggregation tests.test_legacy_invalidation tests.test_snapshot_visibility tests.test_evaluation_protocol
.\.venv\Scripts\python.exe -m unittest -v tests.test_mcq_visit_extract tests.test_mcq_visit_standardize tests.test_mcq_visit_timeline tests.test_mcq_visit_mining
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; E:\Anaconda3\python.exe -m pytest tests/investigation_selection tests/test_legacy_invalidation.py -q -p no:cacheprovider
```

`versions/v2-llm-stem/smoke_test.py` only audits the invalidated V2 line; a green run is not formal progress.

Run documented pipeline stages through `python -m data_pipeline.<module>`; do not bypass manifests or write over existing outputs. Formal snapshot code must go through `evaluation_pipeline.snapshot`, not raw event payloads.

## Coding and Data Conventions

Use four-space indentation, Python type hints where practical, `snake_case` for modules/functions, and `PascalCase` for classes. Keep transformations deterministic, preserve source lineage, and prefer explicit failure over guessing. Outputs must retain schema/version metadata and use atomic publication. Never commit `.env`, API keys, MIMIC data, or generated large artifacts.

## Evaluation-Layer Constraints

All current benchmark outputs are `exploratory_unreviewed`. Gold remains 0. V1 is a frozen template-stem baseline with weak patient context and high-prior bias; do not treat its probes as validated results. V2 (phenotype features + 1,584 → 134 candidates) is scientifically invalidated (post-hoc ICD, unused `available_time`, full-stay target window, category-only lab orders, split leakage) and cannot enter review, release, or new statistics. The rebuild task is `conditional_order_choice`. This methodology pass reuses the existing coronary cohort (`exposure_policy: reuse_existing_coronary_methodology_cohort`); `protocol.yaml` is `frozen` and `protocol-lock.json` exists. `scientific_protocol.decision_contract` locks: labs use `lab_result_proxy` with target `storetime` and occurrence `charttime`; panels count once and stay out of the component class. Eligibility is protocol-frozen from the 1,000-admission subtype audit (`catalog-lock.json`); Telemetry is `monitoring_only`. Existing investigation-selection modules implement time-point actions; they are not a frozen decision corpus. Do not start formal TF-IDF, lift, or question generation until the 1,000-admission integration audit passes. Keep program validation, independent review, and human approval fail-closed.

## Tests, Commits, and Pull Requests

Name tests `test_*.py`, include regression fixtures for changed contracts, and keep API tests offline with fakes. Use commits such as `feat:`, `fix:`, `docs:`, or `refactor:` followed by a specific change and rationale. Pull requests should describe scope, affected data contracts, commands run, and any unresolved clinical or reproducibility risks; include screenshots for UI changes and never include credentials.
