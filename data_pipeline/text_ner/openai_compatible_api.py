"""Provider-neutral, resumable OpenAI-compatible chat-completions adapter."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .annotation_validation import SectionAnnotationValidator
from .model_interface import (
    MODEL_RESPONSE_SCHEMA_VERSION,
    ModelInterfaceError,
    validate_model_request,
    validate_response_envelope,
)


ENVIRONMENT_FILE_KEYS = frozenset(
    {
        "TEXT_NER_API_KEY",
        "TEXT_NER_BASE_URL",
        "TEXT_NER_MODEL",
        "TEXT_NER_MODEL_VERSION",
        "TEXT_NER_PROVIDER",
    }
)


class GenericApiError(ValueError):
    def __init__(self, reason_code: str, message: str, *, retryable: bool = False):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.retryable = retryable


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    api_key: str
    base_url: str
    model: str
    model_version: str
    provider: str

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleSettings(api_key='<redacted>', "
            f"base_url={self.base_url!r}, model={self.model!r}, "
            f"model_version={self.model_version!r}, provider={self.provider!r})"
        )

    @classmethod
    def from_environment(
        cls,
        config: Mapping[str, Any],
        environ: Mapping[str, str] | None = None,
    ) -> "OpenAICompatibleSettings":
        values = os.environ if environ is None else environ
        names = config["environment"]
        resolved = {
            key: values.get(environment_name, "").strip()
            for key, environment_name in names.items()
        }
        if not resolved["provider"]:
            resolved["provider"] = "openai-compatible"
        missing = [
            names[key]
            for key in ("api_key", "base_url", "model", "model_version")
            if not resolved[key]
        ]
        if missing:
            raise GenericApiError("GENERIC_API_ENVIRONMENT_MISSING", ",".join(missing))
        base_url = resolved["base_url"].rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise GenericApiError("GENERIC_API_BASE_URL_INVALID", base_url)
        return cls(
            api_key=resolved["api_key"],
            base_url=base_url,
            model=resolved["model"],
            model_version=resolved["model_version"],
            provider=resolved["provider"],
        )


Transport = Callable[
    [OpenAICompatibleSettings, str, dict[str, Any], int], dict[str, Any]
]


def _http_transport(
    settings: OpenAICompatibleSettings,
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        retryable = error.code == 429 or 500 <= error.code < 600
        raise GenericApiError(
            "GENERIC_API_HTTP_ERROR", f"status={error.code}", retryable=retryable
        ) from error
    except URLError as error:
        raise GenericApiError(
            "GENERIC_API_TRANSPORT_ERROR", str(error.reason), retryable=True
        ) from error
    except json.JSONDecodeError as error:
        raise GenericApiError("GENERIC_API_RESPONSE_NOT_JSON", str(error)) from error


def load_api_config(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != "text-ner-openai-compatible-api/1.0.0":
        raise GenericApiError(
            "GENERIC_API_CONFIG_VERSION_INVALID", str(value.get("schema_version"))
        )
    required = {"environment", "request", "batch", "execution"}
    if required - set(value):
        raise GenericApiError(
            "GENERIC_API_CONFIG_FIELD_MISSING", ",".join(sorted(required - set(value)))
        )
    return value


def load_environment_file(path: Path) -> dict[str, str]:
    """Parse a non-executable UTF-8 KEY=VALUE file containing only NER settings."""

    environment_path = Path(path)
    try:
        lines = environment_path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError as error:
        raise GenericApiError(
            "GENERIC_API_ENV_FILE_NOT_FOUND", str(environment_path)
        ) from error
    except UnicodeDecodeError as error:
        raise GenericApiError(
            "GENERIC_API_ENV_FILE_ENCODING_INVALID", str(environment_path)
        ) from error

    values: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise GenericApiError(
                "GENERIC_API_ENV_FILE_LINE_INVALID",
                f"{environment_path}:{line_number}: expected KEY=VALUE",
            )
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if key not in ENVIRONMENT_FILE_KEYS:
            raise GenericApiError(
                "GENERIC_API_ENV_FILE_KEY_UNKNOWN",
                f"{environment_path}:{line_number}: {key or '<empty>'}",
            )
        if key in values:
            raise GenericApiError(
                "GENERIC_API_ENV_FILE_KEY_DUPLICATE",
                f"{environment_path}:{line_number}: {key}",
            )
        value = raw_value.strip()
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise GenericApiError(
                    "GENERIC_API_ENV_FILE_QUOTE_INVALID",
                    f"{environment_path}:{line_number}: {key}",
                )
            value = value[1:-1]
        values[key] = value
    return values


def resolve_environment(
    environment_file: Path | None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load file settings, then apply process-environment overrides."""

    resolved = (
        load_environment_file(environment_file) if environment_file is not None else {}
    )
    process_environment = os.environ if environ is None else environ
    for key in ENVIRONMENT_FILE_KEYS:
        if key in process_environment:
            resolved[key] = process_environment[key]
    return resolved


