"""Config loading: thresholds profiles and prompts (design doc §7.3, §9, §12)."""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent / "config"

VALID_PROFILES = ("formal", "exploratory")


def load_thresholds(profile: str = "exploratory",
                    path: Path | None = None) -> dict:
    path = path or CONFIG_DIR / "thresholds.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"unknown threshold profile: {profile} (valid: {sorted(profiles)})")
    return dict(profiles[profile])


def load_prompt(name: str, path: Path | None = None) -> str:
    path = path or CONFIG_DIR / "prompts" / name
    return path.read_text(encoding="utf-8")
