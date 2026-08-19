"""Medication name -> clinical category (reused from the v1 treatment task).

The category table is copied verbatim from ``tasks/treatment/src/run.py`` (the
validated exploratory mapping). Two entry points are exposed:

* ``medication_category`` — the v1 treatment-answer semantics (excludes chronic
  home-med categories from the ANSWER space).
* ``medication_feature`` — the phenotype condition-feature semantics: keeps
  chronic home-med categories (metformin/levothyroxine/…) because "medications
  on admission" are exactly the signal we want as a condition feature.
"""
from __future__ import annotations

# Non-medication items (devices/packaging + IV vehicles) — excluded everywhere.
_NON_TREATMENT = (
    "syringe", "vial", "bag", "cassette", "flush",
    "sodium chloride", "dextrose", "lactated ringers", "sterile water",
    "saline", "d5", "d10", "d30",
)

_MEDICATION_CATEGORIES = {
    "anticoagulant": ("heparin", "warfarin", "enoxaparin", "apixaban", "rivaroxaban"),
    "antiplatelet": ("aspirin", "clopidogrel", "ticagrelor", "prasugrel", "eptifibatide",
                     "dipyridamole"),
    "statin": ("atorvastatin", "simvastatin", "rosuvastatin", "pravastatin"),
    "beta_blocker": ("metoprolol", "carvedilol", "labetalol", "atenolol", "propranolol"),
    "ace_arb": ("lisinopril", "losartan", "valsartan", "ramipril", "enalapril"),
    "diuretic": ("furosemide", "torsemide", "spironolactone", "hydrochlorothiazide"),
    "analgesic": ("acetaminophen", "hydromorphone", "morphine", "oxycodone",
                  "fentanyl", "tramadol", "gabapentin", "naproxen",
                  "ibuprofen", "ketorolac", "diclofenac", "celecoxib"),
    "laxative": ("senna", "docusate", "polyethylene glycol", "bisacodyl", "lactulose"),
    "ppi": ("omeprazole", "pantoprazole", "lansoprazole", "esomeprazole"),
    "h2_blocker": ("ranitidine", "famotidine"),
    "antibiotic": ("vancomycin", "cefepime", "ceftriaxone", "ciprofloxacin",
                   "azithromycin", "levofloxacin", "piperacillin", "ceftaroline",
                   "meropenem", "metronidazole", "doxycycline", "erythromycin",
                   "clarithromycin", "fosfomycin"),
    "antidiabetic": ("insulin", "metformin", "glipizide", "glucagon", "glucose gel"),
    "bronchodilator": ("albuterol", "ipratropium", "tiotropium"),
    "antiemetic": ("ondansetron", "promethazine", "metoclopramide"),
    "antidepressant": ("trazodone", "sertraline", "citalopram", "escitalopram",
                       "fluoxetine", "mirtazapine", "doxepin", "amitriptyline",
                       "duloxetine", "venlafaxine", "bupropion"),
    "vitamin": ("vitamin d", "multivitamin", "folic acid", "cyanocobalamin", "thiamine"),
    "mineral": ("calcium carbonate", "ferrous sulfate", "magnesium oxide",
                "calcium gluconate", "magnesium sulfate"),
    "electrolyte": ("potassium chloride", "neutra-phos", "phytonadione",
                    "potassium phosphate"),
    "vasopressor": ("norepinephrine", "dopamine", "epinephrine", "phenylephrine",
                    "vasopressin"),
    "antiarrhythmic": ("amiodarone", "digoxin", "diltiazem", "verapamil", "sotalol"),
    "nitrate": ("nitroglycerin", "isosorbide"),
    "steroid": ("prednisone", "prednisolone", "methylprednisolone", "hydrocortisone",
                "fluticasone"),
    "vaccine": ("vaccine", "influenza"),
    "thyroid": ("levothyroxine", "liothyronine"),
    "sedative": ("lorazepam", "propofol", "midazolam", "zolpidem"),
    "sleep_aid": ("ramelteon", "melatonin"),
    "antihypertensive_other": ("amlodipine", "nifedipine", "hydralazine", "clonidine",
                               "tamsulosin", "finasteride", "doxazosin"),
    "anticonvulsant": ("levetiracetam", "phenytoin", "valproic", "carbamazepine",
                       "lamotrigine"),
    "antigout": ("allopurinol", "colchicine"),
    "antacid": ("simethicone", "maalox"),
    "local_anesthetic": ("lidocaine", "bupivacaine"),
    "phosphate_binder": ("sevelamer"),
}

# Chronic home-med continuation categories (rarely an acute ED treatment) —
# excluded only from the v1 treatment ANSWER space.
_CHRONIC_HOME_MED = {
    "vaccine", "sleep_aid", "antidepressant", "antigout", "thyroid", "vitamin",
}


def _match_category(name: str) -> str | None:
    if not isinstance(name, str) or not name:
        return None
    s = name.lower().strip()
    if s in ("ns", "sw", "nan", "none"):
        return None
    for kw in _NON_TREATMENT:
        if kw in s:
            return None
    for cat, kws in _MEDICATION_CATEGORIES.items():
        for kw in kws:
            if kw in s:
                return cat
    return None


def medication_category(name) -> str | None:
    """v1 treatment-answer semantics (excludes chronic home-med categories)."""
    cat = _match_category(name)
    if cat in _CHRONIC_HOME_MED:
        return None
    return cat


def medication_feature(name) -> str | None:
    """Phenotype condition-feature semantics (keeps chronic home-med categories)."""
    return _match_category(name)
