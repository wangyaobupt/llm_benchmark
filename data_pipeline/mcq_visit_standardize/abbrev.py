"""Expand EHR / MIMIC chief-complaint abbreviations to full English.

Applied on casefolded text. Replacement strings are the canonical English
form (no abbreviations). Transform and review proposals must use these
strings rather than the source shorthand (B/L, R/L, s/p, SBO, …).
"""

from __future__ import annotations

import re

from .text import collapse_ws

# Longest / most specific first. Patterns match casefolded text.
_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    # Slash and comparison forms
    (r"\bb\s*/\s*l\b", "bilateral"),
    (r"\bbilat\.?\b", "bilateral"),
    (r"\bs\s*/\s*p\b", "status post"),
    (r"\bn\s*/\s*v\s*/\s*d\b", "nausea, vomiting, and diarrhea"),
    (r"\bn\s*/\s*v\b", "nausea and vomiting"),
    (r"\bnv\b", "nausea and vomiting"),
    (r"\bn\s*&\s*v\b", "nausea and vomiting"),
    (r"\bbib\b", "brought in by"),
    (r"\bc\s*/\s*o\b", "complains of"),
    (r"\bw\s*/\s*o\b", "without"),
    (r"\br\s*/\s*o\b", "rule out"),
    (r"\bh\s*/\s*o\b", "history of"),
    (r"\bf\s*/\s*u\b", "follow-up"),
    (r"\bd\s*/\s*c\b", "discharge"),
    (r"\bc\s*/\s*b\b", "complicated by"),
    (r"\bp\s*/\s*w\b", "presents with"),
    (r"\bc\s*/\s*f\b", "concern for"),
    (r"\by\s*/\s*o\b", "year-old"),
    (r"\bh\s*/\s*h\b", "hemoglobin/hematocrit"),
    (r"\bh\s*/\s*a\b", "headache"),
    (r"\btib\s*/\s*fib\b", "tibia/fibula"),
    (r"\br\s*>\s*l\b", "right greater than left"),
    (r"\bl\s*>\s*r\b", "left greater than right"),
    (r"\bw/", "with "),
    # Contextual phrases that would be wrong if tokens expanded alone
    (r"\bhd\s+mtx\b", "high-dose methotrexate"),
    (r"\baltered\s+ms\b", "altered mental status"),
    (r"\balt\.?\s*ms\b", "altered mental status"),
    (r"\bms\s+changes\b", "mental status changes"),
    (r"\bchange(?:s)?\s+ms\b", "mental status changes"),
    (r"\blow\s+sat(?:s|uration)?\b", "low oxygen saturation"),
    (r"\blow\s+hct\b", "low hematocrit"),
    (r"\blow\s+crit\b", "low hematocrit"),
    (r"\blow\s+hgb\b", "low hemoglobin"),
    (r"\bped(?:estrian)?\s+struck\b", "pedestrian struck"),
    (r"\bresp(?:iratory)?\s+distress\b", "respiratory distress"),
    (r"\babdo?\s+pain\b", "abdominal pain"),
    (r"\bupper\s+gi\s+bleed(?:ing)?\b", "upper gastrointestinal bleeding"),
    (r"\bgi\s+bleed(?:ing)?\b", "gastrointestinal bleeding"),
    (r"\bl[\s-]+spine\b", "lumbar spine"),
    (r"\bleft\s+sided\b", "left-sided"),
    (r"\bright\s+sided\b", "right-sided"),
    (r"\b(?:lt|l)[\s-]+sided\b", "left-sided"),
    (r"\b(?:rt|r)[\s-]+sided\b", "right-sided"),
    (r"\bnausea\s*/\s*vomiting\b", "nausea and vomiting"),
    (
        r"\bb(?=\s+(?:leg|foot|feet|knee|arm|hand|hip|ankle|calf|thigh|ue|le)\b)",
        "bilateral",
    ),
    # Extremity / quadrant / lobe (before generic L/R)
    (r"\blle\b", "left lower extremity"),
    (r"\brle\b", "right lower extremity"),
    (r"\blue\b", "left upper extremity"),
    (r"\brue\b", "right upper extremity"),
    (r"\bble\b", "bilateral lower extremities"),
    (r"\ble\b", "lower extremity"),
    (r"\bue\b", "upper extremity"),
    (r"\bruq\b", "right upper quadrant"),
    (r"\bluq\b", "left upper quadrant"),
    (r"\brlq\b", "right lower quadrant"),
    (r"\bllq\b", "left lower quadrant"),
    (r"\brll\b", "right lower lobe"),
    (r"\blll\b", "left lower lobe"),
    (r"\brul\b", "right upper lobe"),
    (r"\blul\b", "left upper lobe"),
    (r"\brml\b", "right middle lobe"),
    (r"\bbka\b", "below-knee amputation"),
    (r"\blbp\b", "low back pain"),
    # Generic laterality: standalone L/R/Lt/Rt before a non-digit token
    (r"\b(?:lt|l)(?=\s+(?!\d))", "left"),
    (r"\b(?:rt|r)(?=\s+(?!\d))", "right"),
    # Diagnoses and findings
    (r"\bnstemi\b", "non-ST-elevation myocardial infarction"),
    (r"\bstemi\b", "ST-elevation myocardial infarction"),
    (r"\besrd\b", "end-stage renal disease"),
    (r"\bdka\b", "diabetic ketoacidosis"),
    (r"\butis\b", "urinary tract infections"),
    (r"\buti\b", "urinary tract infection"),
    (r"\bluts\b", "lower urinary tract symptoms"),
    (r"\bbph\b", "benign prostatic hyperplasia"),
    (r"\bhtn\b", "hypertension"),
    (r"\bhld\b", "hyperlipidemia"),
    (r"\bcopd\b", "chronic obstructive pulmonary disease"),
    (r"\bdvts\b", "deep vein thromboses"),
    (r"\bdvt\b", "deep vein thrombosis"),
    (r"\baaa\b", "abdominal aortic aneurysm"),
    (r"\btbi\b", "traumatic brain injury"),
    (r"\bugib\b", "upper gastrointestinal bleeding"),
    (r"\bgib\b", "gastrointestinal bleeding"),
    (r"\bafib\b", "atrial fibrillation"),
    (r"\ba-fib\b", "atrial fibrillation"),
    (r"\baflutter\b", "atrial flutter"),
    (r"\ba-flutter\b", "atrial flutter"),
    (r"\brvr\b", "rapid ventricular response"),
    (r"\betoh\b", "alcohol"),
    (r"\boa\b", "osteoarthritis"),
    (r"\bchf\b", "congestive heart failure"),
    (r"\bcad\b", "coronary artery disease"),
    (r"\bcva\b", "cerebrovascular accident"),
    (r"\btia\b", "transient ischemic attack"),
    (r"\bpna\b", "pneumonia"),
    (r"\buri\b", "upper respiratory infection"),
    (r"\bili\b", "influenza-like illness"),
    (r"\bsbo\b", "small bowel obstruction"),
    (r"\bboo\b", "bladder outlet obstruction"),
    (r"\bgsw\b", "gunshot wound"),
    (r"\bbrbpr\b", "bright red blood per rectum"),
    (r"\bhcc\b", "hepatocellular carcinoma"),
    (r"\bhcv\b", "hepatitis C virus"),
    (r"\bckd\b", "chronic kidney disease"),
    (r"\bdm\b", "diabetes mellitus"),
    (r"\bmrsa\b", "methicillin-resistant Staphylococcus aureus"),
    (r"\bmssa\b", "methicillin-susceptible Staphylococcus aureus"),
    (r"\bcns\b", "central nervous system"),
    (r"\bitp\b", "immune thrombocytopenia"),
    (r"\btma\b", "thrombotic microangiopathy"),
    (r"\bcll\b", "chronic lymphocytic leukemia"),
    (r"\bdlbcl\b", "diffuse large B-cell lymphoma"),
    (r"\bpea\b", "pulseless electrical activity"),
    (r"\bmi\b", "myocardial infarction"),
    (r"\bpe\b", "pulmonary embolism"),
    (r"\bvt\b", "ventricular tachycardia"),
    (r"\bvf\b", "ventricular fibrillation"),
    (r"\bsvts\b", "supraventricular tachycardias"),
    (r"\bsvt\b", "supraventricular tachycardia"),
    (r"\bnsr\b", "normal sinus rhythm"),
    (r"\bsdhs\b", "subdural hematomas"),
    (r"\bsdh\b", "subdural hematoma"),
    (r"\bsah\b", "subarachnoid hemorrhage"),
    (r"\bich\b", "intracerebral hemorrhage"),
    (r"\biph\b", "intraparenchymal hemorrhage"),
    (r"\bnka\b", "no known allergies"),
    (r"\bnkda\b", "no known drug allergies"),
    (r"\bsob\b", "shortness of breath"),
    (r"\bs\.o\.b\.?\b", "shortness of breath"),
    (r"\bdoe\b", "dyspnea on exertion"),
    (r"\bams\b", "altered mental status"),
    (r"\bloc\b", "loss of consciousness"),
    (r"\bcp\b", "chest pain"),
    (r"\bc\.p\.?\b", "chest pain"),
    (r"\bha\b", "headache"),
    (r"\babnl\b", "abnormal"),
    (r"\babdo\b", "abdominal"),
    (r"\babd\b", "abdominal"),
    (r"\bgi\b", "gastrointestinal"),
    (r"\bfx\b", "fracture"),
    (r"\bsz\b", "seizure"),
    (r"\bod\b", "overdose"),
    (r"\bsi\b(?!\s+joint)", "suicidal ideation"),
    (r"\beval\b", "evaluation"),
    (r"\bresp\b", "respiratory"),
    (r"\btib\b", "tibia"),
    (r"\bfib\b", "fibula"),
    (r"\btrop\b", "troponin"),
    (r"\bhct\b", "hematocrit"),
    (r"\binr\b", "international normalized ratio"),
    (r"\bbp\b", "blood pressure"),
    (r"\bpo\b", "oral"),
    (r"\bmtx\b", "methotrexate"),
    (r"\bxrt\b", "radiation therapy"),
    # Procedures / devices / units
    (r"\bosh\b", "outside hospital"),
    (r"\blfts\b", "liver function tests"),
    (r"\blft\b", "liver function test"),
    (r"\bftt\b", "failure to thrive"),
    (r"\btace\b", "transarterial chemoembolization"),
    (r"\bercp\b", "endoscopic retrograde cholangiopancreatography"),
    (r"\bmvc\b", "motor vehicle collision"),
    (r"\bmva\b", "motor vehicle accident"),
    (r"\biabp\b", "intra-aortic balloon pump"),
    (r"\btavr\b", "transcatheter aortic valve replacement"),
    (r"\begd\b", "esophagogastroduodenoscopy"),
    (r"\beeg\b", "electroencephalogram"),
    (r"\becg\b", "electrocardiogram"),
    (r"\bekg\b", "electrocardiogram"),
    (r"\bct\s+scan\b", "computed tomography scan"),
    (r"\bct\b", "computed tomography"),
    (r"\bmri\b", "magnetic resonance imaging"),
    (r"\bcxr\b", "chest radiograph"),
    (r"\baki\b", "acute kidney injury"),
    (r"\bards\b", "acute respiratory distress syndrome"),
    (r"\bappy\b", "appendectomy"),
    (r"\bmicu\b", "medical intensive care unit"),
    (r"\bicu\b", "intensive care unit"),
    (r"\bicd\b", "implantable cardioverter-defibrillator"),
    (r"\bpicc\b", "peripherally inserted central catheter"),
    (r"\bpeg\b", "percutaneous endoscopic gastrostomy"),
    (r"\bppm\b", "permanent pacemaker"),
    (r"\bavf\b", "arteriovenous fistula"),
    (r"\btips\b", "transjugular intrahepatic portosystemic shunt"),
    (r"\bmca\b", "middle cerebral artery"),
    (r"\bica\b", "internal carotid artery"),
    (r"\bems\b", "emergency medical services"),
    (r"\bpmh\b", "past medical history"),
    (r"\bhpi\b", "history of present illness"),
    (r"\bros\b", "review of systems"),
    (r"\bcc:\s*", "chief complaint: "),
)

_COMPILED = [(re.compile(pattern), replacement) for pattern, replacement in _REPLACEMENTS]


def expand_ehr_abbreviations(text: str) -> str:
    collapsed = collapse_ws(text)
    if not collapsed:
        return ""
    expanded = collapsed.casefold()
    for pattern, replacement in _COMPILED:
        expanded = pattern.sub(replacement, expanded)
    return collapse_ws(expanded) or ""


def sentence_case_expanded(text: str) -> str:
    collapsed = collapse_ws(text)
    if not collapsed:
        return ""
    if collapsed[0].islower():
        return collapsed[0].upper() + collapsed[1:]
    return collapsed


def expand_for_display(text: str) -> str:
    return sentence_case_expanded(expand_ehr_abbreviations(text))
