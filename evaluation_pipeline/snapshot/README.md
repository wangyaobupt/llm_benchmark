# Snapshot visibility module

This module creates auditable, deterministic decision snapshots from current
`clinical_event/1.2.0` mappings. `build_snapshot` is the generic engineering
operation; `build_snapshot_from_boundary` is the authenticated formal-lineage
operation, and `audit_authenticated_snapshot` independently rechecks it.

The scientific policy controls permitted subject splits, event-kind-specific
field whitelists, and deterministic semantic/identity leakage checks. The
implementation then applies every gate independently, so one excluded event
may retain multiple registered reason codes. Missing event or availability
times fail closed with `SNAPSHOT_TIME_UNKNOWN`; malformed non-null times raise
`SnapshotInputError` instead of being silently treated as valid evidence.

`visible_evidence` is the task-facing projection. `event_id` and
`source_event_sha256` are audit metadata and must not be copied into an LLM
prompt. Excluded evidence values are never retained in the manifest.

`batch_size` is runtime configuration. Events and reason codes are sorted
canonically before hashing, so input order and batch size cannot change
`snapshot_sha256`.

Formal journey snapshots must use `build_snapshot_from_boundary`. The connector
authenticates the encounter-boundary HMAC and expected protocol/split/source
lineage, joins only exact `event_id + source_event_sha256` matches from the
current clinical-event contract, enforces the split-specific operation, and
adds boundary lineage to the snapshot manifest. Direct `build_snapshot`
always emits `generic_unverified` and cannot accept or establish formal
lineage. The connector emits `boundary_authenticated` with an HMAC over the
entire snapshot body. Its independent audit revalidates the boundary HMAC,
trusted upstream hashes, single-journey event set, snapshot hash and snapshot
HMAC.

For more than one snapshot, call `authenticate_boundary_context` once and reuse
the returned `AuthenticatedBoundaryContext`. It validates the boundary once,
scans the clinical-event stream once, recomputes every assigned event's journey
HMAC from `subject_id + hadm_id`, verifies event/availability times and
precision against the assignment, and builds reusable per-journey indexes.
This keeps a batch linear in boundary plus source-event size instead of
rescanning both for every journey.
