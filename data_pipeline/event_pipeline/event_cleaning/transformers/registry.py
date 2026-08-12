"""Single transformer registry assembled from clinical-domain modules."""

from .diagnoses_procedures import (
    transform_diagnosis,
    transform_drg,
    transform_ed_diagnosis,
    transform_hcpcs,
    transform_procedure_icd,
    transform_service,
    transform_transfer,
)
from .ed import (
    transform_ed_medrecon,
    transform_ed_pyxis,
    transform_ed_triage,
    transform_ed_vitals,
)
from .icu import (
    transform_icu_datetime,
    transform_icu_ingredient,
    transform_icu_input,
    transform_icu_output,
    transform_icu_procedure,
)
from .laboratory import transform_labevent, transform_microbiology
from .medications import transform_emar, transform_pharmacy, transform_prescription
from .notes import transform_discharge_note, transform_radiology_note
from .orders import transform_poe, transform_poe_timeline


TRANSFORMERS = {
    name: value
    for name, value in globals().copy().items()
    if name.startswith("transform_") and callable(value)
}

__all__ = ["TRANSFORMERS"]
