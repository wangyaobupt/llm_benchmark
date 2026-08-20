"""Per-family isolation contracts. Each family is mined alone; forbidden types never enter X."""

from __future__ import annotations

from dataclasses import dataclass

FAMILY_IDS: tuple[str, ...] = (
    "type1_investigation",
    "type2_diagnosis",
    "type3_medication",
    "type3_procedure",
    "type4_service",
    "type5_disposition",
)

CLINICAL_FEATURE_TYPES = frozenset({"symptom", "physiologic_flag", "absent"})


@dataclass(frozen=True)
class FamilyContract:
    family: str
    allowed_feature_types: frozenset[str]
    forbidden_feature_types: frozenset[str]
    allow_posthoc_diagnosis: bool
    posthoc_flags: tuple[str, ...]


def contract_for(family: str, *, allow_posthoc_diagnosis: bool = False) -> FamilyContract:
    if family not in FAMILY_IDS:
        raise ValueError(f"unknown family {family}")
    presentation = frozenset({"symptom", "physiologic_flag", "age_band", "sex", "admission_type"})
    diagnosis = frozenset({"diagnosis"})
    result_flags = frozenset({"investigation_result_flag"})
    allergy = frozenset({"allergy"})
    leakage = frozenset(
        {
            "diagnosis",
            "investigation_result_flag",
            "medication",
            "procedure",
            "service",
            "disposition",
            "allergy",
        }
    )
    if family == "type1_investigation":
        allowed = presentation
        forbidden = leakage | frozenset({"lab_result", "prescription", "poe_category"})
        return FamilyContract(family, allowed, forbidden, False, ())
    if family == "type2_diagnosis":
        allowed = presentation | result_flags
        forbidden = (leakage - result_flags) | diagnosis
        return FamilyContract(family, allowed, forbidden, False, ("discharge_icd_posthoc",))
    if family in {"type3_medication", "type3_procedure"}:
        allowed = presentation | allergy
        flags = []
        if allow_posthoc_diagnosis:
            allowed = allowed | diagnosis
            flags.append("uses_posthoc_diagnosis")
        else:
            forbidden_extra = diagnosis
            return FamilyContract(
                family,
                allowed,
                (leakage - allergy) | forbidden_extra | result_flags,
                False,
                tuple(flags),
            )
        return FamilyContract(
            family,
            allowed,
            (leakage - allergy - diagnosis) | result_flags,
            True,
            tuple(flags),
        )
    if family in {"type4_service", "type5_disposition"}:
        allowed = presentation
        flags: list[str] = []
        if family == "type5_disposition":
            flags.append("structured_disposition_only")
        if allow_posthoc_diagnosis:
            allowed = allowed | diagnosis
            flags.append("uses_posthoc_diagnosis")
            return FamilyContract(
                family,
                allowed,
                leakage - diagnosis,
                True,
                tuple(flags),
            )
        return FamilyContract(family, allowed, leakage | result_flags, False, tuple(flags))
    raise ValueError(f"unknown family {family}")


class IsolationError(ValueError):
    pass


def assert_isolated(features: list[dict], contract: FamilyContract, *, outcomes: list[dict] | None = None) -> None:
    for feature in features:
        ftype = str(feature.get("feature_type") or "")
        if ftype in contract.forbidden_feature_types:
            raise IsolationError(f"{contract.family} leaked forbidden feature_type={ftype}")
        if ftype not in contract.allowed_feature_types:
            raise IsolationError(f"{contract.family} has unlisted feature_type={ftype}")
    if contract.family == "type1_investigation":
        for outcome in outcomes or []:
            if outcome.get("category_only"):
                raise IsolationError("type1_investigation outcome is POE category_only")
            if str(outcome.get("grain") or "") == "poe_category":
                raise IsolationError("type1_investigation cannot use POE category grain")
            if str(outcome.get("source_event_kind") or "") in {
                "medication_prescribed",
                "procedure_recorded",
                "service_transfer",
            }:
                raise IsolationError("type1_investigation leaked treatment/service outcome")
