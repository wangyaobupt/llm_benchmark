# Patient-level subject split

This module has one construction seam: `build_subject_split`. It accepts unique
formal subject IDs, separately listed engineering-audit IDs, and an explicit
configuration. It returns:

- a public manifest containing only stable HMAC-derived `subject_ref` values;
- a protected map containing the raw `subject_id` to `subject_ref` mapping;
- an audit report covering partition isolation, duplicates, empty partitions,
  hashes, and optional input-drift detection.

The required `ratios` keys are `development`, `validation`, and `final_test`.
The module never chooses those scientific parameters. The three values must be
positive and sum to one. `assignment_seed` makes the hash ranking reproducible.
`subject_ref_secret` is used only to derive references and is never written to
an output artifact; callers must store it outside Git and identify it with
`subject_ref_key_id`.

Engineering-audit subjects must be passed through
`engineering_audit_subject_ids`. Any overlap with the formal population fails
closed. They appear as `engineering_audit` with
`formal_test_eligible: false`, and never enter a formal partition.

On the first run, preserve `input_population_sha256` as the baseline. It hashes
only HMAC-derived `subject_ref` values and roles, never raw subject IDs. On later
runs, pass it as `expected_input_sha256`; any addition, removal, or role change
then fails as input drift. `audit_subject_split` can independently recheck
persisted artifacts without requiring the pseudonymization secret.
