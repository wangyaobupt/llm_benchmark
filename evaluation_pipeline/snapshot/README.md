# Snapshot visibility module

This module creates an auditable, deterministic decision snapshot from current
`clinical_event/1.2.0` mappings. Its single external operation is
`build_snapshot(events, index_time=..., policy=..., batch_size=...)`.

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
