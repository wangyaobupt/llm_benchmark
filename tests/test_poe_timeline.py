from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from poe_timeline import parse_admission, run
from poe_timeline.parser import PoeTimelineError


def order(
    poe_id: str,
    seq: int,
    time: str,
    transaction: str,
    *,
    predecessor: str | None = None,
    successor: str | None = None,
    order_type: str = "Medications",
    subtype: str | None = None,
) -> dict[str, object]:
    return {
        "poe_id": poe_id,
        "poe_seq": str(seq),
        "subject_id": "1",
        "hadm_id": "10",
        "ordertime": time,
        "order_type": order_type,
        "order_subtype": subtype,
        "transaction_type": transaction,
        "discontinue_of_poe_id": predecessor,
        "discontinued_by_poe_id": successor,
        "order_provider_id": "P1",
        "order_status": "Inactive",
    }


def prescription(poe_id: str, seq: int, dose: str) -> dict[str, object]:
    return {
        "subject_id": "1",
        "hadm_id": "10",
        "pharmacy_id": f"RX{seq}",
        "poe_id": poe_id,
        "poe_seq": str(seq),
        "order_provider_id": "P1",
        "starttime": "2150-01-01 10:00:00",
        "stoptime": "2150-01-02 10:00:00",
        "drug_type": "MAIN",
        "drug": "Aspirin",
        "formulary_drug_cd": "ASA81",
        "gsn": None,
        "ndc": None,
        "prod_strength": "81 mg Tablet",
        "form_rx": None,
        "dose_val_rx": dose,
        "dose_unit_rx": "mg",
        "form_val_disp": "1",
        "form_unit_disp": "TAB",
        "doses_per_24_hrs": "1",
        "route": "PO",
    }


def pharmacy(
    pharmacy_id: str,
    *,
    poe_id: str | None = "1-1",
    frequency: str = "BID",
) -> dict[str, object]:
    return {
        "subject_id": "1",
        "hadm_id": "10",
        "pharmacy_id": pharmacy_id,
        "poe_id": poe_id,
        "proc_type": "Unit Dose",
        "frequency": frequency,
    }


def record() -> dict[str, object]:
    return {
        "subject_id": "1",
        "hadm_id": "10",
        "mimic_iv_hosp": {
            "poe": [
                order("1-1", 1, "2150-01-01 09:00:00", "New", successor="1-2"),
                order(
                    "1-2",
                    2,
                    "2150-01-01 11:00:00",
                    "Change",
                    predecessor="1-1",
                    successor="1-3",
                ),
                order("1-3", 3, "2150-01-02 09:00:00", "D/C", predecessor="1-2"),
            ],
            "poe_detail": [],
            "prescriptions": [prescription("1-1", 1, "81"), prescription("1-2", 2, "162")],
            "pharmacy": [],
        },
    }


