"""Direct MIMIC CSV.GZ → visit-row extract for five MCQ types."""

from .config import VisitExtractConfig
from .pipeline import run

SCHEMA_NAME = "mcq_visit_extract"
SCHEMA_VERSION = "3.1.0"

__all__ = ["VisitExtractConfig", "run", "SCHEMA_NAME", "SCHEMA_VERSION"]
