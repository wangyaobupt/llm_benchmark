# Stage 1: source-spanned clinical mentions

Return only a `section-annotation/1.0.0` JSON object. Extract mention candidates from the supplied section without changing its text. Use zero-based, left-closed right-open Python Unicode character offsets. Every `surface_text` must equal `section_text[start:end]` exactly.

Use only the nine entity types and frozen attributes from `text-ner-annotation-protocol/1.0.0`. Preserve negated, possible, historical, family-member and future-planned mentions through their attributes. Do not normalize terminology, infer unstated facts, or create relations in this stage. Set `relations` to an empty array.

When the text does not contain a supported clinical mention, return empty `mentions` and `relations`. Never create `other`, `miscellaneous`, or knowledge-inferred entities.
