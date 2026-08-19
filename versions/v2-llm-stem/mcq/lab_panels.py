"""Laboratory panel mapping (derived from the v1 exploratory pipeline).

Individual analytes are near-universal (BMP/CBC), so the laboratory comparison
class ranks the PANEL rather than the raw analyte. This mapping is the v1
placeholder, carried into v2 verbatim; it remains pending clinical review
(``docs/reports/clinical-review-freeze-checklist.md``) and is not frozen.
"""
from __future__ import annotations

LAB_PANEL_MAP: dict[str, str] = {
    # Basic metabolic / chemistry (universal)
    "lab:50971": "chemistry_bmp", "lab:50912": "chemistry_bmp",
    "lab:51006": "chemistry_bmp", "lab:50902": "chemistry_bmp",
    "lab:50983": "chemistry_bmp", "lab:50931": "chemistry_bmp",
    "lab:50868": "chemistry_bmp", "lab:50882": "chemistry_bmp",
    "lab:50960": "chemistry_bmp", "lab:50893": "chemistry_bmp",
    "lab:50970": "chemistry_bmp",
    # CBC / hematology (universal)
    "lab:51265": "cbc_hematology", "lab:51221": "cbc_hematology",
    "lab:51248": "cbc_hematology", "lab:51279": "cbc_hematology",
    "lab:51250": "cbc_hematology", "lab:51277": "cbc_hematology",
    "lab:51222": "cbc_hematology", "lab:51249": "cbc_hematology",
    "lab:51301": "cbc_hematology", "lab:52172": "cbc_hematology",
    "lab:51146": "cbc_hematology", "lab:51256": "cbc_hematology",
    "lab:51254": "cbc_hematology", "lab:51200": "cbc_hematology",
    "lab:51244": "cbc_hematology", "lab:51144": "cbc_hematology",
    "lab:52075": "cbc_hematology", "lab:52069": "cbc_hematology",
    "lab:51133": "cbc_hematology", "lab:52074": "cbc_hematology",
    "lab:52073": "cbc_hematology", "lab:52135": "cbc_hematology",
    # Coagulation
    "lab:51274": "coagulation", "lab:51237": "coagulation",
    "lab:51275": "coagulation", "lab:51214": "coagulation",
    "lab:50915": "coagulation", "lab:51297": "coagulation",
    # Cardiac markers
    "lab:51003": "cardiac_markers", "lab:50911": "cardiac_markers",
    "lab:50908": "cardiac_markers", "lab:50963": "cardiac_markers",
    # Liver
    "lab:50885": "liver_panel", "lab:50861": "liver_panel",
    "lab:50878": "liver_panel", "lab:50863": "liver_panel",
    "lab:50862": "liver_panel", "lab:50976": "liver_panel",
    "lab:50927": "liver_panel", "lab:50883": "liver_panel",
    "lab:50884": "liver_panel",
    # Pancreatic
    "lab:50956": "pancreatic", "lab:50867": "pancreatic",
    # Thyroid
    "lab:50993": "thyroid", "lab:50995": "thyroid",
    "lab:50994": "thyroid", "lab:51001": "thyroid",
    # Blood gas
    "lab:50820": "blood_gas", "lab:50821": "blood_gas",
    "lab:50818": "blood_gas", "lab:50802": "blood_gas",
    "lab:50804": "blood_gas", "lab:50822": "blood_gas",
    "lab:50824": "blood_gas", "lab:50806": "blood_gas",
    "lab:50808": "blood_gas", "lab:50817": "blood_gas",
    "lab:50803": "blood_gas", "lab:50813": "blood_gas",
    # Inflammatory / acute phase / tissue
    "lab:50954": "inflammatory", "lab:50889": "inflammatory",
    "lab:50924": "inflammatory", "lab:51288": "inflammatory",
    "lab:50866": "inflammatory",
    # Renal / other chemistry
    "lab:50920": "renal_function", "lab:51007": "renal_function",
    "lab:51082": "renal_function", "lab:51100": "renal_function",
    # Iron studies
    "lab:50952": "iron_studies", "lab:50998": "iron_studies",
    "lab:50953": "iron_studies",
    # Urinalysis
    "lab:51478": "urinalysis", "lab:51464": "urinalysis",
    "lab:51492": "urinalysis", "lab:51506": "urinalysis",
    "lab:51498": "urinalysis", "lab:51508": "urinalysis",
    "lab:51514": "urinalysis", "lab:51491": "urinalysis",
    "lab:51487": "urinalysis", "lab:51486": "urinalysis",
    "lab:51484": "urinalysis", "lab:51466": "urinalysis",
    "lab:51493": "urinalysis", "lab:51463": "urinalysis",
    "lab:51476": "urinalysis", "lab:51516": "urinalysis",
    "lab:51519": "urinalysis", "lab:51512": "urinalysis",
    "lab:51482": "urinalysis",
    # Toxicology / drug levels
    "lab:51009": "toxicology", "lab:50917": "toxicology",
    "lab:50922": "toxicology", "lab:50856": "toxicology",
    "lab:50981": "toxicology", "lab:50967": "toxicology",
    "lab:51008": "toxicology", "lab:50986": "toxicology",
    "lab:50929": "toxicology", "lab:50961": "toxicology",
    "lab:51079": "toxicology", "lab:51092": "toxicology",
    "lab:51090": "toxicology", "lab:51075": "toxicology",
    "lab:51071": "toxicology", "lab:51074": "toxicology",
    "lab:50880": "toxicology", "lab:50879": "toxicology",
    "lab:51989": "toxicology", "lab:51089": "toxicology",
}

_OTHER = "other"


def lab_panel(concept_id: str | None) -> str:
    return LAB_PANEL_MAP.get(concept_id or "", _OTHER)
