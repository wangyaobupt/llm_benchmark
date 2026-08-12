"""在不把完整数据集载入内存的前提下，可复现地随机抽取 JSONL 记录。

核心方法是蓄水池抽样：完整扫描 N 条记录时，始终只保存 k 条候选记录的
位置元数据，从而让每条源记录最终被选中的概率都等于 k / N。
"""

# 推迟解析类型注解，避免运行时立即求值前向引用，并降低类型注解的运行开销。
from __future__ import annotations

# argparse：解析命令行中的输入、输出、样本量和随机种子等参数。
import argparse
# hashlib：计算源文件、输出文件以及每条候选记录的 SHA-256 哈希。
import hashlib
# json：解析每条 JSONL 记录，并生成结构化抽样清单。
import json
# os：执行原子替换和 fsync 强制落盘。
import os
# random：使用固定种子的伪随机数生成器，实现可复现抽样。
import random
# sys：把运行进度写入标准错误流，避免污染标准输出中的最终结果。
import sys
# time：分别记录单调运行时间和计算扫描速度。
import time
# dataclass：定义不可变的入选记录元数据结构。
from dataclasses import dataclass
# datetime：生成带本地时区的审计时间戳。
from datetime import datetime
# Path：跨平台、类型安全地处理文件路径。
from pathlib import Path
# Any：允许原始 subject_id、hadm_id 保持源 JSON 中的数据类型。
from typing import Any


class JsonlSamplingError(ValueError):
    """源 JSONL 存在歧义或结构错误、无法可靠抽样时抛出的异常。"""


# frozen=True 使候选记录不可变，避免保存偏移后被意外修改。
@dataclass(frozen=True)
class SelectedRecord:
    # 记录在源 JSONL 中的物理行号，从 1 开始。
    line_number: int
    # 该行第一个字节相对于文件开头的偏移量。
    byte_offset: int
    # 该行在源文件中的原始字节长度，包括原有换行符。
    byte_length: int
    # 该行原始字节的 SHA-256，用于写出前检测源文件是否发生变化。
    line_sha256: str
    # MIMIC 患者标识，仅写入审计清单，不参与抽样概率计算。
    subject_id: Any
    # MIMIC 住院标识，仅写入审计清单，不参与抽样概率计算。
    hadm_id: Any


def _now_iso() -> str:
    """返回包含本地时区、精确到秒的 ISO 8601 时间。"""
    # astimezone() 保留本地时区信息，便于之后判断任务实际运行时间。
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _partial_path(path: Path) -> Path:
    """为目标文件构造同目录的临时文件名。"""
    # 临时文件使用 .partial 后缀；只有完整写入并落盘后才替换为正式文件。
    return path.with_name(path.name + ".partial")


def _validate_paths(input_path: Path, output_path: Path, manifest_path: Path) -> None:
    """在开始长时间扫描前，验证所有输入输出路径。"""
    # 源路径必须是现有普通文件，否则立即失败。
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    # 三个路径必须互不相同，防止输出覆盖源数据或清单覆盖样本。
    if len({input_path, output_path, manifest_path}) != 3:
        raise ValueError("input, output and manifest paths must differ")
    # 分别检查样本文件和清单文件，默认拒绝覆盖任何已有结果。
    for target in (output_path, manifest_path):
        # 已存在正式结果时停止，确保历史结果不会被静默改写。
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {target}")
        # 计算与当前目标对应的临时文件路径。
        partial = _partial_path(target)
        # 已有 .partial 可能来自中断任务；拒绝覆盖，以免掩盖未处理的问题。
        if partial.exists():
            raise FileExistsError(f"refusing to overwrite incomplete output: {partial}")


def _parse_record(raw_line: bytes, line_number: int, byte_offset: int) -> dict[str, Any]:
    """解析一条原始 JSONL 字节行，并给出可定位到源文件的错误。"""
    # 空行不是合法记录；不能跳过，否则物理行号和抽样总体定义会变得含糊。
    if not raw_line.strip():
        raise JsonlSamplingError(
            f"line {line_number}, byte offset {byte_offset}: blank JSONL record"
        )
    # 对当前行做严格 JSON 解析；整个文件的每一条记录都会经过此检查。
    try:
        record = json.loads(raw_line)
    # 同时捕获 JSON 语法错误和 UTF-8 解码错误，并补充物理位置。
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise JsonlSamplingError(
            f"line {line_number}, byte offset {byte_offset}: {error}"
        ) from error
    # 本项目的一条住院记录必须是 JSON 对象，数组、数字或字符串均不接受。
    if not isinstance(record, dict):
        raise JsonlSamplingError(
            f"line {line_number}, byte offset {byte_offset}: record must be an object"
        )
    # 返回解析后的对象，以便抽取 subject_id 和 hadm_id 作为审计元数据。
    return record


