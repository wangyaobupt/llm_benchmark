"""Provider-neutral, resumable OpenAI-compatible chat-completions adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .annotation_validation import AnnotationValidationError, SectionAnnotationValidator
from .model_interface import (
    MODEL_RESPONSE_SCHEMA_VERSION,
    ModelInterfaceError,
    validate_model_request,
    validate_response_envelope,
)
from .span_grounding import ground_annotation_spans


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
    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        retryable: bool = False,
        diagnostics: Mapping[str, Any] | None = None,
    ):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.retryable = retryable
        self.diagnostics = dict(diagnostics or {})


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


def _sanitized_usage(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ):
        item = value.get(key)
        if isinstance(item, int) and item >= 0:
            result[key] = item
    details = value.get("completion_tokens_details")
    if isinstance(details, Mapping):
        reasoning_tokens = details.get("reasoning_tokens")
        if isinstance(reasoning_tokens, int) and reasoning_tokens >= 0:
            result["completion_tokens_details"] = {
                "reasoning_tokens": reasoning_tokens
            }
    return result


def _short_api_string(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:200]


def _response_diagnostics(
    raw: Mapping[str, Any],
    *,
    choice: Mapping[str, Any] | None = None,
    content: object = None,
) -> dict[str, Any]:
    message = choice.get("message") if isinstance(choice, Mapping) else None
    reasoning_content = (
        message.get("reasoning_content") if isinstance(message, Mapping) else None
    )
    diagnostics: dict[str, Any] = {
        "response_id": _short_api_string(raw.get("id")),
        "finish_reason": _short_api_string(choice.get("finish_reason"))
        if isinstance(choice, Mapping)
        else None,
        "usage": _sanitized_usage(raw.get("usage")),
        "content_length": len(content) if isinstance(content, str) else 0,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()
        if isinstance(content, str)
        else None,
        "reasoning_content_length": len(reasoning_content)
        if isinstance(reasoning_content, str)
        else 0,
    }
    return diagnostics


def _unwrap_complete_json_fence(content: str) -> tuple[str, str]:
    stripped = content.strip()
    lines = stripped.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1]).strip(), "markdown_json_fence_removed"
    return stripped, "none"


def _parse_annotation_response(
    raw: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        choice = raw["choices"][0]
        if not isinstance(choice, Mapping):
            raise TypeError("choice is not an object")
        message = choice["message"]
        if not isinstance(message, Mapping):
            raise TypeError("message is not an object")
        content = message.get("content")
    except (KeyError, IndexError, TypeError) as error:
        diagnostics = _response_diagnostics(raw)
        raise GenericApiError(
            "GENERIC_API_RESPONSE_SHAPE_INVALID",
            "choices[0].message.content is unavailable",
            retryable=True,
            diagnostics=diagnostics,
        ) from error

    diagnostics = _response_diagnostics(raw, choice=choice, content=content)
    finish_reason = diagnostics["finish_reason"]
    if finish_reason == "length":
        diagnostics["content_state"] = "truncated"
        raise GenericApiError(
            "GENERIC_API_OUTPUT_TRUNCATED",
            (
                "finish_reason=length; increase request.max_tokens or reduce the "
                "input section size"
            ),
            diagnostics=diagnostics,
        )
    if finish_reason == "content_filter":
        diagnostics["content_state"] = "filtered"
        raise GenericApiError(
            "GENERIC_API_OUTPUT_CONTENT_FILTERED",
            "finish_reason=content_filter",
            diagnostics=diagnostics,
        )
    if finish_reason == "tool_calls":
        diagnostics["content_state"] = "tool_calls"
        raise GenericApiError(
            "GENERIC_API_OUTPUT_TOOL_CALL_UNEXPECTED",
            "finish_reason=tool_calls is not valid for NER annotation",
            diagnostics=diagnostics,
        )
    if finish_reason == "insufficient_system_resource":
        diagnostics["content_state"] = "incomplete_system_resource"
        raise GenericApiError(
            "GENERIC_API_OUTPUT_RESOURCE_INTERRUPTED",
            "finish_reason=insufficient_system_resource",
            retryable=True,
            diagnostics=diagnostics,
        )
    if not isinstance(content, str) or not content.strip():
        diagnostics["content_state"] = "empty"
        raise GenericApiError(
            "GENERIC_API_ANNOTATION_CONTENT_EMPTY",
            (
                f"finish_reason={finish_reason or 'missing'}; "
                f"content_length={diagnostics['content_length']}"
            ),
            retryable=True,
            diagnostics=diagnostics,
        )

    normalized, normalization = _unwrap_complete_json_fence(content)
    diagnostics["content_state"] = "nonempty"
    diagnostics["content_normalization"] = normalization
    try:
        annotation = json.loads(normalized)
    except json.JSONDecodeError as error:
        diagnostics["json_error_line"] = error.lineno
        diagnostics["json_error_column"] = error.colno
        diagnostics["json_error_position"] = error.pos
        raise GenericApiError(
            "GENERIC_API_ANNOTATION_JSON_INVALID",
            (
                f"finish_reason={finish_reason or 'missing'}; "
                f"content_length={diagnostics['content_length']}; "
                f"json_line={error.lineno}; json_column={error.colno}"
            ),
            retryable=True,
            diagnostics=diagnostics,
        ) from error
    if not isinstance(annotation, dict):
        raise GenericApiError(
            "GENERIC_API_ANNOTATION_ROOT_NOT_OBJECT",
            f"finish_reason={finish_reason or 'missing'}",
            retryable=True,
            diagnostics=diagnostics,
        )
    return annotation, {
        "response_id": diagnostics["response_id"],
        "finish_reason": finish_reason,
        "usage": diagnostics["usage"],
        "content_normalization": normalization,
        "diagnostics": diagnostics,
    }


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


def _provider_request_options(
    config: Mapping[str, Any], provider: str
) -> dict[str, Any]:
    all_options = config.get("provider_request_options", {})
    if not isinstance(all_options, Mapping):
        raise GenericApiError(
            "GENERIC_API_PROVIDER_OPTIONS_INVALID", "provider_request_options"
        )
    selected = all_options.get(provider)
    if selected is None:
        selected = all_options.get(provider.lower(), {})
    if not isinstance(selected, Mapping):
        raise GenericApiError(
            "GENERIC_API_PROVIDER_OPTIONS_INVALID", provider
        )
    unknown = set(selected) - {"thinking"}
    if unknown:
        raise GenericApiError(
            "GENERIC_API_PROVIDER_OPTION_UNKNOWN", ",".join(sorted(unknown))
        )
    result: dict[str, Any] = {}
    if "thinking" in selected:
        thinking = selected["thinking"]
        if (
            not isinstance(thinking, Mapping)
            or set(thinking) != {"type"}
            or thinking.get("type") not in {"enabled", "disabled"}
        ):
            raise GenericApiError(
                "GENERIC_API_PROVIDER_OPTIONS_INVALID", f"{provider}.thinking"
            )
        result["thinking"] = {"type": thinking["type"]}
    return result


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
        self._request_options = _provider_request_options(config, settings.provider)

    @property
    def provider(self) -> str:
        return self._settings.provider

    @property
    def model_name(self) -> str:
        return self._settings.model

    @property
    def model_version(self) -> str:
        return self._settings.model_version

    @property
    def request_options(self) -> dict[str, Any]:
        return dict(self._request_options)

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
        payload.update(self._request_options)
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
        annotation, response_metadata = _parse_annotation_response(raw)
        response = {
            "schema_version": MODEL_RESPONSE_SCHEMA_VERSION,
            "request_id": validated["request_id"],
            "stage_id": validated["stage_id"],
            "provider": self.provider,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "annotation": annotation,
        }
        try:
            validate_response_envelope(response, validated)
        except ModelInterfaceError as error:
            raise GenericApiError(
                "GENERIC_API_ANNOTATION_CONTRACT_INVALID",
                error.reason_code,
                retryable=True,
                diagnostics=response_metadata["diagnostics"],
            ) from error
        return {
            "response": response,
            "usage": response_metadata["usage"],
            "response_id": response_metadata["response_id"],
            "finish_reason": response_metadata["finish_reason"],
            "content_normalization": response_metadata["content_normalization"],
            "request_options": dict(self._request_options),
            "diagnostics": response_metadata["diagnostics"],
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


def _request_sha256(request: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _default_failure_audit_path(audit_path: Path) -> Path:
    suffix = audit_path.suffix or ".jsonl"
    return audit_path.with_name(f"{audit_path.stem}.failures{suffix}")


def _accumulate_usage(target: dict[str, int], value: object) -> None:
    usage = _sanitized_usage(value)
    for key in target:
        item = usage.get(key)
        if isinstance(item, int):
            target[key] += item


def _safe_failure_diagnostics(error: GenericApiError) -> dict[str, Any]:
    allowed = {
        "response_id",
        "finish_reason",
        "content_length",
        "content_sha256",
        "reasoning_content_length",
        "content_state",
        "content_normalization",
        "json_error_line",
        "json_error_column",
        "json_error_position",
        "annotation_validation_reason_code",
        "annotation_validation_local_id",
    }
    result = {
        key: error.diagnostics[key]
        for key in allowed
        if key in error.diagnostics
    }
    result["usage"] = _sanitized_usage(error.diagnostics.get("usage"))
    return result


def _append_failure_audit(
    path: Path,
    *,
    request: Mapping[str, Any],
    settings: OpenAICompatibleSettings,
    endpoint_scope: str,
    request_options: Mapping[str, Any],
    error: GenericApiError,
    attempt_number: int,
    maximum_attempts: int,
    will_retry: bool,
    retry_delay_seconds: float | None,
    retry_stop_reason: str | None,
) -> None:
    diagnostics = _safe_failure_diagnostics(error)
    thinking = request_options.get("thinking")
    thinking_mode = thinking.get("type") if isinstance(thinking, Mapping) else None
    _append_jsonl(
        path,
        {
            "schema_version": "text-ner-api-call-failure-audit/1.0.0",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "request_id": request["request_id"],
            "stage_id": request["stage_id"],
            "provider": settings.provider,
            "model_name": settings.model,
            "model_version": settings.model_version,
            "endpoint_scope": endpoint_scope,
            "request_sha256": _request_sha256(request),
            "attempt_number": attempt_number,
            "maximum_attempts": maximum_attempts,
            "reason_code": error.reason_code,
            "retryable": error.retryable,
            "will_retry": will_retry,
            "retry_delay_seconds": retry_delay_seconds,
            "retry_stop_reason": retry_stop_reason,
            "response_id": diagnostics.get("response_id"),
            "finish_reason": diagnostics.get("finish_reason"),
            "content_state": diagnostics.get("content_state"),
            "content_length": diagnostics.get("content_length", 0),
            "content_sha256": diagnostics.get("content_sha256"),
            "content_normalization": diagnostics.get("content_normalization"),
            "reasoning_content_length": diagnostics.get(
                "reasoning_content_length", 0
            ),
            "json_error_line": diagnostics.get("json_error_line"),
            "json_error_column": diagnostics.get("json_error_column"),
            "json_error_position": diagnostics.get("json_error_position"),
            "annotation_validation_reason_code": diagnostics.get(
                "annotation_validation_reason_code"
            ),
            "annotation_validation_local_id": diagnostics.get(
                "annotation_validation_local_id"
            ),
            "usage": diagnostics["usage"],
            "thinking_mode": thinking_mode,
            "credential_persisted": False,
            "raw_model_content_persisted": False,
        },
    )


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
    failure_audit_path: Path | None = None,
    retry_failures_from: Path | None = None,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    progress_reporter: Callable[[str], None] | None = None,
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

    selection_mode = "all_pending"
    eligible_request_ids = set(request_by_id) - completed
    if retry_failures_from is not None:
        selection_mode = "terminal_failures_only"
        failure_rows = _load_jsonl(Path(retry_failures_from))
        terminal_failure_ids = {
            str(row.get("request_id"))
            for row in failure_rows
            if row.get("will_retry") is False and row.get("request_id")
        }
        unknown_failure_ids = terminal_failure_ids - set(request_by_id)
        if unknown_failure_ids:
            raise GenericApiError(
                "GENERIC_API_RETRY_FAILURE_REQUEST_UNKNOWN",
                str(len(unknown_failure_ids)),
            )
        eligible_request_ids &= terminal_failure_ids

    adapter = OpenAICompatibleAdapter(settings, config, prompt, transport=transport)
    resolved_failure_audit_path = (
        Path(failure_audit_path)
        if failure_audit_path is not None
        else _default_failure_audit_path(Path(audit_path))
    )
    requested_limit = (
        len(eligible_request_ids) if maximum_requests is None else maximum_requests
    )
    if requested_limit < 0:
        raise GenericApiError(
            "GENERIC_API_MAXIMUM_REQUESTS_INVALID", str(requested_limit)
        )
    limit = min(requested_limit, len(eligible_request_ids))
    successful_responses = 0
    attempted_requests = 0
    failed_requests = 0
    api_attempts = 0
    retries = 0
    token_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    successful_token_usage = dict(token_usage)
    interval = 60.0 / max(1, int(config["batch"]["requests_per_minute"]))
    if progress_reporter is not None:
        progress_reporter(
            f"[API] 已载入 {len(requests):,} 个文本单元 | "
            f"checkpoint {len(completed):,} | 候选 {len(eligible_request_ids):,} | "
            f"本次最多尝试 {limit:,} 个 | 模式 {selection_mode}"
        )
    for request in requests:
        if request["request_id"] not in eligible_request_ids:
            continue
        if attempted_requests >= limit:
            break
        attempted_requests += 1
        if request["prompt_sha256"] != prompt_sha256:
            raise GenericApiError(
                "GENERIC_API_PROMPT_HASH_MISMATCH", request["request_id"]
            )
        maximum_retries = int(config["batch"]["maximum_retries"])
        maximum_attempts = maximum_retries + 1
        attempt_number = 1
        failed_content_hashes: set[str] = set()
        response: dict[str, Any] | None = None
        result: Mapping[str, Any] | None = None
        span_repairs: list[dict[str, Any]] = []
        while True:
            api_attempts += 1
            if progress_reporter is not None:
                progress_reporter(
                    f"[API] 文本单元 {attempted_requests:,}/{limit:,} | "
                    f"调用 {attempt_number}/{maximum_attempts}"
                )
            try:
                result = adapter.generate(request)
                response = dict(result["response"])
                grounded_annotation, span_repairs = ground_annotation_spans(
                    response["annotation"], request["section_text"]
                )
                response["annotation"] = grounded_annotation
                try:
                    _validate_annotation_for_request(response, request)
                except (
                    AnnotationValidationError,
                    ModelInterfaceError,
                ) as validation_error:
                    diagnostics = dict(result["diagnostics"])
                    diagnostics["annotation_validation_reason_code"] = (
                        validation_error.reason_code
                    )
                    validation_detail = str(validation_error).partition(": ")[2]
                    if (
                        len(validation_detail) >= 2
                        and validation_detail[0] in {"m", "r"}
                        and validation_detail[1:].isdigit()
                    ):
                        diagnostics["annotation_validation_local_id"] = (
                            validation_detail
                        )
                    raise GenericApiError(
                        "GENERIC_API_ANNOTATION_CONTRACT_INVALID",
                        validation_error.reason_code,
                        retryable=True,
                        diagnostics=diagnostics,
                    ) from validation_error
                break
            except GenericApiError as error:
                _accumulate_usage(token_usage, error.diagnostics.get("usage"))
                content_sha256 = error.diagnostics.get("content_sha256")
                repeated_invalid_content = (
                    isinstance(content_sha256, str)
                    and content_sha256 in failed_content_hashes
                )
                if isinstance(content_sha256, str):
                    failed_content_hashes.add(content_sha256)
                will_retry = (
                    error.retryable
                    and attempt_number < maximum_attempts
                    and not repeated_invalid_content
                )
                delay = (
                    float(config["batch"]["retry_initial_seconds"])
                    * (2 ** (attempt_number - 1))
                    if will_retry
                    else None
                )
                retry_stop_reason = (
                    "identical_invalid_content"
                    if repeated_invalid_content
                    else (
                        "maximum_attempts_reached"
                        if error.retryable and attempt_number >= maximum_attempts
                        else ("non_retryable_error" if not error.retryable else None)
                    )
                )
                _append_failure_audit(
                    resolved_failure_audit_path,
                    request=request,
                    settings=settings,
                    endpoint_scope=endpoint_scope,
                    request_options=adapter.request_options,
                    error=error,
                    attempt_number=attempt_number,
                    maximum_attempts=maximum_attempts,
                    will_retry=will_retry,
                    retry_delay_seconds=delay,
                    retry_stop_reason=retry_stop_reason,
                )
                if not will_retry:
                    quarantinable = error.reason_code in {
                        "GENERIC_API_ANNOTATION_CONTENT_EMPTY",
                        "GENERIC_API_ANNOTATION_JSON_INVALID",
                        "GENERIC_API_ANNOTATION_CONTRACT_INVALID",
                    }
                    if error.retryable and quarantinable:
                        failed_requests += 1
                        if progress_reporter is not None:
                            progress_reporter(
                                f"[API] 文本单元失败并继续 | {error.reason_code} | "
                                f"停止原因 {retry_stop_reason} | "
                                f"本次失败 {failed_requests:,}"
                            )
                        response = None
                        result = None
                        break
                    raise
                retries += 1
                if progress_reporter is not None:
                    progress_reporter(
                        f"[API] 校验失败，{delay:.1f} 秒后重试 | "
                        f"{error.reason_code}"
                    )
                attempt_number += 1
                sleep(delay)
        if response is None or result is None:
            if attempted_requests < limit:
                sleep(interval)
            continue
        _append_jsonl(Path(output_responses_path), response)
        usage = result["usage"]
        _accumulate_usage(token_usage, usage)
        _accumulate_usage(successful_token_usage, usage)
        thinking = result["request_options"].get("thinking")
        audit = {
            "schema_version": "text-ner-api-call-audit/1.2.0",
            "request_id": request["request_id"],
            "stage_id": request["stage_id"],
            "provider": settings.provider,
            "model_name": settings.model,
            "model_version": settings.model_version,
            "endpoint_scope": endpoint_scope,
            "request_sha256": _request_sha256(request),
            "response_id": result["response_id"],
            "finish_reason": result["finish_reason"],
            "content_normalization": result["content_normalization"],
            "attempt_number": attempt_number,
            "usage": usage,
            "span_grounding": {
                "schema_version": "text-ner-span-grounding/1.1.0",
                "repair_count": len(span_repairs),
                "repairs": span_repairs,
            },
            "thinking_mode": thinking.get("type")
            if isinstance(thinking, Mapping)
            else None,
            "credential_source": config["environment"]["api_key"],
            "credential_persisted": False,
            "raw_model_content_persisted": False,
        }
        _append_jsonl(Path(audit_path), audit)
        completed.add(request["request_id"])
        successful_responses += 1
        if progress_reporter is not None:
            progress_reporter(
                f"[API] 成功 {successful_responses:,} | 失败 {failed_requests:,} | "
                f"完成总数 {len(completed):,}/{len(requests):,} | "
                f"本次 tokens {token_usage['total_tokens']:,}"
            )
        if attempted_requests < limit:
            sleep(interval)
    return {
        "schema_version": "text-ner-api-batch-summary/1.3.0",
        "requests": len(requests),
        "already_completed": len(existing),
        "selection_mode": selection_mode,
        "eligible_requests": len(eligible_request_ids),
        "attempted_requests_this_run": attempted_requests,
        "model_calls_this_run": api_attempts,
        "successful_responses_this_run": successful_responses,
        "failed_requests_this_run": failed_requests,
        "failed_attempts_this_run": api_attempts - successful_responses,
        "completed_total": len(completed),
        "remaining": len(requests) - len(completed),
        "retries": retries,
        "usage_this_run": token_usage,
        "successful_usage_this_run": successful_token_usage,
        "failure_audit_path": str(resolved_failure_audit_path),
        "request_options": adapter.request_options,
        "provider": settings.provider,
        "model_name": settings.model,
        "model_version": settings.model_version,
        "endpoint_scope": endpoint_scope,
    }
