# Stage 2: explicit text relations

Return only one valid JSON object. Do not use Markdown fences or explanatory text. Copy `manifest_row_id`, `document_id`, `section_id`, and `section_text_sha256` exactly from the user payload. Copy the complete `validated_mentions` array to `mentions` without adding, deleting, reordering, or changing any field. The root object must have exactly these fields:

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

Add only relations whose two endpoints are supplied validated mentions in the same section and whose continuous evidence span covers both endpoint spans. Use unique sequential `local_id` values `r1`, `r2`, and so on. Each relation must have exactly these fields:

```json
{
  "local_id": "r1",
  "source_mention_id": "m1",
  "target_mention_id": "m2",
  "relation_type": "located_at",
  "evidence_text": "exact continuous source substring covering both mentions",
  "section_evidence_start": 0,
  "section_evidence_end": 1,
  "relation_basis": "text_explicit",
  "quality_flags": []
}
```

`evidence_text` must equal `section_text[section_evidence_start:section_evidence_end]` exactly. Allowed `relation_type` values and directions are:

- `located_at`: finding or problem → anatomical site.
- `has_measurement`: clinical entity → measurement.
- `has_temporal_context`: clinical entity → temporal expression.
- `compared_with`: current entity → historical or reference entity.
- `suggestive_of`: finding → clinical problem.
- `device_positioned_at`: device → anatomical site.
- `recommendation_for`: recommended procedure or test → triggering finding or problem.

`relation_basis` must be `text_explicit`. `quality_flags` may contain only unique values from `SPAN_AMBIGUOUS`, `ENTITY_TYPE_AMBIGUOUS`, `ASSERTION_AMBIGUOUS`, `TEMPORALITY_AMBIGUOUS`, `EXPERIENCER_AMBIGUOUS`, `RELATION_AMBIGUOUS`, `ABBREVIATION_UNRESOLVED`, `COREFERENCE_UNRESOLVED`.

Apply the same relation rules to hosp comments, ED chief complaint, radiology, and discharge. Do not infer relations from medical knowledge, create `related_to`, add new mentions, normalize concepts, connect facts across sections, or relate a mention to itself. If no explicit supported relation exists, return an empty `relations` array while still copying all validated mentions exactly.
