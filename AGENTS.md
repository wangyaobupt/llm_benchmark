# Repository Guidelines

## Project Structure

The active data path is `data_pipeline/`: raw MIMIC archives → clinical decoding/POE timelines → event cleaning and normalization → lossless aggregation → visit-level phenotype features. `versions/v2-llm-stem/` is the current MCQ development line for investigation selection; `versions/v1-template-stem/` is a frozen exploratory baseline. Shared tests are in `tests/`, design and operational documents are in `docs/` and `mcq_generation/`, and utility entry points are in `scripts/`. Treat `rwd_pipeline/` as historical handoff material, not as an active implementation or source for current guidance.

## Development and Test Commands

Use Python 3.12 from the repository root. Install locked dependencies with `uv sync` when the environment needs provisioning. Run focused data-pipeline checks with, for example:

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_event_pipeline tests.test_event_aggregation
.\.venv\Scripts\python.exe versions\v2-llm-stem\smoke_test.py
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; E:\Anaconda3\python.exe -m pytest versions/v2-llm-stem/tests -q -p no:cacheprovider
```

Run the documented pipeline stages through `python -m data_pipeline.<module>`; do not bypass manifests or write over existing outputs.

## Coding and Data Conventions

Use four-space indentation, Python type hints where practical, `snake_case` for modules/functions, and `PascalCase` for classes. Keep transformations deterministic, preserve source lineage, and prefer explicit failure over guessing. Outputs must retain schema/version metadata and use atomic publication. Never commit `.env`, API keys, MIMIC data, or generated large artifacts.

## Evaluation-Layer Constraints

All current benchmark outputs are `exploratory_unreviewed`. V1 uses template stems with weak patient context and high-prior selection bias; its thresholds are not clinically frozen and follow-up has no MCQ gold. V2 lets statistics choose the answer and the LLM write only the stem, but currently has limited feature coverage, near-empty laboratory/clinical-order candidate spaces, and 134 formal candidates awaiting human review; gold remains zero until clinical review and freeze gates pass. Keep program validation, independent review, and human approval fail-closed. Do not treat model probes as validated results.

## Tests, Commits, and Pull Requests

Name tests `test_*.py`, include regression fixtures for changed contracts, and keep API tests offline with fakes. Use commits such as `feat:`, `fix:`, `docs:`, or `refactor:` followed by a specific change and rationale. Pull requests should describe scope, affected data contracts, commands run, and any unresolved clinical or reproducibility risks; include screenshots for UI changes and never include credentials.
