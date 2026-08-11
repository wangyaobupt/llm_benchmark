"""Raw MIMIC admission archive: one admission, original source rows only."""

SCHEMA_NAME = "mimic_admission_raw"
SCHEMA_VERSION = "1.0.0"

from .config import RawArchiveConfig
from .extractor import run

__all__ = ["RawArchiveConfig", "run", "SCHEMA_NAME", "SCHEMA_VERSION"]
