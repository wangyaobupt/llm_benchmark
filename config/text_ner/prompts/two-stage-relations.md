# Stage 2: explicit text relations

Return only a `section-annotation/1.0.0` JSON object. Copy the supplied Python-validated mentions without changing their IDs, spans, types or attributes. Add only relations whose two endpoints are validated mentions in the same section and whose continuous evidence span covers both endpoints.

Use only the seven frozen relation types from `text-ner-annotation-protocol/1.0.0`. Set `relation_basis` to `text_explicit`. Do not infer relations from medical knowledge, create `related_to`, add new mentions, normalize concepts, or connect facts across sections.
