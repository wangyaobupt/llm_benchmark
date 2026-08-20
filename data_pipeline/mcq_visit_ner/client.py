"""OpenAI-compatible chat client and fail-closed external-transfer gates."""

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

ENVIRONMENT_KEYS = (
    "MCQ_VISIT_NER_API_KEY",
    "MCQ_VISIT_NER_BASE_URL",
    "MCQ_VISIT_NER_MODEL",
    "MCQ_VISIT_NER_MODEL_VERSION",
    "MCQ_VISIT_NER_PROVIDER",
    "MCQ_VISIT_NER_EXTERNAL_API_APPROVED",
)

DEFAULT_BASE_URL = "https://www.dmxapi.cn/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_MODEL_VERSION = "DeepSeek-V4-Flash"
DEFAULT_PROVIDER = "openai-compatible"
APPROVAL_VALUE = "YES"

Transport = Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]]


class NerError(ValueError):
    def __init__(self, reason_code: str, message: str, *, retryable: bool = False):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code
        self.retryable = retryable


def load_env_file(path: Path) -> dict[str, str]:
    """Read MCQ_VISIT_NER_* keys; ignore other subsystems' keys."""
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError as error:
        raise NerError("ENV_FILE_NOT_FOUND", str(path)) from error
    values: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise NerError("ENV_FILE_LINE_INVALID", f"{path}:{line_number}")
        key, raw = stripped.split("=", 1)
        key = key.strip()
        if key not in ENVIRONMENT_KEYS:
            continue
        if key in values:
            raise NerError("ENV_FILE_KEY_DUPLICATE", f"{path}:{line_number}: {key}")
        value = raw.strip()
        if value[:1] in {"'", '"'} and len(value) >= 2 and value[-1] == value[0]:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class ApiSettings:
    api_key: str
    base_url: str
    model: str
    model_version: str
    provider: str

    def __repr__(self) -> str:
        return (
            "ApiSettings(api_key='<redacted>', "
            f"base_url={self.base_url!r}, model={self.model!r}, "
            f"model_version={self.model_version!r}, provider={self.provider!r})"
        )

    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def is_loopback(self) -> bool:
        hostname = (urlparse(self.base_url).hostname or "").lower()
        return hostname in {"localhost", "127.0.0.1", "::1"}

    @classmethod
    def resolve(
        cls,
        env_file: Path | None,
        environ: Mapping[str, str] | None = None,
    ) -> "ApiSettings":
        file_values = load_env_file(env_file) if env_file is not None else {}
        process = os.environ if environ is None else environ
        merged = {key: str(process.get(key, "")).strip() for key in ENVIRONMENT_KEYS}
        for key in ENVIRONMENT_KEYS:
            if not merged[key]:
                merged[key] = file_values.get(key, "")
        if not merged["MCQ_VISIT_NER_BASE_URL"]:
            merged["MCQ_VISIT_NER_BASE_URL"] = DEFAULT_BASE_URL
        if not merged["MCQ_VISIT_NER_MODEL"]:
            merged["MCQ_VISIT_NER_MODEL"] = DEFAULT_MODEL
        if not merged["MCQ_VISIT_NER_MODEL_VERSION"]:
            merged["MCQ_VISIT_NER_MODEL_VERSION"] = DEFAULT_MODEL_VERSION
        if not merged["MCQ_VISIT_NER_PROVIDER"]:
            merged["MCQ_VISIT_NER_PROVIDER"] = DEFAULT_PROVIDER
        if not merged["MCQ_VISIT_NER_API_KEY"]:
            raise NerError("API_ENV_MISSING", "MCQ_VISIT_NER_API_KEY")
        base_url = merged["MCQ_VISIT_NER_BASE_URL"].rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise NerError("API_BASE_URL_INVALID", base_url)
        return cls(
            api_key=merged["MCQ_VISIT_NER_API_KEY"],
            base_url=base_url,
            model=merged["MCQ_VISIT_NER_MODEL"],
            model_version=merged["MCQ_VISIT_NER_MODEL_VERSION"],
            provider=merged["MCQ_VISIT_NER_PROVIDER"],
        )


def approval_value(environ: Mapping[str, str] | None = None) -> str:
    process = os.environ if environ is None else environ
    return str(process.get("MCQ_VISIT_NER_EXTERNAL_API_APPROVED", "")).strip()


