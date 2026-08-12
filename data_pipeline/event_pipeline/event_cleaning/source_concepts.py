"""Source concepts required while constructing cleaned events."""

from __future__ import annotations

import re
from typing import Any


VITAL_CONCEPTS = {
    "heart_rate": ("vital:heart_rate", "Heart rate", "/min"),
    "blood_pressure": ("vital:blood_pressure", "Blood pressure", "mmHg"),
    "temperature": ("vital:temperature", "Temperature", "°F"),
    "respiratory_rate": ("vital:respiratory_rate", "Respiratory rate", "/min"),
    "oxygen_saturation": ("vital:oxygen_saturation", "Oxygen saturation", "%"),
    "pain_score": ("vital:pain_score", "Pain score", None),
}


def normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


__all__ = ["VITAL_CONCEPTS", "normalized_text"]