def reservoir_sample_jsonl(
    # 要完整扫描的源 JSONL 文件。
    input_path: Path,
    # 抽样记录的目标 JSONL 文件。
    output_path: Path,
    # 保存随机种子、源行号和哈希等证据的 JSON 清单。
    manifest_path: Path,
    # 星号表示后续参数必须使用关键字传入，避免位置参数含义混淆。
    *,
    # 需要抽取的记录数 k。
    sample_size: int,
    # 固定随机种子；相同源文件和种子会得到相同样本。
    seed: int,
    # 每扫描多少条记录打印一次进度；0 表示不打印。
    progress_every: int = 0,
) -> dict[str, Any]:
    """对完整 JSONL 做等概率无放回抽样，并保留入选记录的源字节。

    蓄水池仅保存源文件偏移和审计元数据，不保存 1000 条大型住院记录本身；
    完整扫描结束后，再按照已保存的偏移读取入选行，因此内存占用接近常数。
    """
    # 样本量必须为正数，否则“抽样”没有明确含义。
    if sample_size <= 0:
        raise ValueError("sample_size must be greater than zero")
    # 负数的进度间隔无效；0 被专门定义为关闭进度输出。
    if progress_every < 0:
        raise ValueError("progress_every must be non-negative")

    # 转为绝对路径，保证清单中的路径明确且路径比较不受当前目录影响。
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    manifest_path = manifest_path.resolve()
    # 在创建目录或扫描大文件前先完成路径安全检查。
    _validate_paths(input_path, output_path, manifest_path)
    # 创建样本输出目录；parents=True 会同时创建缺失的父目录。
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 清单可以位于另一目录，因此单独确保它的父目录存在。
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # 正式样本对应的临时输出路径。
    output_partial = _partial_path(output_path)
    # 正式审计清单对应的临时输出路径。
    manifest_partial = _partial_path(manifest_path)
    # 使用局部随机数生成器，避免改变其他代码的全局随机状态。
    rng = random.Random(seed)
    # 蓄水池只保存最多 sample_size 个轻量元数据对象。
    reservoir: list[SelectedRecord] = []
    # 在扫描过程中增量计算完整源文件 SHA-256，无需再次读取 19.9 GB 文件。
    input_digest = hashlib.sha256()
    # 记录扫描开始前的源文件大小，用于进度百分比和审计。
    input_size = input_path.stat().st_size
    # 保存可读的任务开始时间。
    started_at = _now_iso()
    # monotonic() 不受系统时钟校准影响，适合计算耗时和速度。
    started = time.monotonic()
    # 累计已读取的非空、合法 JSON 对象记录数。
    record_count = 0
    # 标记正式样本是否已经生成，用于跨文件原子替换失败时回滚本次输出。
    created_output = False

    # 捕获整个扫描和写出阶段的异常，确保本次任务不留下半成品。
    try:
        # 二进制读取可以精确保留源字节，并提供可复现的字节偏移。
        with input_path.open("rb") as source:
            # 使用 readline() 流式读取；任何时刻只持有一条完整记录。
            while True:
                # 在读取当前行前记录其起始字节位置。
                byte_offset = source.tell()
                # 读取一条原始字节行，包括原文件中的换行符。
                raw_line = source.readline()
                # 空字节串只在到达文件末尾时出现，因此结束扫描。
                if not raw_line:
                    break
                # 当前物理行成为第 record_count 条记录，编号从 1 开始。
                record_count += 1
                # 将当前行字节加入源文件整体 SHA-256。
                input_digest.update(raw_line)
                # 严格验证 JSON，并取得住院标识等审计字段。
                record = _parse_record(raw_line, record_count, byte_offset)
                # 只保存该行的位置、长度和哈希，不把大记录长期留在内存。
                selected = SelectedRecord(
                    # 保存当前物理行号。
                    line_number=record_count,
                    # 保存当前行的起始字节偏移。
                    byte_offset=byte_offset,
                    # 保存读取该行时得到的确切字节数。
                    byte_length=len(raw_line),
                    # 保存行级哈希，写出前可检测源文件是否在扫描中被修改。
                    line_sha256=hashlib.sha256(raw_line).hexdigest(),
                    # 从源对象原样读取患者 ID；缺失时明确记录为 null。
                    subject_id=record.get("subject_id"),
                    # 从源对象原样读取住院 ID；缺失时明确记录为 null。
                    hadm_id=record.get("hadm_id"),
                )
                # 前 k 条记录直接填满蓄水池，因为此时还没有可替换的旧候选。
                if record_count <= sample_size:
                    reservoir.append(selected)
                # 从第 k+1 条开始，使用标准蓄水池替换规则。
                else:
                    # 在 [0, record_count) 中均匀取一个整数，使当前记录入选概率为 k/n。
                    replacement_index = rng.randrange(record_count)
                    # 只有随机位置落入蓄水池范围 [0, k) 时才替换已有候选。
                    if replacement_index < sample_size:
                        reservoir[replacement_index] = selected

                # 按用户指定频率打印进度；两个条件都满足才执行。
                if progress_every and record_count % progress_every == 0:
                    # 防止极短运行出现除以零，同时得到已运行秒数。
                    elapsed = max(time.monotonic() - started, 1e-9)
                    # 文件非空时按已读字节计算百分比；空文件视为已扫描完。
                    progress = source.tell() * 100 / input_size if input_size else 100.0
                    # 把平均读取速度换算为 MiB/s，便于观察大文件进度。
                    speed_mib = source.tell() / elapsed / (1024 * 1024)
                    # 进度写入 stderr；stdout 保留给机器可读的最终摘要。
                    print(
                        f"scanned={record_count:,} progress={progress:.2f}% "
                        f"speed={speed_mib:.2f} MiB/s",
                        file=sys.stderr,
                        # 立即刷新缓冲区，使长任务能够及时显示最新进度。
                        flush=True,
                    )

            # 完整扫描后再检查总体是否足够，避免返回不足 1000 条的伪成功结果。
            if record_count < sample_size:
                raise JsonlSamplingError(
                    f"source contains {record_count} records, fewer than requested "
                    f"sample size {sample_size}"
                )

            # 蓄水池内部顺序会因替换而打乱；按源行号排序后再写出。
            selected_records = sorted(reservoir, key=lambda item: item.line_number)
            # 增量计算最终样本文件哈希，写入清单供独立复核。
            output_digest = hashlib.sha256()
            # x 模式要求临时文件不存在，避免覆盖意外遗留文件。
            with output_partial.open("xb") as output:
                # 依次写出按源行号排序的 1000 个候选记录。
                for selected in selected_records:
                    # 直接跳到入选行的起始字节，不需要再次顺序扫描完整源文件。
                    source.seek(selected.byte_offset)
                    # 按扫描时保存的确切长度读取原始记录。
                    raw_line = source.read(selected.byte_length)
                    # 行哈希不一致说明源文件在任务期间发生了变化，必须停止。
                    if hashlib.sha256(raw_line).hexdigest() != selected.line_sha256:
                        raise JsonlSamplingError(
                            "source changed while sampling at line "
                            f"{selected.line_number}"
                        )
                    # 原行已有换行符时完全保留；仅为文件末尾无换行的记录补一个换行。
                    preserved_line = raw_line if raw_line.endswith(b"\n") else raw_line + b"\n"
                    # 将该条记录的原始字节写入临时样本文件。
                    output.write(preserved_line)
                    # 同步更新最终样本文件的 SHA-256。
                    output_digest.update(preserved_line)
                # 把 Python 用户态缓冲区的数据推送给操作系统。
                output.flush()
                # 要求操作系统把文件内容刷新到磁盘，再进入正式文件替换阶段。
                os.fsync(output.fileno())

        # 计算从开始扫描到样本临时文件完整落盘的总耗时。
        elapsed_seconds = time.monotonic() - started
        # 构建完整审计清单，使本次抽样可以复现、定位和独立验证。
        manifest = {
            # 明确记录采用标准无放回蓄水池抽样，而不是前 1000 条截取。
            "algorithm": "reservoir_sampling_without_replacement",
            # 记录任务开始时间。
            "started_at": started_at,
            # 记录任务完成时间。
            "completed_at": _now_iso(),
            # 记录实际运行秒数。
            "elapsed_seconds": elapsed_seconds,
            # 记录随机种子，是复现同一抽样结果的必要条件。
            "seed": seed,
            # 记录目标样本量。
            "sample_size": sample_size,
            # 汇总源文件路径、规模、记录数和完整性哈希。
            "source": {
                "path": str(input_path),
                "byte_size": input_size,
                "record_count": record_count,
                "sha256": input_digest.hexdigest(),
            },
            # 汇总输出文件路径、规模、记录数、哈希和排序规则。
            "output": {
                "path": str(output_path),
                "byte_size": output_partial.stat().st_size,
                "record_count": sample_size,
                "sha256": output_digest.hexdigest(),
                "ordering": "ascending_source_line_number",
            },
            # 为每条样本保存从输出记录到源文件物理位置的一一映射。
            "selected_records": [
                {
                    # 当前记录在样本 JSONL 中的顺序，从 1 开始。
                    "output_record_number": output_number,
                    # 当前记录原来位于源 JSONL 的物理行号。
                    "source_line_number": selected.line_number,
                    # 当前记录在源文件中的起始字节位置。
                    "source_byte_offset": selected.byte_offset,
                    # 当前记录在源文件中的原始字节长度。
                    "source_byte_length": selected.byte_length,
                    # 当前源行的 SHA-256，可用于逐条校验。
                    "source_line_sha256": selected.line_sha256,
                    # 当前样本的患者 ID，方便人工审计和定位。
                    "subject_id": selected.subject_id,
                    # 当前样本的住院 ID，方便人工审计和定位。
                    "hadm_id": selected.hadm_id,
                }
                # enumerate 同时生成从 1 开始的输出序号和对应候选对象。
                for output_number, selected in enumerate(selected_records, start=1)
            ],
        }
        # 以独占文本模式创建清单临时文件，避免覆盖已有文件。
        with manifest_partial.open("x", encoding="utf-8", newline="\n") as file:
            # 使用 UTF-8、中文不转义、两空格缩进，生成可读 JSON 清单。
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            # 在文件末尾补一个标准换行，便于命令行工具处理。
            file.write("\n")
            # 把 Python 文本缓冲区的数据推送给操作系统。
            file.flush()
            # 要求操作系统把清单内容刷新到磁盘。
            os.fsync(file.fileno())

        # 样本临时文件完整落盘后，原子替换为正式输出文件。
        os.replace(output_partial, output_path)
        # 记录正式样本已经产生；若下一步失败，需要删除本次样本以保持成套交付。
        created_output = True
        # 清单临时文件也完整落盘后，原子替换为正式清单文件。
        os.replace(manifest_partial, manifest_path)
        # 返回完整清单，供调用方继续验证或展示摘要。
        return manifest
    # 任意异常都进入统一清理流程，不吞掉原始错误。
    except Exception:
        # 删除本次运行创建的样本和清单临时文件。
        for partial in (output_partial, manifest_partial):
            partial.unlink(missing_ok=True)
        # 若样本已正式生成但清单生成失败，也删除样本，避免不成套的输出。
        if created_output:
            output_path.unlink(missing_ok=True)
        # 原样重新抛出异常，保留真实错误类型和调用栈。
        raise