def enforce_execution_gates(
    *,
    execute: bool,
    data_transfer_authorized: bool,
    settings: ApiSettings,
    environ: Mapping[str, str] | None = None,
) -> None:
    if not execute:
        raise NerError(
            "MODEL_EXECUTION_NOT_AUTHORIZED",
            "pass --execute to perform model calls",
        )
    if settings.is_loopback():
        return
    if not data_transfer_authorized:
        raise NerError(
            "EXTERNAL_DATA_TRANSFER_NOT_AUTHORIZED",
            "external clinical-text transfer requires --confirm-data-transfer-authorized",
        )
    if approval_value(environ) != APPROVAL_VALUE:
        raise NerError(
            "EXTERNAL_API_NOT_APPROVED",
            "set MCQ_VISIT_NER_EXTERNAL_API_APPROVED=YES in the local environment "
            "(restricted MIMIC text will leave this machine)",
        )


def _http_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=body, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        retryable = error.code == 429 or 500 <= error.code < 600
        raise NerError(
            "API_HTTP_ERROR", f"status={error.code}", retryable=retryable
        ) from error
    except TimeoutError as error:
        raise NerError("API_TIMEOUT", str(error), retryable=True) from error
    except URLError as error:
        raise NerError("API_TRANSPORT_ERROR", str(error.reason), retryable=True) from error
    except json.JSONDecodeError as error:
        raise NerError("API_RESPONSE_NOT_JSON", str(error)) from error


def _json_fence_strip(content: str) -> str:
    stripped = content.strip()
    lines = stripped.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_json_object(content: str) -> dict[str, Any]:
    value = json.loads(_json_fence_strip(content))
    if not isinstance(value, dict):
        raise NerError("INVALID_JSON", "root is not an object")
    return value


def _sanitized_usage(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
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
    return result


def chat_completions(
    settings: ApiSettings,
    system_prompt: str,
    user_payload: Mapping[str, Any],
    *,
    max_tokens: int,
    timeout_seconds: int = 300,
    transport: Transport | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
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
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    sender = transport or _http_transport
    raw = sender(settings.chat_url(), payload, headers, timeout_seconds)
    if not isinstance(raw, Mapping):
        raise NerError("API_RESPONSE_NOT_OBJECT", type(raw).__name__)
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise NerError("API_CHOICES_MISSING", "empty choices")
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise NerError("API_CHOICE_INVALID", type(choice).__name__)
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length":
        raise NerError("OUTPUT_TRUNCATED", "finish_reason=length", retryable=True)
    message = choice.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str) or not content.strip():
        raise NerError("EMPTY_CONTENT", f"finish_reason={finish_reason}", retryable=True)
    try:
        parsed = parse_json_object(content)
    except (json.JSONDecodeError, NerError) as error:
        raise NerError("INVALID_JSON", str(error), retryable=True) from error
    return parsed, _sanitized_usage(raw.get("usage"))


def call_with_retry(
    settings: ApiSettings,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    max_tokens: int,
    maximum_retries: int,
    interval_seconds: float,
    timeout_seconds: int = 300,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], dict[str, int], int]:
    usage_total: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    attempt = 0
    payload = dict(user_payload)
    while True:
        attempt += 1
        try:
            parsed, usage = chat_completions(
                settings,
                system_prompt,
                payload,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                transport=transport,
            )
            for key in usage_total:
                usage_total[key] += usage.get(key, 0)
            return parsed, usage_total, attempt
        except NerError as error:
            retryable = error.retryable or error.reason_code in {
                "EMPTY_CONTENT",
                "INVALID_JSON",
                "OUTPUT_TRUNCATED",
                "API_TRANSPORT_ERROR",
                "API_TIMEOUT",
            }
            if not retryable or attempt > maximum_retries:
                raise
            if error.reason_code in {"EMPTY_CONTENT", "INVALID_JSON", "OUTPUT_TRUNCATED"}:
                payload = dict(payload)
                payload["_correction"] = {
                    "reason": error.reason_code,
                    "instruction": (
                        "Return the complete JSON object required by the system prompt "
                        "and no other text. Every surface_text must be a verbatim substring."
                    ),
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            sleep(interval_seconds * (2 ** (attempt - 1)))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
