"""Zero-call DeepSeek token and price scenarios for prepared NER requests."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .deepseek_adapter import load_deepseek_policy


TOKEN_ESTIMATE_ID = "deepseek-official-character-ratio/2026-08-13"
TOKEN_ESTIMATE_SOURCE_URL = (
    "https://api-docs.deepseek.com/quick_start/token_usage/"
)
SCENARIOS = {
    "lean": {"mention_output_tokens_per_unit": 128, "relation_output_tokens_per_unit": 64},
    "planning": {"mention_output_tokens_per_unit": 512, "relation_output_tokens_per_unit": 256},
    "stress": {"mention_output_tokens_per_unit": 1536, "relation_output_tokens_per_unit": 768},
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _estimated_english_tokens(character_count: int) -> int:
    # Official guidance is approximately 0.3 token per English character.
    return max(1, math.ceil(character_count * 0.3))


def _cost(tokens: int, rate: float, unit: int) -> float:
    return tokens * rate / unit


def estimate_deepseek_cost(
    method_run_directory: Path,
    policy_path: Path,
    *,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    run_directory = Path(method_run_directory).resolve()
    policy_path = Path(policy_path).resolve()
    policy = load_deepseek_policy(policy_path)
    run_manifest_path = run_directory / "run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    if run_manifest["input"]["partition"] != "calibration":
        raise ValueError("DEEPSEEK_COST_NON_CALIBRATION_INPUT")
    if run_manifest["input"]["evaluation_access_count"] != 0:
        raise ValueError("DEEPSEEK_COST_EVALUATION_ACCESS_DETECTED")
    requests_path = run_directory / "requests" / "mention_requests.jsonl"
    requests = _load_jsonl(requests_path)
    if len(requests) != run_manifest["input"]["text_units"]:
        raise ValueError("DEEPSEEK_COST_REQUEST_COUNT_MISMATCH")
    if any(request.get("partition") != "calibration" for request in requests):
        raise ValueError("DEEPSEEK_COST_NON_CALIBRATION_REQUEST")

    mention_prompt = (
        run_directory / "configuration" / "prompts" / "mentions.md"
    ).read_text(encoding="utf-8")
    relation_prompt = (
        run_directory / "configuration" / "prompts" / "relations.md"
    ).read_text(encoding="utf-8")
    text_characters = sum(len(request["section_text"]) for request in requests)
    source_counts = dict(sorted(Counter(request["source_table"] for request in requests).items()))
    units = len(requests)
    mention_common_tokens = units * _estimated_english_tokens(len(mention_prompt))
    relation_common_tokens = units * _estimated_english_tokens(len(relation_prompt))
    text_tokens_per_stage = sum(
        _estimated_english_tokens(len(request["section_text"])) for request in requests
    )
    scenarios: dict[str, Any] = {}
    for name, assumptions in SCENARIOS.items():
        mention_output = units * assumptions["mention_output_tokens_per_unit"]
        relation_output = units * assumptions["relation_output_tokens_per_unit"]
        # Relation input contains the same section plus validated stage-one output.
        common_input = mention_common_tokens + relation_common_tokens
        variable_input = text_tokens_per_stage * 2 + mention_output
        total_input = common_input + variable_input
        total_output = mention_output + relation_output
        model_costs: dict[str, Any] = {}
        for model, rate in policy["pricing"]["models"].items():
            unit = policy["pricing"]["unit_tokens"]
            all_miss = _cost(total_input, rate["input_cache_miss"], unit) + _cost(
                total_output, rate["output"], unit
            )
            prompt_cache_optimistic = (
                _cost(common_input, rate["input_cache_hit"], unit)
                + _cost(variable_input, rate["input_cache_miss"], unit)
                + _cost(total_output, rate["output"], unit)
            )
            model_costs[model] = {
                "all_input_cache_miss_cny": round(all_miss, 6),
                "repeated_prompt_cache_optimistic_cny": round(
                    prompt_cache_optimistic, 6
                ),
            }
        scenarios[name] = {
            "assumptions": assumptions,
            "estimated_tokens": {
                "input": total_input,
                "output": total_output,
                "total": total_input + total_output,
                "common_prompt_input": common_input,
                "variable_input": variable_input,
            },
            "cost_by_model": model_costs,
        }

    result = {
        "schema_version": "text-ner-deepseek-cost-estimate/1.0.0",
        "status": "zero_call_estimate_only",
        "model_calls": 0,
        "evaluation_access_count": 0,
        "input": {
            "run_id": run_manifest["run_id"],
            "run_manifest_sha256": _sha256_file(run_manifest_path),
            "request_file_sha256": _sha256_file(requests_path),
            "policy_sha256": _sha256_file(policy_path),
            "partition": "calibration",
            "text_units": units,
            "source_counts": source_counts,
            "section_text_characters": text_characters,
        },
        "token_estimation": {
            "method_id": TOKEN_ESTIMATE_ID,
            "source_url": TOKEN_ESTIMATE_SOURCE_URL,
            "english_character_to_token_ratio": 0.3,
            "actual_billing_usage_required_after_execution": True,
        },
        "pricing": policy["pricing"],
        "scenarios": scenarios,
        "compliance": {
            "restricted_mimic_api_transfer": policy["data_policy"][
                "restricted_mimic_api_transfer"
            ],
            "reason_code": policy["data_policy"]["reason_code"],
            "environment_override_allowed": policy["data_policy"][
                "environment_override_allowed"
            ],
            "cost_estimate_authorizes_execution": False,
        },
    }
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    if output_markdown:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Text NER DeepSeek API 成本与合规评估",
            "",
            "结论：**成本可估算，但当前禁止把受限MIMIC文本发送到DeepSeek API。**",
            "",
            "## 输入与执行状态",
            "",
            f"- calibration文本单元：{units}",
            f"- section原文字符数：{text_characters}",
            f"- 来源分布：`{json.dumps(source_counts, ensure_ascii=False, sort_keys=True)}`",
            "- evaluation访问：0",
            "- 模型调用：0",
            "",
            "## 费用情景（人民币）",
            "",
            "| 情景 | 模型 | 全部输入未命中缓存 | 重复提示词理想命中 | 估算总tokens |",
            "|---|---|---:|---:|---:|",
        ]
        for scenario_name, scenario in scenarios.items():
            for model, costs in scenario["cost_by_model"].items():
                lines.append(
                    f"| `{scenario_name}` | `{model}` | "
                    f"{costs['all_input_cache_miss_cny']:.6f} | "
                    f"{costs['repeated_prompt_cache_optimistic_cny']:.6f} | "
                    f"{scenario['estimated_tokens']['total']} |"
                )
        lines.extend(
            [
                "",
                "费用是规划情景，不是账单：英文字符按DeepSeek官方约0.3 token估算；输出token是假设值，真实调用后必须用API `usage`重算。缓存理想值也不保证实际命中。",
                "",
                "## 合规判断",
                "",
                "PhysioNet要求第三方API具备零数据保留、不训练、无人审；若无法完整验证则不得使用。DeepSeek现行隐私政策说明会收集输入，并可能为服务、研发、安全等目的保留，未提供本项目可核验的零保留承诺。因此：",
                "",
                "- `restricted_mimic`在代码中硬阻断；",
                "- API key、base URL或其他环境变量均不能解除阻断；",
                "- 适配器只能对合成文本或公开非临床文本进行模拟/接口测试；",
                "- 若未来获得满足PhysioNet要求的DeepSeek企业零保留协议，必须重新审查并升级政策版本，不能直接改环境变量。",
                "",
                "## 官方依据",
                "",
                f"- [PhysioNet：LLM与在线服务使用要求]({policy['data_policy']['physionet_source_url']})",
                f"- [DeepSeek隐私政策]({policy['data_policy']['provider_privacy_source_url']})",
                f"- [DeepSeek模型与价格]({policy['pricing']['source_url']})",
                f"- [DeepSeek token估算说明]({TOKEN_ESTIMATE_SOURCE_URL})",
            ]
        )
        output_markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
