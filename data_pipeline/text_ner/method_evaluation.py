"""Gold-gated, source-stratified metrics for section-level NER methods."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .annotation_contracts import (
    ASSERTION_VALUES,
    ENTITY_TYPES,
    EXPERIENCER_VALUES,
    TEMPORALITY_VALUES,
)


def _score_counts(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _set_score(predicted: set[tuple[Any, ...]], gold: set[tuple[Any, ...]]) -> dict[str, float | int]:
    return _score_counts(
        len(predicted & gold), len(predicted - gold), len(gold - predicted)
    )


def _records_by_unit(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        annotation = record["annotation"]
        unit = annotation["manifest_row_id"]
        if unit in result:
            raise ValueError(f"DUPLICATE_EVALUATION_UNIT: {unit}")
        result[unit] = record
    return result


def _mention_key(unit: str, mention: dict[str, Any]) -> tuple[Any, ...]:
    return (
        unit,
        mention["section_span_start"],
        mention["section_span_end"],
        mention["entity_type"],
    )


def _mention_sets(
    records: dict[str, dict[str, Any]], entity_type: str | None = None
) -> set[tuple[Any, ...]]:
    return {
        _mention_key(unit, mention)
        for unit, record in records.items()
        for mention in record["annotation"]["mentions"]
        if entity_type is None or mention["entity_type"] == entity_type
    }


def _maximum_overlap_matches(
    predicted: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]], entity_type: str | None = None
) -> int:
    matches = 0
    for unit in sorted(set(predicted) | set(gold)):
        predicted_mentions = [
            mention
            for mention in predicted.get(unit, {"annotation": {"mentions": []}})["annotation"]["mentions"]
            if entity_type is None or mention["entity_type"] == entity_type
        ]
        gold_mentions = [
            mention
            for mention in gold.get(unit, {"annotation": {"mentions": []}})["annotation"]["mentions"]
            if entity_type is None or mention["entity_type"] == entity_type
        ]
        edges: list[list[int]] = []
        for pred in predicted_mentions:
            edges.append(
                [
                    index
                    for index, reference in enumerate(gold_mentions)
                    if pred["entity_type"] == reference["entity_type"]
                    and pred["section_span_start"] < reference["section_span_end"]
                    and reference["section_span_start"] < pred["section_span_end"]
                ]
            )
        owner: dict[int, int] = {}

        def augment(pred_index: int, seen: set[int]) -> bool:
            for gold_index in edges[pred_index]:
                if gold_index in seen:
                    continue
                seen.add(gold_index)
                if gold_index not in owner or augment(owner[gold_index], seen):
                    owner[gold_index] = pred_index
                    return True
            return False

        matches += sum(augment(index, set()) for index in range(len(edges)))
    return matches


def _relaxed_score(
    predicted: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]], entity_type: str | None = None
) -> dict[str, float | int]:
    predicted_count = len(_mention_sets(predicted, entity_type))
    gold_count = len(_mention_sets(gold, entity_type))
    tp = _maximum_overlap_matches(predicted, gold, entity_type)
    return _score_counts(tp, predicted_count - tp, gold_count - tp)


def _attribute_macro_f1(
    predicted: dict[str, dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    attribute: str,
    values: tuple[str, ...],
) -> dict[str, Any]:
    by_value: dict[str, dict[str, float | int]] = {}
    supported_f1: list[float] = []
    for value in values:
        predicted_set = {
            (*_mention_key(unit, mention), value)
            for unit, record in predicted.items()
            for mention in record["annotation"]["mentions"]
            if mention[attribute] == value
        }
        gold_set = {
            (*_mention_key(unit, mention), value)
            for unit, record in gold.items()
            for mention in record["annotation"]["mentions"]
            if mention[attribute] == value
        }
        score = _set_score(predicted_set, gold_set)
        by_value[value] = score
        if predicted_set or gold_set:
            supported_f1.append(float(score["f1"]))
    return {
        "macro_f1": sum(supported_f1) / len(supported_f1) if supported_f1 else None,
        "by_value": by_value,
    }


def _relation_set(records: dict[str, dict[str, Any]]) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for unit, record in records.items():
        annotation = record["annotation"]
        mentions = {
            mention["local_id"]: _mention_key(unit, mention)[1:]
            for mention in annotation["mentions"]
        }
        for relation in annotation["relations"]:
            source = mentions.get(relation["source_mention_id"])
            target = mentions.get(relation["target_mention_id"])
            if source is None or target is None:
                raise ValueError(f"RELATION_ENDPOINT_MISSING: {unit}")
            result.add((unit, source, relation["relation_type"], target))
    return result


def _critical_errors(
    predicted: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]]
) -> dict[str, int]:
    counts = defaultdict(int)
    for unit in set(predicted) & set(gold):
        predicted_mentions = {
            _mention_key(unit, mention): mention
            for mention in predicted[unit]["annotation"]["mentions"]
        }
        gold_mentions = {
            _mention_key(unit, mention): mention
            for mention in gold[unit]["annotation"]["mentions"]
        }
        for key in predicted_mentions.keys() & gold_mentions.keys():
            pred = predicted_mentions[key]
            reference = gold_mentions[key]
            if reference["assertion"] == "absent" and pred["assertion"] == "present":
                counts["negated_as_present"] += 1
            if reference["experiencer"] == "family_member" and pred["experiencer"] == "patient":
                counts["family_as_patient"] += 1
            if reference["temporality"] == "future_planned" and pred["temporality"] == "current":
                counts["recommendation_as_completed"] += 1
    return {
        "negated_as_present": counts["negated_as_present"],
        "family_as_patient": counts["family_as_patient"],
        "recommendation_as_completed": counts["recommendation_as_completed"],
    }


def _evaluate_core(
    predicted: dict[str, dict[str, Any]], gold: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    predicted_mentions = _mention_sets(predicted)
    gold_mentions = _mention_sets(gold)
    return {
        "text_units": {"predicted": len(predicted), "gold": len(gold)},
        "exact_span_type": _set_score(predicted_mentions, gold_mentions),
        "relaxed_span_type": _relaxed_score(predicted, gold),
        "by_entity_type": {
            entity_type: {
                "exact": _set_score(
                    _mention_sets(predicted, entity_type),
                    _mention_sets(gold, entity_type),
                ),
                "relaxed": _relaxed_score(predicted, gold, entity_type),
            }
            for entity_type in ENTITY_TYPES
        },
        "attributes": {
            "assertion": _attribute_macro_f1(
                predicted, gold, "assertion", ASSERTION_VALUES
            ),
            "temporality": _attribute_macro_f1(
                predicted, gold, "temporality", TEMPORALITY_VALUES
            ),
            "experiencer": _attribute_macro_f1(
                predicted, gold, "experiencer", EXPERIENCER_VALUES
            ),
        },
        "relations_exact": _set_score(
            _relation_set(predicted), _relation_set(gold)
        ),
        "critical_errors": _critical_errors(predicted, gold),
    }


def evaluate_section_annotations(
    predictions: Iterable[dict[str, Any]], gold: Iterable[dict[str, Any]] | None
) -> dict[str, Any]:
    prediction_rows = list(predictions)
    gold_rows = [] if gold is None else list(gold)
    if not gold_rows:
        return {
            "status": "not_evaluable",
            "reason_code": "HUMAN_GOLD_UNAVAILABLE",
            "metrics": None,
            "prediction_text_units": len(prediction_rows),
            "gold_text_units": 0,
        }
    predicted = _records_by_unit(prediction_rows)
    references = _records_by_unit(gold_rows)
    sources = sorted(
        {
            record.get("source_table", "unknown")
            for record in prediction_rows + gold_rows
        }
    )
    by_source: dict[str, Any] = {}
    for source in sources:
        predicted_source = {
            unit: record
            for unit, record in predicted.items()
            if record.get("source_table", "unknown") == source
        }
        gold_source = {
            unit: record
            for unit, record in references.items()
            if record.get("source_table", "unknown") == source
        }
        by_source[source] = _evaluate_core(predicted_source, gold_source)
    return {
        "status": "evaluated",
        "reason_code": None,
        "metrics": {
            "overall": _evaluate_core(predicted, references),
            "by_source": by_source,
        },
        "prediction_text_units": len(predicted),
        "gold_text_units": len(references),
    }
