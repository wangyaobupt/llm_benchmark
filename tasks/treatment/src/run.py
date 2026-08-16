"""Treatment/disposition task (task 3): chief complaint -> most likely treatment.

Behavioral gold = T1 开立/处方 (POE + prescriptions), per
docs/reports/five-dimension-execution-refinement.md §2.3. Normative gold
(bundle N1 auto / Beers N2 semi-auto / MAI N3 manual) is a separate manual
track, not automated here.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark_common.task import run_task

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\treatment\output")


# Non-treatment items (devices/packaging + IV vehicles) to exclude.
# NOTE: "soln" is deliberately NOT here — it is a formulation word (e.g.
# "Albuterol 0.083% Neb Soln"), not a vehicle; excluding it swallowed real drugs.
_NON_TREATMENT = (
    "syringe", "vial", "bag", "cassette", "flush",
    "sodium chloride", "dextrose", "lactated ringers", "sterile water",
    "saline", "d5", "d10", "d30",
)

# Medication -> treatment category (substring match on lowercase name).
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


# Chronic home-med continuation categories: rarely an acute ED treatment, but
# their low baseline inflates selectivity into spurious gold (e.g. "abnormal
# mri -> vaccine", "abnormal labs -> antigout"). Excluded from the candidate
# (answer) space per the P3 default; adjustable.
_CHRONIC_HOME_MED = {
    "vaccine", "sleep_aid", "antidepressant", "antigout", "thyroid", "vitamin",
}


def medication_category(name):
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
                return None if cat in _CHRONIC_HOME_MED else cat
    return None


# Non-procedure items (billing, communication, diagnostic imaging/labs, IV gauges).
_NON_PROCEDURE = (
    "gauge", "observation", "family updated", "or received",
    "x-ray", "xray", "ct scan", "ultrasound", "magnetic resonance", "ekg", "ecg",
    "cultured", "culture", "swab", "eeg",
)

_PROCEDURE_CATEGORIES = {
    "cardiac_intervention": ("coronary", "cardiac catheterization", "angioplasty",
                             "stent", "arteriography", "heart"),
    "respiratory_support": ("ventilation", "intubation", "extubation",
                            "endotracheal", "tracheostomy", "respiratory"),
    "vascular_access": ("arterial line", "central venous", "picc", "multi lumen",
                        "venous catheterization", "dialysis catheter"),
    "renal_replacement": ("hemodialysis", "urinary filtration", "ultrafiltration"),
    "urinary_catheter": ("foley",),
    "gi_procedure": ("intestinal tract", "colonoscopy", "endoscopy",
                     "paracentesis", "gastrostomy", "esophago"),
    "nutritional_support": ("nutritional substance", "enteral", "feeding"),
    "echo": ("echo",),
    "line_placement": ("infusion device", "catheter placement"),
}


def procedure_category(name):
    if not isinstance(name, str) or not name:
        return None
    s = name.lower().strip()
    for kw in _NON_PROCEDURE:
        if kw in s:
            return None
    for cat, kws in _PROCEDURE_CATEGORIES.items():
        for kw in kws:
            if kw in s:
                return cat
    return None


def _medication_candidate(events, event_kind):
    d = events[events["event_kind"] == event_kind].copy()
    d["candidate"] = d["source_label"].map(medication_category)
    d = d[d["candidate"].notna()]
    return d[["hadm_id", "candidate"]].drop_duplicates()


def candidate_t1(events):
    """T1 开立/处方 (POE + prescriptions)."""
    return _medication_candidate(events, "medication_ordered")


def candidate_t2(events):
    """T2 执行 (eMAR)."""
    return _medication_candidate(events, "medication_administered")


def candidate_t3(events):
    """T3 手术/操作 -> procedure category."""
    d = events[events["event_kind"].isin(
        ["procedure_performed", "procedure_recorded_post_hoc"])].copy()
    d["candidate"] = d["source_label"].map(procedure_category)
    d = d[d["candidate"].notna()]
    return d[["hadm_id", "candidate"]].drop_duplicates()


LAYERS = {
    "t1": (candidate_t1, "ordered"),
    "t2": (candidate_t2, "administered"),
    "t3": (candidate_t3, "performed"),
}


def make_pool(candidate_fn):
    def pool(events):
        d = candidate_fn(events)
        return (d.groupby("candidate")["hadm_id"].nunique()
                 .sort_values(ascending=False).index.tolist())
    return pool


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--role", default="development")
    ap.add_argument("--layer", default="t1", choices=["t1", "t2", "t3"])
    ap.add_argument("--min-share-gap", type=float, default=0.10)
    ap.add_argument("--min-gold-share", type=float, default=0.0)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    candidate_fn, verb = LAYERS[args.layer]
    out_dir = args.out_dir or (OUT / args.layer / "development")
    stem_fn = lambda c: (f"A patient presents to the emergency department with {c}. "
                         f"Which treatment is most likely to be {verb}?")

    s = run_task(args.events, args.split, candidate_fn, make_pool(candidate_fn),
                 stem_fn, f"treatment_{args.layer}", role=args.role, out_dir=out_dir,
                 min_share_gap=args.min_share_gap, min_gold_share=args.min_gold_share)
    print("=" * 70)
    print(f"TREATMENT (task 3, {args.layer}) — behavioral gold, {s['gold_semantics']}")
    print("=" * 70)
    print(f"admissions: {s['admissions_total']}, patterns: {s['n_gold_patterns']}, "
          f"questions: {s['n_questions']}")
    for g in s["gold_patterns"][:15]:
        print(f"  {g['condition']:<30} -> {g['gold_candidate']} (sel={g['gold_selectivity']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