def enforce_execution_gate(
    *, execute: bool, endpoint_scope: str, data_transfer_authorized: bool
) -> None:
    if not execute:
        raise GenericApiError(
            "MODEL_EXECUTION_NOT_AUTHORIZED", "pass --execute to perform model calls"
        )
    if endpoint_scope not in {"local", "external"}:
        raise GenericApiError("GENERIC_API_ENDPOINT_SCOPE_INVALID", endpoint_scope)
    if endpoint_scope == "external" and not data_transfer_authorized:
        raise GenericApiError(
            "EXTERNAL_DATA_TRANSFER_NOT_AUTHORIZED",
            "external clinical-text transfer requires explicit authorization",
        )


def enforce_endpoint_scope(
    settings: OpenAICompatibleSettings, endpoint_scope: str
) -> None:
    hostname = (urlparse(settings.base_url).hostname or "").lower()
    if endpoint_scope == "local" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise GenericApiError(
            "GENERIC_API_LOCAL_SCOPE_REQUIRES_LOOPBACK", settings.base_url
        )


class OpenAICompatibleAdapter:
    """One model binding; batch orchestration and validation remain outside it."""

    def __init__(
        self,
        settings: OpenAICompatibleSettings,
        config: Mapping[str, Any],
        prompt: str,
        *,
        transport: Transport | None = None,
    ):
        self._settings = settings
        self._config = config
        self._prompt = prompt
        self._transport = transport or _http_transport

    @property
    def provider(self) -> str:
        return self._settings.provider

    @property
    def model_name(self) -> str:
        return self._settings.model

    @property
    def model_version(self) -> str:
        return self._settings.model_version

    def generate(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        validated = validate_model_request(request)
        request_config = self._config["request"]
        user_payload = {
            "stage_id": validated["stage_id"],
            "manifest_row_id": validated["manifest_row_id"],
            "document_id": validated["document_id"],
            "section_id": validated["section_id"],
            "section_text_sha256": validated["section_text_sha256"],
            "section_text": validated["section_text"],
        }
        if validated["stage_id"] == "relations":
            user_payload["validated_mentions"] = validated["validated_mentions"]
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": self._prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ],
            "temperature": request_config["temperature"],
            "max_tokens": request_config["max_tokens"],
            "stream": False,
        }
        if request_config.get("response_format_json_object"):
            payload["response_format"] = {"type": "json_object"}
        endpoint = (
            self._settings.base_url
            + "/"
            + request_config["chat_completions_path"].lstrip("/")
        )
        raw = self._transport(
            self._settings,
            endpoint,
            payload,
            int(request_config["timeout_seconds"]),
        )
        try:
            content = raw["choices"][0]["message"]["content"]
            annotation = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise GenericApiError("GENERIC_API_ANNOTATION_JSON_INVALID", str(error)) from error
        response = {
            "schema_version": MODEL_RESPONSE_SCHEMA_VERSION,
            "request_id": validated["request_id"],
            "stage_id": validated["stage_id"],
            "provider": self.provider,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "annotation": annotation,
        }
        validate_response_envelope(response, validated)
        return {
            "response": response,
            "usage": raw.get("usage") or {},
            "response_id": raw.get("id"),
        }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise GenericApiError(
                    "GENERIC_API_CHECKPOINT_INVALID", f"{path}:{line_number}: {error}"
                ) from error
            if not isinstance(value, dict):
                raise GenericApiError(
                    "GENERIC_API_CHECKPOINT_INVALID", f"{path}:{line_number}: not object"
                )
            rows.append(value)
    return rows