def create_parser() -> argparse.ArgumentParser:
    """定义命令行接口及其默认参数。"""
    # 创建顶层参数解析器，并提供命令用途说明。
    parser = argparse.ArgumentParser(
        description="Uniformly sample a complete JSONL file with reservoir sampling"
    )
    # --input：必须提供的源 JSONL 路径，并自动转换为 Path。
    parser.add_argument("--input", type=Path, required=True)
    # --output：必须提供的样本 JSONL 路径。
    parser.add_argument("--output", type=Path, required=True)
    # --manifest：必须提供的审计清单 JSON 路径。
    parser.add_argument("--manifest", type=Path, required=True)
    # --sample-size：默认随机抽取 1000 条记录。
    parser.add_argument("--sample-size", type=int, default=1000)
    # --seed：默认使用任务日期 20260812，保证本次结果可复现。
    parser.add_argument("--seed", type=int, default=20260812)
    # --progress-every：默认每扫描 1000 条向 stderr 报告一次进度。
    parser.add_argument("--progress-every", type=int, default=1000)
    # 返回配置完整的解析器，由 main() 实际读取命令行。
    return parser


def main() -> None:
    """解析命令行、执行抽样并打印简洁结果摘要。"""
    # 读取并验证当前命令行参数。
    args = create_parser().parse_args()
    # 调用核心函数；所有可变参数均以关键字方式传入。
    manifest = reservoir_sample_jsonl(
        # 源 JSONL 路径。
        args.input,
        # 样本 JSONL 路径。
        args.output,
        # 抽样审计清单路径。
        args.manifest,
        # 用户指定或默认的样本量。
        sample_size=args.sample_size,
        # 用户指定或默认的固定随机种子。
        seed=args.seed,
        # 用户指定或默认的进度输出频率。
        progress_every=args.progress_every,
    )
    # 只向终端打印摘要，不重复输出清单中 1000 条逐记录明细。
    print(
        # 将摘要字典序列化为便于阅读的 JSON。
        json.dumps(
            {
                # 抽样算法名称。
                "algorithm": manifest["algorithm"],
                # 实际使用的随机种子。
                "seed": manifest["seed"],
                # 实际抽样记录数。
                "sample_size": manifest["sample_size"],
                # 源文件规模、记录数及哈希。
                "source": manifest["source"],
                # 输出文件规模、记录数、哈希及排序规则。
                "output": manifest["output"],
                # 完整逐记录审计信息所在的清单绝对路径。
                "manifest_path": str(args.manifest.resolve()),
            },
            # 保留中文字符，不转换为 Unicode 转义序列。
            ensure_ascii=False,
            # 使用两空格缩进提高终端可读性。
            indent=2,
        )
    )


# 只有直接运行此文件或使用 python -m 时才执行命令行入口；导入模块不会自动抽样。
if __name__ == "__main__":
    # 启动命令行主流程。
    main()
