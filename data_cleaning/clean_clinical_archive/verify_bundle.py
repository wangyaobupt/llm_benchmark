"""Verify that the portable cleaner contains complete, unchanged resources."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from .decoder import DecodeError, file_sha256, load_json_dictionaries


BUNDLE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = BUNDLE_ROOT / "bundle-manifest.json"


class BundleVerificationError(ValueError):
    """Raised when the portable bundle is incomplete or corrupted."""


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BundleVerificationError(
            f"bundle manifest does not exist: {MANIFEST_PATH}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise BundleVerificationError(
            f"invalid bundle manifest: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise BundleVerificationError("bundle manifest root must be an object")
    return manifest


def verify_bundle() -> dict[str, Any]:
    manifest = _load_manifest()
    if sys.version_info[:2] != (3, 12):
        raise BundleVerificationError(
            "portable cleaner requires Python 3.12; got "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )

    missing = [
        relative
        for relative in manifest.get("required_files", [])
        if not (BUNDLE_ROOT / relative).is_file()
    ]
    if missing:
        raise BundleVerificationError(
            "portable bundle is missing required files: " + ", ".join(missing)
        )

    try:
        dictionaries, files = load_json_dictionaries(
            BUNDLE_ROOT / "dictionaries"
        )
    except (DecodeError, FileNotFoundError) as exc:
        raise BundleVerificationError(str(exc)) from exc

    expected_dictionaries = manifest.get("dictionaries")
    if not isinstance(expected_dictionaries, dict):
        raise BundleVerificationError(
            "bundle manifest dictionaries must be an object"
        )
    if set(files) != set(expected_dictionaries):
        raise BundleVerificationError("dictionary inventory does not match manifest")

    verified: dict[str, dict[str, Any]] = {}
    for name, expected in expected_dictionaries.items():
        path = BUNDLE_ROOT / expected["file"]
        actual = {
            "file": expected["file"],
            "rows": len(dictionaries[name]),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for field in ("rows", "bytes", "sha256"):
            if actual[field] != expected[field]:
                raise BundleVerificationError(
                    f"dictionary {name} {field} mismatch: "
                    f"expected {expected[field]!r}, got {actual[field]!r}"
                )
        verified[name] = actual

    return {
        "schema": manifest["schema"],
        "bundle_root": BUNDLE_ROOT.as_posix(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "required_files": len(manifest["required_files"]),
        "dictionaries": verified,
        "dictionary_rows": sum(item["rows"] for item in verified.values()),
        "status": "ok",
    }


def main() -> None:
    print(json.dumps(verify_bundle(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