class PoeTimelineParserTest(unittest.TestCase):
    def test_reconstructs_create_change_discontinue_chain(self) -> None:
        events = parse_admission(record())
        self.assertEqual([event["action"] for event in events], ["create", "change", "discontinue"])
        self.assertIn("Aspirin", events[0]["display_text_zh"])
        self.assertTrue(events[1]["incremental_information"]["observable_content_change"])
        self.assertTrue(any("dose_val_rx=162" in fact for fact in events[1]["incremental_information"]["added_facts"]))
        self.assertIn("剂量值：81 → 162", events[1]["incremental_information"]["summary_zh"])
        self.assertIn("停止用药医嘱", events[2]["display_text_zh"])
        self.assertEqual(events[2]["relations"]["chain_root_poe_id"], "1-1")
        self.assertEqual(events[2]["relations"]["chain_position"], 2)

    def test_preserves_duplicate_eav_values_and_flags_unobservable_change(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order("1-1", 1, "2150-01-01 09:00:00", "New", successor="1-2", order_type="ADT orders", subtype="Admit"),
            order("1-2", 2, "2150-01-01 10:00:00", "Change", predecessor="1-1", order_type="ADT orders", subtype="Admit"),
        ]
        fixture["mimic_iv_hosp"]["prescriptions"] = []
        fixture["mimic_iv_hosp"]["poe_detail"] = [
            {"subject_id": "1", "poe_id": poe_id, "poe_seq": seq, "field_name": "Admit to", "field_value": value}
            for poe_id, seq in (("1-1", "1"), ("1-2", "2"))
            for value in ("Medicine", "Cardiology NP")
        ]
        events = parse_admission(fixture)
        self.assertEqual(len(events[0]["order_content"]["details"]), 2)
        self.assertIn("change_without_observable_delta", events[1]["quality_flags"])
        self.assertIn("未显示临床内容差异", events[1]["incremental_information"]["summary_zh"])

    def test_marks_official_uninterpreted_transaction_and_unresolved_relation(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order("1-9", 9, "2150-01-01 09:00:00", "H", predecessor="outside")
        ]
        fixture["mimic_iv_hosp"]["prescriptions"] = []
        events = parse_admission(fixture)
        self.assertEqual(events[0]["action"], "uninterpreted")
        self.assertIn("未解释的官方操作 H：", events[0]["display_text_zh"])
        self.assertIn(
            "official_transaction_semantics_unresolved", events[0]["quality_flags"]
        )
        self.assertIn("unresolved_predecessor", events[0]["quality_flags"])
        self.assertIsNone(events[0]["relations"]["chain_root_poe_id"])
        self.assertFalse(events[0]["relations"]["chain_complete"])

    def test_distinguishes_invalid_and_missing_transaction_values(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order("1-8", 8, "2150-01-01 08:00:00", "INVALID"),
            order("1-9", 9, "2150-01-01 09:00:00", "New"),
        ]
        fixture["mimic_iv_hosp"]["poe"][1]["transaction_type"] = None
        fixture["mimic_iv_hosp"]["prescriptions"] = []
        events = parse_admission(fixture)
        self.assertIn("unknown_transaction_type", events[0]["quality_flags"])
        self.assertIn("missing_transaction_type", events[1]["quality_flags"])

    def test_streams_complete_admission_jsonl_and_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.jsonl"
            output = root / "admissions-with-poe-timeline.jsonl"
            report = root / "report.json"
            fixture = record()
            fixture["untouched_top_level"] = {"text": "keep me", "items": [1, 2]}
            fixture["mimic_iv_hosp"]["untouched_table"] = [{"value": "unchanged"}]
            source.write_text(json.dumps(fixture) + "\n", encoding="utf-8")
            metrics = run(source, output, report)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(metrics["admissions"], 1)
            self.assertEqual(metrics["events"], 3)
            self.assertEqual(len(rows), 1)
            actual = rows[0]
            events = actual["mimic_iv_hosp"].pop("poe_timeline")
            self.assertEqual(actual, fixture)
            self.assertEqual(
                [event["action"] for event in events],
                ["create", "change", "discontinue"],
            )
            self.assertEqual(
                json.loads(report.read_text(encoding="utf-8"))["action_counts"][
                    "change"
                ],
                1,
            )
            self.assertEqual(metrics["schema"]["version"], "2.0.0")
            self.assertIn("content_specificity_counts", metrics)

    def test_rejects_missing_required_source_table(self) -> None:
        fixture = record()
        del fixture["mimic_iv_hosp"]["pharmacy"]
        with self.assertRaises(PoeTimelineError):
            parse_admission(fixture)

    def test_uses_official_poe_id_link_and_rejects_repeated_key_conflict(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe_detail"] = [{
            "subject_id": "1",
            "poe_id": "1-1",
            "poe_seq": "999",
            "field_name": "Route",
            "field_value": "PO",
        }]
        with self.assertRaisesRegex(PoeTimelineError, "poe_seq conflicts"):
            parse_admission(fixture)

    def test_rejects_colliding_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.jsonl"
            target = root / "same.json"
            source.write_text(json.dumps(record()) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PoeTimelineError, "must be different"):
                run(source, target, target)

    def test_never_falls_back_to_mismatched_pharmacy_id(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order("1-1", 1, "2150-01-01 09:00:00", "New")
        ]
        fixture["mimic_iv_hosp"]["prescriptions"] = [prescription("1-1", 1, "81")]
        fixture["mimic_iv_hosp"]["pharmacy"] = [pharmacy("WRONG")]
        event = parse_admission(fixture)[0]
        self.assertIsNone(event["order_content"]["medications"][0]["frequency"])
        self.assertEqual(
            event["order_content"]["medications"][0]["source_tables"],
            ["prescriptions"],
        )
        self.assertIn("unresolved_pharmacy_id", event["quality_flags"])

    def test_links_pharmacy_by_exact_id_even_when_pharmacy_poe_id_is_null(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order("1-1", 1, "2150-01-01 09:00:00", "New")
        ]
        fixture["mimic_iv_hosp"]["prescriptions"] = [prescription("1-1", 1, "81")]
        fixture["mimic_iv_hosp"]["pharmacy"] = [
            pharmacy("RX1", poe_id=None, frequency="QAM")
        ]
        event = parse_admission(fixture)[0]
        self.assertEqual(event["order_content"]["medications"][0]["frequency"], "QAM")
        self.assertIn("pharmacy", event["resolution_sources"])

    def test_does_not_enrich_from_pharmacy_row_pointing_to_another_poe(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order("1-1", 1, "2150-01-01 09:00:00", "New")
        ]
        fixture["mimic_iv_hosp"]["prescriptions"] = [prescription("1-1", 1, "81")]
        fixture["mimic_iv_hosp"]["pharmacy"] = [
            pharmacy("RX1", poe_id="1-999", frequency="QAM")
        ]
        event = parse_admission(fixture)[0]
        self.assertIsNone(event["order_content"]["medications"][0]["frequency"])
        self.assertIn("pharmacy_poe_id_conflict", event["quality_flags"])

    def test_flags_nonreciprocal_successor_link(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = [
            order(
                "1-1",
                1,
                "2150-01-01 09:00:00",
                "New",
                successor="1-2",
            ),
            order("1-2", 2, "2150-01-01 10:00:00", "D/C"),
        ]
        fixture["mimic_iv_hosp"]["prescriptions"] = []
        event = parse_admission(fixture)[0]
        self.assertIn("nonreciprocal_successor_link", event["quality_flags"])

    def test_rejects_missing_required_poe_field_and_archive_id_conflict(self) -> None:
        missing = record()
        del missing["mimic_iv_hosp"]["poe"][0]["ordertime"]
        with self.assertRaisesRegex(PoeTimelineError, "missing required fields: ordertime"):
            parse_admission(missing)

        conflict = record()
        conflict["mimic_iv_hosp"]["poe"][0]["subject_id"] = "2"
        with self.assertRaisesRegex(PoeTimelineError, "conflicts with archive subject_id"):
            parse_admission(conflict)

    def test_uses_conservative_diff_for_duplicate_same_name_medications(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe"] = fixture["mimic_iv_hosp"]["poe"][:2]
        fixture["mimic_iv_hosp"]["poe"][1]["discontinued_by_poe_id"] = None
        fixture["mimic_iv_hosp"]["prescriptions"] = [
            prescription("1-1", 1, "10"),
            prescription("1-1", 1, "20"),
            prescription("1-2", 2, "10"),
            prescription("1-2", 2, "30"),
        ]
        event = parse_admission(fixture)[1]
        self.assertIn("ambiguous_medication_pairing", event["quality_flags"])
        self.assertTrue(
            any(
                change["kind"] == "ambiguous_medication_group_change"
                for change in event["incremental_information"]["clinical_changes"]
            )
        )
        self.assertFalse(
            any(
                change["kind"] == "changed_medication_field"
                for change in event["incremental_information"]["clinical_changes"]
            )
        )

    def test_embeds_comparison_provenance_and_classifies_detail_origin(self) -> None:
        fixture = record()
        fixture["mimic_iv_hosp"]["poe_detail"] = [{
            "subject_id": "1",
            "poe_id": "1-1",
            "poe_seq": "1",
            "field_name": "Route",
            "field_value": "PO",
        }]
        events = parse_admission(fixture)
        self.assertEqual(
            events[0]["order_content"]["details"][0]["documentation_status"],
            "observed_extension",
        )
        self.assertEqual(
            events[1]["provenance"]["comparison"]["poe"]["poe_id"], "1-1"
        )


if __name__ == "__main__":
    unittest.main()
