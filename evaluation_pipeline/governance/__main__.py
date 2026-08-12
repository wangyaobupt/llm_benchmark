"""CLI for protocol validation and deterministic locking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .protocol import (
    ProtocolBundleError,
    build_protocol_lock,
    load_protocol_bundle,
    validate_protocol_bundle,
    write_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "lock"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--reason-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    bundle = load_protocol_bundle(args.protocol, args.schema, args.reason_registry)
    if args.command == "validate":
        result = validate_protocol_bundle(bundle)
    else:
        result = build_protocol_lock(bundle)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProtocolBundleError as error:
        raise SystemExit(str(error)) from error
