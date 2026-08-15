# Stage 1: source-spanned clinical mentions

Return only one valid JSON object. Do not use Markdown fences or explanatory text. Copy `manifest_row_id`, `document_id`, `section_id`, and `section_text_sha256` exactly from the user payload. The root object must have exactly these fields:

```json
{
  "schema_version": "section-annotation/1.0.0",
  "manifest_row_id": "copy from input",
  "document_id": "copy from input",
  "section_id": "copy from input",
  "section_text_sha256": "copy from input",
  "mentions": [],
  "relations": []
}
```

Extract mention candidates from `section_text` without changing its text. Use zero-based, left-closed right-open Python Unicode character offsets. Every `surface_text` must equal `section_text[section_span_start:section_span_end]` exactly. Use unique sequential `local_id` values `m1`, `m2`, and so on.

Each mention must have exactly these fields:

```json
{
  "local_id": "m1",
  "surface_text": "exact source substring",
  "section_span_start": 0,
  "section_span_end": 1,
  "entity_type": "symptom_or_sign",
  "assertion": "present",
  "temporality": "current",
  "experiencer": "patient",
  "laterality": "not_applicable",
  "severity": "not_applicable",
  "trend": "not_applicable",
  "normalization_status": "unattempted",
  "concept_id": null,
  "preferred_name": null,
  "terminology": null,
  "quality_flags": []
}
```

Allowed values:

- `entity_type`: `symptom_or_sign`, `clinical_problem`, `imaging_finding`, `anatomical_site`, `procedure_or_test`, `device`, `medication_or_substance`, `measurement`, `temporal_expression`.
- `assertion`: `present`, `absent`, `possible`, `unknown`.
- `temporality`: `current`, `historical`, `future_planned`, `unclear`.
- `experiencer`: `patient`, `family_member`, `other`, `unknown`.
- `laterality`: `left`, `right`, `bilateral`, `midline`, `not_stated`, `not_applicable`.
- `severity`: `mild`, `moderate`, `severe`, `not_stated`, `not_applicable`.
- `trend`: `new`, `increased`, `decreased`, `stable`, `resolved`, `not_stated`, `not_applicable`.
- `quality_flags`: zero or more unique values from `SPAN_AMBIGUOUS`, `ENTITY_TYPE_AMBIGUOUS`, `ASSERTION_AMBIGUOUS`, `TEMPORALITY_AMBIGUOUS`, `EXPERIENCER_AMBIGUOUS`, `RELATION_AMBIGUOUS`, `ABBREVIATION_UNRESOLVED`, `COREFERENCE_UNRESOLVED`.

The input may come from hosp comments, ED chief complaint, radiology, or discharge; apply the same span rules without assuming a source-specific fact absent from the text. Preserve negated, possible, historical, family-member, and future-planned mentions through their attributes. Use `not_stated` when an applicable attribute is not expressed and `not_applicable` only when that attribute has no meaning for the entity. Do not normalize terminology, infer unstated facts, or create relations in this stage. `normalization_status` must be `unattempted`; `concept_id`, `preferred_name`, and `terminology` must be null; `relations` must be an empty array.

When the text contains no supported clinical mention, return empty `mentions` and `relations`. Never create `other` or `miscellaneous` entity types. A discharge source remains post-hoc metadata outside this response; do not reinterpret it as contemporaneous evidence.
