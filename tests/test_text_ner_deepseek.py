from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from data_pipeline.text_ner.deepseek_adapter import (
    DeepSeekJsonAdapter,
    DeepSeekPolicyError,
    DeepSeekSettings,
    build_deepseek_json_request,
    enforce_data_policy,
    load_deepseek_policy,
    persist_deepseek_call_result,
)
from data_pipeline.text_ner.deepseek_cost import estimate_deepseek_cost


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY_ROOT / "config" / "text_ner" / "deepseek-api-policy.json"


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        "TEXT_NER_DEEPSEEK_API_KEY": "secret-test-key",
        "TEXT_NER_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "TEXT_NER_DEEPSEEK_MODEL": "deepseek-v4-flash",
        "TEXT_NER_DEEPSEEK_MODEL_REVISION": "DeepSeek-V4-Flash",
    }
    values.update(overrides)
    return values


class DeepSeekAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_deepseek_policy(POLICY_PATH)

    def test_policy_freezes_price_source_and_mimic_block(self) -> None:
        self.assertEqual(
            self.policy["data_policy"]["restricted_mimic_api_transfer"], "blocked"
        )
        self.assertFalse(
            self.policy["data_policy"]["environment_override_allowed"]
        )
        self.assertEqual(
            self.policy["pricing"]["models"]["deepseek-v4-flash"][
                "input_cache_miss"
            ],
            1.0,
        )

    def test_restricted_mimic_is_blocked_before_credentials_or_transport(self) -> None:
        calls: list[object] = []

        def transport(settings: DeepSeekSettings, request: dict[str, object]) -> dict[str, object]:
            calls.append((settings, request))
            raise AssertionError("transport must not be reached")

        adapter = DeepSeekJsonAdapter(self.policy, environ={}, transport=transport)
        with self.assertRaisesRegex(
            DeepSeekPolicyError, "EXTERNAL_MIMIC_TRANSFER_PROHIBITED"
        ):
            adapter.execute(
                {"model": "deepseek-v4-flash"},
                data_classification="restricted_mimic",
            )
        self.assertEqual(calls, [])

    def test_environment_cannot_redirect_to_unfrozen_endpoint(self) -> None:
        with self.assertRaisesRegex(
            DeepSeekPolicyError, "DEEPSEEK_BASE_URL_NOT_FROZEN"
        ):
            DeepSeekSettings.from_environment(
                self.policy,
                _environment(
                    TEXT_NER_DEEPSEEK_BASE_URL="https://example.invalid"
                ),
            )

    def test_environment_cannot_relabel_model_revision(self) -> None:
        with self.assertRaisesRegex(
            DeepSeekPolicyError, "DEEPSEEK_MODEL_REVISION_MISMATCH"
        ):
            DeepSeekSettings.from_environment(
                self.policy,
                _environment(TEXT_NER_DEEPSEEK_MODEL_REVISION="latest"),
            )

    def test_settings_repr_and_audit_never_persist_key(self) -> None:
        settings = DeepSeekSettings.from_environment(self.policy, _environment())
        self.assertNotIn("secret-test-key", repr(settings))

        def transport(
            received: DeepSeekSettings, request: dict[str, object]
        ) -> dict[str, object]:
            self.assertEqual(received.api_key, "secret-test-key")
            return {
                "id": "mock-response",
                "model": request["model"],
                "choices": [
                    {"message": {"role": "assistant", "content": '{"mentions":[]}'}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": 10,
                    "total_tokens": 14,
                },
            }

        request = build_deepseek_json_request(
            model="deepseek-v4-flash",
            prompt="Return JSON.",
            section_text="synthetic text",
            policy=self.policy,
            max_tokens=100,
        )
        result = DeepSeekJsonAdapter(
            self.policy, environ=_environment(), transport=transport
        ).execute(request, data_classification="synthetic")
        self.assertEqual(result["parsed_json"], {"mentions": []})
        serialized = json.dumps(result["audit_record"], sort_keys=True)
        self.assertNotIn("secret-test-key", serialized)
        self.assertEqual(result["audit_record"]["usage"]["total_tokens"], 14)
        self.assertIn("raw_response", result)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "call"
            manifest = persist_deepseek_call_result(target, result)
            self.assertTrue(manifest["immutable"])
            persisted = "".join(
                path.read_text(encoding="utf-8")
                for path in target.iterdir()
                if path.is_file()
            )
            self.assertNotIn("secret-test-key", persisted)
            with self.assertRaises(FileExistsError):
                persist_deepseek_call_result(target, result)

    def test_unknown_data_classification_is_not_an_override(self) -> None:
        with self.assertRaisesRegex(
            DeepSeekPolicyError, "DEEPSEEK_DATA_CLASSIFICATION_NOT_ALLOWED"
        ):
            enforce_data_policy(self.policy, "deidentified_clinical")


class DeepSeekCostTests(unittest.TestCase):
    def test_cost_estimate_is_zero_call_and_scenario_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            (run / "requests").mkdir(parents=True)
            (run / "configuration" / "prompts").mkdir(parents=True)
            manifest = {
                "run_id": "nrun:000000000000000000000000",
                "input": {
                    "partition": "calibration",
                    "evaluation_access_count": 0,
                    "text_units": 2,
                },
            }
            (run / "run_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            requests = [
                {
                    "partition": "calibration",
                    "source_table": "ed.triage",
                    "section_text": "chest pain",
                },
                {
                    "partition": "calibration",
                    "source_table": "note.radiology",
                    "section_text": "No edema.",
                },
            ]
            (run / "requests" / "mention_requests.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in requests),
                encoding="utf-8",
            )
            (run / "configuration" / "prompts" / "mentions.md").write_text(
                "Return JSON mentions.", encoding="utf-8"
            )
            (run / "configuration" / "prompts" / "relations.md").write_text(
                "Return JSON relations.", encoding="utf-8"
            )
            result = estimate_deepseek_cost(run, POLICY_PATH)
            self.assertEqual(result["model_calls"], 0)
            self.assertEqual(result["evaluation_access_count"], 0)
            self.assertEqual(result["input"]["text_units"], 2)
            self.assertFalse(
                result["compliance"]["cost_estimate_authorizes_execution"]
            )
            self.assertLess(
                result["scenarios"]["lean"]["estimated_tokens"]["total"],
                result["scenarios"]["stress"]["estimated_tokens"]["total"],
            )
            self.assertGreater(
                result["scenarios"]["planning"]["cost_by_model"][
                    "deepseek-v4-flash"
                ]["all_input_cache_miss_cny"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
