"""DeepSeek JSON API adapter with a non-overridable restricted-MIMIC gate."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator, FormatChecker


POLICY_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "schemas" / "deepseek-api-policy.schema.json"
)


class DeepSeekPolicyError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def load_deepseek_policy(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    policy = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(POLICY_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(policy), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "<root>"
        raise DeepSeekPolicyError(
            "DEEPSEEK_POLICY_INVALID", f"{location}: {error.message}"
        )
    return policy


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    base_url: str
    model: str
    model_revision: str

    def __repr__(self) -> str:
        return (
            "DeepSeekSettings(api_key='<redacted>', "
            f"base_url={self.base_url!r}, model={self.model!r}, "
            f"model_revision={self.model_revision!r})"
        )

    @classmethod
    def from_environment(
        cls, policy: Mapping[str, Any], environ: Mapping[str, str] | None = None
    ) -> "DeepSeekSettings":
        values = os.environ if environ is None else environ
        names = policy["environment"]
        api_key = values.get(names["api_key"], "").strip()
        base_url = values.get(names["base_url"], policy["base_url"]).strip().rstrip("/")
        model = values.get(names["model"], "").strip()
        model_revision = values.get(names["model_revision"], "").strip()
        missing = [
            name
            for name, value in (
                (names["api_key"], api_key),
                (names["model"], model),
                (names["model_revision"], model_revision),
            )
            if not value
        ]
        if missing:
            raise DeepSeekPolicyError(
                "DEEPSEEK_ENVIRONMENT_MISSING", ",".join(missing)
            )
        if base_url != policy["base_url"]:
            raise DeepSeekPolicyError(
                "DEEPSEEK_BASE_URL_NOT_FROZEN", base_url
            )
        if model not in policy["models"]:
            raise DeepSeekPolicyError("DEEPSEEK_MODEL_NOT_ALLOWED", model)
        expected_revision = policy["model_revisions"][model]
        if model_revision != expected_revision:
            raise DeepSeekPolicyError(
                "DEEPSEEK_MODEL_REVISION_MISMATCH",
                f"observed={model_revision}, expected={expected_revision}",
            )
        return cls(api_key, base_url, model, model_revision)


def enforce_data_policy(policy: Mapping[str, Any], data_classification: str) -> None:
    allowed = policy["data_policy"]["allowed_data_classifications"]
    if data_classification in allowed:
        return
    if data_classification == "restricted_mimic":
        raise DeepSeekPolicyError(
            "EXTERNAL_MIMIC_TRANSFER_PROHIBITED",
            policy["data_policy"]["reason_code"],
        )
    raise DeepSeekPolicyError(
        "DEEPSEEK_DATA_CLASSIFICATION_NOT_ALLOWED", data_classification
    )


def build_deepseek_json_request(
    *,
    model: str,
    prompt: str,
    section_text: str,
    policy: Mapping[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    if max_tokens <= 0:
        raise DeepSeekPolicyError("DEEPSEEK_MAX_TOKENS_INVALID", str(max_tokens))
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": "Return JSON for this section_text exactly as instructed:\n"
                + section_text,
            },
        ],
        "response_format": {"type": policy["request"]["response_format"]},
        "thinking": {"type": policy["request"]["thinking"]},
        "temperature": policy["request"]["temperature"],
        "max_tokens": max_tokens,
        "stream": False,
    }


Transport = Callable[[DeepSeekSettings, dict[str, Any]], dict[str, Any]]


def _openai_transport(
    settings: DeepSeekSettings, request: dict[str, Any]
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    payload = dict(request)
    thinking = payload.pop("thinking")
    response = client.chat.completions.create(
        **payload, extra_body={"thinking": thinking}
    )
    return response.model_dump(mode="json")


class DeepSeekJsonAdapter:
    def __init__(
        self,
        policy: Mapping[str, Any],
        *,
        environ: Mapping[str, str] | None = None,
        transport: Transport | None = None,
    ):
        self._policy = policy
        self._environ = environ
        self._transport = transport or _openai_transport

    def execute(
        self, request: dict[str, Any], *, data_classification: str
    ) -> dict[str, Any]:
        # The policy gate precedes credential loading and client construction. No
        # environment variable can authorize restricted-MIMIC transfer.
        enforce_data_policy(self._policy, data_classification)
        settings = DeepSeekSettings.from_environment(self._policy, self._environ)
        if request.get("model") != settings.model:
            raise DeepSeekPolicyError(
                "DEEPSEEK_REQUEST_MODEL_MISMATCH", str(request.get("model"))
            )
        response = self._transport(settings, request)
        try:
            content = response["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise DeepSeekPolicyError(
                "DEEPSEEK_RESPONSE_JSON_INVALID", str(error)
            ) from error
        usage = response.get("usage") or {}
        audit_record = {
            "provider": "deepseek",
            "base_url": settings.base_url,
            "model": settings.model,
            "model_revision": settings.model_revision,
            "data_classification": data_classification,
            "request_sha256": _sha256_json(request),
            "response_sha256": _sha256_json(response),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
                "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            "credential_source": self._policy["environment"]["api_key"],
            "credential_persisted": False,
        }
        return {
            "parsed_json": parsed,
            "raw_response": response,
            "audit_record": audit_record,
        }


def persist_deepseek_call_result(
    output_directory: Path, result: Mapping[str, Any]
) -> dict[str, Any]:
    """Atomically persist one non-overwriting raw response and audit record."""

    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.", dir=output_directory.parent
        )
    )
    try:
        paths = {
            "raw_response.json": result["raw_response"],
            "parsed_response.json": result["parsed_json"],
            "audit_record.json": result["audit_record"],
        }
        hashes: dict[str, str] = {}
        for filename, value in paths.items():
            payload = _canonical_json(value) + b"\n"
            (temporary / filename).write_bytes(payload)
            hashes[filename] = hashlib.sha256(payload).hexdigest()
        manifest = {
            "schema_version": "text-ner-deepseek-call-artifact/1.0.0",
            "immutable": True,
            "files": hashes,
        }
        manifest_payload = _canonical_json(manifest) + b"\n"
        (temporary / "manifest.json").write_bytes(manifest_payload)
        temporary.replace(output_directory)
        return manifest
    except Exception:
        resolved = temporary.resolve()
        if output_directory.parent.resolve() in resolved.parents:
            shutil.rmtree(resolved, ignore_errors=True)
        raise
