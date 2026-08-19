"""Structured LLM client for stem generation and independent auto review.

Reuses the OpenAI-compatible transport / settings / execution gates from the
project's text_ner client (``data_pipeline.text_ner.openai_compatible_api``) so
the v2 pipeline and the NER branch share one HTTP/gate/retry/audit mechanism.
Only the request/response CONTRACT is MCQ-specific: JSON-in, strict-schema-JSON-
out, no clinical free text leaves the machine (the payload carries standardized
feature names, option names, and aggregate statistics only).

A ``FakeStructuredClient`` provides an offline deterministic implementation for
tests and dry runs.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402

from data_pipeline.text_ner.openai_compatible_api import (  # noqa: E402
    GenericApiError,
    OpenAICompatibleSettings,
    _http_transport,
    _sanitized_usage,
    _unwrap_complete_json_fence,
    enforce_execution_gate,
    enforce_endpoint_scope,
)

from .validators import SchemaValidationError, validate_strict  # noqa: E402

_REQUIRED_CONFIG_KEYS = {"environment", "request", "batch", "execution"}


def load_api_config(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != "mcq-openai-compatible-api/1.0.0":
        raise GenericApiError(
            "MCQ_API_CONFIG_VERSION_INVALID", str(value.get("schema_version"))
        )
    missing = _REQUIRED_CONFIG_KEYS - set(value)
    if missing:
        raise GenericApiError(
            "MCQ_API_CONFIG_FIELD_MISSING", ",".join(sorted(missing))
        )
    return value


def _provider_request_options(config: Mapping[str, Any], provider: str) -> dict[str, Any]:
    selected = config.get("provider_request_options", {}).get(provider, {})
    if not isinstance(selected, Mapping):
        return {}
    result: dict[str, Any] = {}
    thinking = selected.get("thinking")
    if isinstance(thinking, Mapping) and thinking.get("type") in {"enabled", "disabled"}:
        result["thinking"] = {"type": thinking["type"]}
    return result


@runtime_checkable
class StructuredLLMClient(Protocol):
    model_name: str

    def complete(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_payload: Mapping[str, Any],
        validator: Draft202012Validator,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (validated_object, metadata). metadata carries usage/attempts."""
        ...


class OpenAIStructuredClient:
    """Real OpenAI-compatible client gated by --execute-api + authorization."""

    def __init__(
        self,
        settings: OpenAICompatibleSettings,
        api_config: Mapping[str, Any],
        *,
        execute: bool = False,
        data_transfer_authorized: bool = False,
        transport=None,
        sleep=time.sleep,
    ):
        self._settings = settings
        self._config = api_config
        self._execute = execute
        self._authorized = data_transfer_authorized
        self._transport = transport or _http_transport
        self._sleep = sleep
        self._request = api_config["request"]
        self._batch = api_config["batch"]
        self._options = _provider_request_options(api_config, settings.provider)

    @property
    def model_name(self) -> str:
        return self._settings.model

    @property
    def request_options(self) -> dict[str, Any]:
        return dict(self._options)

    def complete(self, *, task_type, system_prompt, user_payload, validator):
        enforce_execution_gate(
            execute=self._execute,
            endpoint_scope="external",
            data_transfer_authorized=self._authorized,
        )
        enforce_endpoint_scope(self._settings, "external")
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    user_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            },
        ]
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._request["temperature"],
            "max_tokens": self._request["max_tokens"],
            "stream": False,
        }
        if self._request.get("response_format_json_object"):
            payload["response_format"] = {"type": "json_object"}
        payload.update(self._options)
        endpoint = (
            self._settings.base_url + "/" + self._request["chat_completions_path"].lstrip("/")
        )
        max_retries = int(self._batch.get("maximum_retries", 5))
        delay = float(self._batch.get("retry_initial_seconds", 2.0))

        attempt = 0
        while True:
            attempt += 1
            try:
                raw = self._transport(
                    self._settings, endpoint, payload, int(self._request["timeout_seconds"])
                )
                obj, usage = _parse_structured(raw, validator)
                return obj, {
                    "model": self._settings.model,
                    "attempts": attempt,
                    "usage": usage,
                    "cache_hit": False,
                }
            except GenericApiError as error:
                if not error.retryable or attempt > max_retries:
                    raise
                self._sleep(delay * (2 ** (attempt - 1)))
            except SchemaValidationError as error:
                if attempt > max_retries:
                    raise
                self._sleep(delay * (2 ** (attempt - 1)))


def _parse_structured(raw: Mapping[str, Any], validator: Draft202012Validator):
    try:
        choice = raw["choices"][0]
        message = choice["message"]
        content = message.get("content")
    except (KeyError, IndexError, TypeError) as error:
        raise GenericApiError(
            "MCQ_API_RESPONSE_SHAPE_INVALID", "choices[0].message.content unavailable",
            retryable=True,
        ) from error
    if not isinstance(content, str) or not content.strip():
        raise GenericApiError("MCQ_API_CONTENT_EMPTY", "empty content", retryable=True)
    normalized, _ = _unwrap_complete_json_fence(content)
    try:
        obj = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise GenericApiError(
            "MCQ_API_RESPONSE_JSON_INVALID", str(error), retryable=True
        ) from error
    if not isinstance(obj, dict):
        raise GenericApiError(
            "MCQ_API_RESPONSE_ROOT_NOT_OBJECT", "not an object", retryable=True
        )
    # The schema_version is a pipeline constant, not something the model should
    # have to reproduce; inject it before validation so a model that omits it
    # still passes (both stem-response and review-response schemas fix it to
    # "1.0.0").
    obj.setdefault("schema_version", "1.0.0")
    try:
        validate_strict(validator, obj)
    except SchemaValidationError as error:
        raise
    usage = _sanitized_usage(raw.get("usage"))
    return obj, usage


class FakeStructuredClient:
    """Offline deterministic client: builds a valid stem from the payload and
    returns an all-pass review. For tests and dry runs only."""

    def __init__(self, model_name: str = "fake-mcq-model"):
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def complete(self, *, task_type, system_prompt, user_payload, validator):
        if task_type == "generate":
            features = list(user_payload.get("condition_features", []))
            joined = _join_features(features)
            obj = {
                "schema_version": "1.0.0",
                "stem": (
                    f"A patient presents with {joined}. "
                    f"Which investigation is most likely to be selected?"
                ),
                "rationale": (
                    "In the source data, this presentation is most strongly "
                    "associated with selection of the keyed investigation."
                ),
            }
        elif task_type == "review":
            obj = {
                "schema_version": "1.0.0",
                "question_id": user_payload.get("question_id", ""),
                "is_investigation_selection": True,
                "uses_rwd_prediction_semantics": True,
                "single_best_answer": True,
                "clinically_plausible": True,
                "safe_priority": True,
                "no_answer_leakage": True,
                "options_same_granularity": True,
                "statistically_supported": True,
                "synthetic_case": True,
                "english_quality": True,
                "recommendation": "accept",
                "concise_reason": "Valid single-answer investigation-selection question.",
            }
        else:
            raise ValueError(f"unknown task_type: {task_type}")
        validate_strict(validator, obj)
        return obj, {"model": self._model_name, "attempts": 1, "usage": {}, "cache_hit": False}


def _join_features(features: list[str]) -> str:
    if not features:
        return "an unspecified presentation"
    if len(features) == 1:
        return features[0]
    return ", ".join(features[:-1]) + " and " + features[-1]
