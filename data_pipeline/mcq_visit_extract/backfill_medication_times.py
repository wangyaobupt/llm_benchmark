"""Backward-compatible entry for medication time backfill."""

from __future__ import annotations

from data_pipeline.mcq_visit_extract.backfill_times import (
    BackfillError,
    attach_times,
    main,
    run,
)

__all__ = ["BackfillError", "attach_times", "main", "run"]


if __name__ == "__main__":
    raise SystemExit(main())