def _validate_annotation_for_request(
    response: dict[str, Any], request: dict[str, Any]
) -> None:
    annotation = response["annotation"]
    SectionAnnotationValidator().validate(
        annotation,
        {
            "manifest_row_id": request["manifest_row_id"],
            "document_id": request["document_id"],
            "section_id": request["section_id"],
            "span_sha256": request["section_text_sha256"],
        },
        request["section_text"],
    )
    if request["stage_id"] == "mentions" and annotation["relations"]:
        raise ModelInterfaceError(
            "MENTION_RESPONSE_CONTAINS_RELATIONS", request["request_id"]
        )
    if request["stage_id"] == "relations" and annotation["mentions"] != request[
        "validated_mentions"
    ]:
        raise ModelInterfaceError(
            "RELATION_RESPONSE_MENTIONS_CHANGED", request["request_id"]
        )


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def run_api_batch(
    requests_path: Path,
    prompt_path: Path,
    output_responses_path: Path,
    audit_path: Path,
    config_path: Path,
    *,
    execute: bool = False,
    endpoint_scope: str = "external",
    data_transfer_authorized: bool = False,
    maximum_requests: int | None = None,
    environment_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run or resume one stage; no call occurs before both execution gates pass."""

    enforce_execution_gate(
        execute=execute,
        endpoint_scope=endpoint_scope,
        data_transfer_authorized=data_transfer_authorized,
    )
    config = load_api_config(config_path)
    settings = OpenAICompatibleSettings.from_environment(
        config, resolve_environment(environment_file, environ)
    )
    enforce_endpoint_scope(settings, endpoint_scope)
    prompt = Path(prompt_path).read_text(encoding="utf-8")
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    requests = _load_jsonl(Path(requests_path))
    existing = _load_jsonl(Path(output_responses_path))
    completed: set[str] = set()
    request_by_id = {row["request_id"]: validate_model_request(row) for row in requests}
    if len(request_by_id) != len(requests):
        raise GenericApiError("GENERIC_API_REQUEST_ID_DUPLICATE", str(requests_path))
    for response in existing:
        request = request_by_id.get(str(response.get("request_id")))
        if request is None:
            raise GenericApiError(
                "GENERIC_API_CHECKPOINT_REQUEST_UNKNOWN", str(response.get("request_id"))
            )
        validate_response_envelope(response, request)
        _validate_annotation_for_request(response, request)
        if response["request_id"] in completed:
            raise GenericApiError(
                "GENERIC_API_CHECKPOINT_DUPLICATE", response["request_id"]
            )
        completed.add(response["request_id"])

    adapter = OpenAICompatibleAdapter(
        settings, config, prompt, transport=transport
    )
    limit = len(requests) if maximum_requests is None else maximum_requests
    if limit < 0:
        raise GenericApiError("GENERIC_API_MAXIMUM_REQUESTS_INVALID", str(limit))
    calls = 0
    retries = 0
    token_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    interval = 60.0 / max(1, int(config["batch"]["requests_per_minute"]))
    for request in requests:
        if request["request_id"] in completed:
            continue
        if calls >= limit:
            break
        if request["prompt_sha256"] != prompt_sha256:
            raise GenericApiError(
                "GENERIC_API_PROMPT_HASH_MISMATCH", request["request_id"]
            )
        maximum_retries = int(config["batch"]["maximum_retries"])
        attempt = 0
        while True:
            try:
                result = adapter.generate(request)
                break
            except GenericApiError as error:
                if not error.retryable or attempt >= maximum_retries:
                    raise
                delay = float(config["batch"]["retry_initial_seconds"]) * (2**attempt)
                retries += 1
                attempt += 1
                sleep(delay)
        response = dict(result["response"])
        _validate_annotation_for_request(response, request)
        _append_jsonl(Path(output_responses_path), response)
        usage = result["usage"]
        for key in token_usage:
            value = usage.get(key)
            if isinstance(value, int):
                token_usage[key] += value
        audit = {
            "schema_version": "text-ner-api-call-audit/1.0.0",
            "request_id": request["request_id"],
            "stage_id": request["stage_id"],
            "provider": settings.provider,
            "model_name": settings.model,
            "model_version": settings.model_version,
            "endpoint_scope": endpoint_scope,
            "request_sha256": hashlib.sha256(
                json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "response_id": result["response_id"],
            "usage": usage,
            "credential_source": config["environment"]["api_key"],
            "credential_persisted": False,
        }
        _append_jsonl(Path(audit_path), audit)
        completed.add(request["request_id"])
        calls += 1
        if calls < limit:
            sleep(interval)
    return {
        "schema_version": "text-ner-api-batch-summary/1.0.0",
        "requests": len(requests),
        "already_completed": len(existing),
        "model_calls_this_run": calls,
        "completed_total": len(completed),
        "remaining": len(requests) - len(completed),
        "retries": retries,
        "usage_this_run": token_usage,
        "provider": settings.provider,
        "model_name": settings.model,
        "model_version": settings.model_version,
        "endpoint_scope": endpoint_scope,
    }
