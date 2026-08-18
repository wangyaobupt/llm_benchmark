"""Development-only TF-IDF/BM25 retrieval contracts.

This module intentionally accepts decision-level records rather than event rows.
The caller is responsible for producing authenticated, split-assigned decision
documents; this layer refuses records marked as post-hoc or unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


class RetrievalContractError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievalQueryResult:
    decision_id: str
    configuration: str
    neighbors: tuple[Mapping[str, Any], ...]
    candidate_contributions: tuple[Mapping[str, Any], ...]
    refusal_reasons: tuple[str, ...]
    audit: Mapping[str, Any]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _group_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("track_id", "")),
        str(record.get("candidate_class", "")),
        str(record.get("window_id", "")),
    )


def eligible_features(record: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, int]]:
    """Return normalized features and audit counts from one decision document."""
    raw = record.get("features", {})
    if isinstance(raw, Mapping):
        items = raw.items()
    else:
        items = ((feature, 1) for feature in raw)
    accepted: dict[str, float] = {}
    rejected: dict[str, int] = {}
    identity_prefixes = ("subject_", "patient_", "hadm_", "stay_")
    for raw_feature, raw_count in items:
        feature = str(raw_feature)
        reason = None
        if not feature or feature.startswith(identity_prefixes):
            reason = "IDENTITY_FEATURE_EXCLUDED"
        elif isinstance(raw_count, Mapping):
            status = raw_count.get("visibility_status", "visible")
            phase = raw_count.get("evidence_phase", "pre_index")
            if status != "visible":
                reason = "UNRESOLVED_FEATURE_EXCLUDED"
            elif phase == "post_hoc":
                reason = "POST_HOC_FEATURE_EXCLUDED"
            elif raw_count.get("ner_frozen") is False:
                reason = "UNFROZEN_NER_EXCLUDED"
            count = raw_count.get("count", 1)
        else:
            count = raw_count
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        try:
            value = float(count)
        except (TypeError, ValueError):
            rejected["INVALID_FEATURE_COUNT"] = rejected.get("INVALID_FEATURE_COUNT", 0) + 1
            continue
        if not math.isfinite(value) or value <= 0:
            rejected["INVALID_FEATURE_COUNT"] = rejected.get("INVALID_FEATURE_COUNT", 0) + 1
            continue
        accepted[feature] = accepted.get(feature, 0.0) + value
    return accepted, rejected


class RetrievalIndex:
    """Frozen development index with explicit transform/retrieve boundaries."""

    def __init__(self, *, configuration: str = "binary_tfidf", k1: float = 1.2, b: float = 0.75) -> None:
        allowed = {"frequency", "binary_tfidf", "log_count_tfidf", "bm25"}
        if configuration not in allowed:
            raise RetrievalContractError(f"unknown retrieval configuration: {configuration}")
        self.configuration = configuration
        self.k1 = k1
        self.b = b
        self._documents: tuple[dict[str, Any], ...] = ()
        self._vocabulary: tuple[str, ...] = ()
        self._idf: dict[str, float] = {}
        self._df: dict[str, int] = {}
        self._groups: dict[tuple[str, str, str], tuple[dict[str, Any], ...]] = {}
        self._manifest: dict[str, Any] | None = None

    @property
    def manifest(self) -> Mapping[str, Any]:
        if self._manifest is None:
            raise RetrievalContractError("retrieval index has not been fitted")
        return self._manifest

    def fit(self, development_documents: Iterable[Mapping[str, Any]]) -> "RetrievalIndex":
        rows = sorted((dict(row) for row in development_documents), key=lambda row: str(row.get("decision_id", "")))
        ids = [str(row.get("decision_id", "")) for row in rows]
        if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
            raise RetrievalContractError("development decision_id must be non-empty and unique")
        if any(row.get("split") not in (None, "development") for row in rows):
            raise RetrievalContractError("retrieval index may only be fitted on development documents")
        normalized = []
        for row in rows:
            features, rejected = eligible_features(row)
            normalized.append({**row, "decision_id": str(row["decision_id"]), "_features": features, "_rejected": rejected})
        self._documents = tuple(normalized)
        vocabulary = sorted({feature for row in normalized for feature in row["_features"]})
        self._vocabulary = tuple(vocabulary)
        self._df = {feature: sum(feature in row["_features"] for row in normalized) for feature in vocabulary}
        n = len(normalized)
        self._idf = {feature: math.log((n + 1) / (df + 1)) + 1.0 for feature, df in self._df.items()}
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in normalized:
            groups.setdefault(_group_key(row), []).append(row)
        self._groups = {key: tuple(value) for key, value in groups.items()}
        self._manifest = {
            "configuration": self.configuration,
            "document_count": n,
            "vocabulary": list(self._vocabulary),
            "vocabulary_sha256": _stable_hash(list(self._vocabulary)),
            "document_order_sha256": _stable_hash([row["decision_id"] for row in normalized]),
            "idf_sha256": _stable_hash(self._idf),
            "fit_split": "development",
            "validation_or_final_test_read": False,
        }
        return self

    def _score(self, query: Mapping[str, float], document: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
        features = document["_features"]
        overlap = sorted(set(query) & set(features))
        if self.configuration == "frequency":
            contributions = {feature: query[feature] for feature in overlap}
            return sum(contributions.values()), contributions
        if self.configuration == "bm25":
            avg_len = sum(sum(row["_features"].values()) for row in self._documents) / max(len(self._documents), 1)
            length = sum(features.values())
            contributions = {
                feature: self._idf[feature] * (self.k1 + 1) * query[feature]
                / (query[feature] + self.k1 * (1 - self.b + self.b * length / max(avg_len, 1e-12)))
                for feature in overlap
            }
            return sum(contributions.values()), contributions
        query_weights = {}
        doc_weights = {}
        for feature in overlap:
            q_tf = 1.0 if self.configuration == "binary_tfidf" else math.log1p(query[feature])
            d_tf = 1.0 if self.configuration == "binary_tfidf" else math.log1p(features[feature])
            query_weights[feature] = q_tf * self._idf[feature]
            doc_weights[feature] = d_tf * self._idf[feature]
        q_norm = math.sqrt(sum(value * value for value in query_weights.values()))
        d_norm = math.sqrt(sum((value * self._idf[feature]) ** 2 for feature, value in features.items()))
        if not q_norm or not d_norm:
            return 0.0, {}
        contributions = {feature: query_weights[feature] * doc_weights[feature] / (q_norm * d_norm) for feature in overlap}
        return sum(contributions.values()), contributions

    def retrieve(self, query_documents: Iterable[Mapping[str, Any]], *, top_k: int = 10) -> tuple[RetrievalQueryResult, ...]:
        if self._manifest is None:
            raise RetrievalContractError("fit must be called before retrieve")
        if top_k <= 0:
            raise RetrievalContractError("top_k must be positive")
        results = []
        for raw_query in sorted((dict(row) for row in query_documents), key=lambda row: str(row.get("decision_id", ""))):
            query_id = str(raw_query.get("decision_id", ""))
            if not query_id:
                raise RetrievalContractError("query decision_id is required")
            features, rejected = eligible_features(raw_query)
            refusal = [reason for reason, count in sorted(rejected.items()) for _ in range(count)]
            if not features:
                results.append(RetrievalQueryResult(query_id, self.configuration, (), (), tuple(refusal + ["NO_ELIGIBLE_FEATURES"]), {"oov_count": 0}))
                continue
            candidates = []
            oov = set(features) - set(self._vocabulary)
            usable = {feature: value for feature, value in features.items() if feature in self._idf}
            for document in self._groups.get(_group_key(raw_query), ()):
                if document.get("subject_ref") == raw_query.get("subject_ref"):
                    continue
                score, contributions = self._score(usable, document)
                if score > 0:
                    candidates.append({"decision_id": document["decision_id"], "subject_ref": document.get("subject_ref"), "similarity": score, "contributions": contributions})
            candidates.sort(key=lambda row: (-row["similarity"], row["decision_id"]))
            neighbors = tuple(candidates[:top_k])
            contribution_totals: dict[str, float] = {}
            for neighbor in neighbors:
                for feature, value in neighbor["contributions"].items():
                    contribution_totals[feature] = contribution_totals.get(feature, 0.0) + value
            contributions = tuple({"feature": feature, "contribution": contribution_totals[feature]} for feature in sorted(contribution_totals, key=lambda key: (-contribution_totals[key], key)))
            if not neighbors:
                refusal.append("NO_ELIGIBLE_NEIGHBORS")
            results.append(RetrievalQueryResult(query_id, self.configuration, neighbors, contributions, tuple(refusal), {"oov_count": len(oov), "usable_feature_count": len(usable), "same_subject_excluded": True}))
        return tuple(results)
