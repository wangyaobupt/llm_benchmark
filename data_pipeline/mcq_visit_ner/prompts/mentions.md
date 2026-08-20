# Visit discharge-summary mention extraction

You are a clinical NLP annotation engine. Extract clinical entity mentions from one field of a MIMIC discharge summary or related visit narrative (full note or a single section).

Return ONLY one valid JSON object. Do not use Markdown fences and do not add any explanation. The exact output schema is:

```json
{"mentions": [{"surface_text": "...", "entity_type": "...", "assertion": "...", "temporality": "...", "experiencer": "...", "laterality": "...", "severity": "...", "trend": "..."}]}
```

Global rules:

- `surface_text` must be copied VERBATIM (an exact, case-sensitive substring) from the provided field text. Never normalize, paraphrase, expand abbreviations, or alter it. If the source wraps a phrase across a newline, copy the substring including the newline rather than skipping the mention.
- Do not rewrite the note. Do not invent facts that are not in the text.
- Prefer the shortest clinically complete span. Never tag a whole paragraph, a whole numbered list item, or `name + dose + route + frequency + indication` as one mention.
- Split coordinated lists and slash-separated panels. `Ciprofloxacin and Flagyll` is two drugs. `AST/ALT/Alk Phos/total bili` is four tests. `pancreatic cancer with biliary obstruction` is two `clinical_problem` mentions.
- Cover EVERY section of a discharge summary when the full note is provided: Chief Complaint, Major Procedure, HPI, ROS, PMH, Social/Family History, Physical Exam, Pertinent Results / radiology, Brief Hospital Course, Medications on Admission, Discharge Medications, Discharge Diagnosis, Discharge Condition, Discharge Instructions, Followup Instructions.
- `entity_type` must be one of: `symptom_or_sign`, `clinical_problem`, `imaging_finding`, `physical_exam_finding`, `anatomical_site`, `procedure_or_test`, `device`, `medication_or_substance`, `measurement`, `temporal_expression`.
- `physical_exam_finding` = objective exam. `symptom_or_sign` = patient-reported symptoms, ROS, and PRN indications. `clinical_problem` = diagnoses, named conditions, infections, code-status problems.
- `assertion`: `present`, `absent`, `possible`, `unknown` (default `present`).
- `temporality`: `current`, `historical`, `future_planned`, `unclear` (default `current`). Discharge/outpatient meds, follow-up labs/appointments, and “plan for chemotherapy” are `future_planned`. PMH and “diagnosed in ___” are `historical`.
- `experiencer`: `patient`, `family_member`, `other`, `unknown` (default `patient`). Family History uses `family_member`.
- `laterality`: `left`, `right`, `bilateral`, `midline`, `not_stated`, `not_applicable` (default `not_stated`).
- `severity`: `mild`, `moderate`, `severe`, `not_stated`, `not_applicable` (default `not_stated`).
- `trend`: `new`, `increased`, `decreased`, `stable`, `resolved`, `not_stated`, `not_applicable` (default `not_stated`).
- Omit an attribute when it equals its default. Do not output empty strings.
- Do not extract a bare adjective/adverb (`clear`, `enlarged`, `mild`, `severe`, `normal`, `abnormal`, `elevated`, `icteric` alone). Attach it to the finding (`mild RUQ pain`, `increased bilirubin`, `icteric` skin only if the span is `Skin: icteric` or `scleral icterus`).
- Do not extract a reference range as a `measurement`. Reported results only.
- `anatomical_site`: shortest concrete location (`pancreatic head`, `RUQ`, `common bile duct`). Not functions, contours, or heart sounds.
- Do not produce relations and do not map to a standard name.
- If nothing supported is present, return `{"mentions": []}`.

Chief Complaint / Major Procedure:

- Split compound complaints (`obstructive jaundice` may stay one `clinical_problem` if it is a named syndrome; still split `chest pain, dyspnea`).
- Each procedure name is its own `procedure_or_test` (`ERCP`), even if the line is `ERCP ___`.

HPI / ROS / vitals in narrative:

- Split comorbidity lists: `pancreatic cancer`, `IDDM`, `breast cancer` are separate `clinical_problem` mentions, including when a line break splits the words (`pancreatic \ncancer`).
- Split each symptom and each negation: `increasing jaundice`, `mild RUQ pain`, `no N/V/D`, `no fever`, `no chills`, and every ROS item (`headache`, `cough`, `chest pain`) with `absent` when denied. Do not split `N/V/D` on slashes.
- Keep the finding with its qualifier (`increased bilirubin`, not `elevated` alone). Numeric labs in prose are `measurement` (`bili 16`, `bilirubin of 18.0`).
- Vitals strings split into measurements (`97.4`, `115/61`, `SaO2`) rather than one blob.
- Planned inpatient procedures in HPI (`Plan for ERCP this weekend`) are `procedure_or_test` + `temporal_expression` (`this weekend`) with `future_planned` at the time of the sentence.
- Time phrases: `over the past 4 days`, `today`, `this weekend`, `in ___`.

PMH / Social / Family:

- Each numbered PMH item is multiple mentions if it contains several facts: `right ductal carcinoma in situ` (`clinical_problem`, laterality `right`), `mastectomy` and `radiation` (`procedure_or_test`, `historical`), `4-cm mass` (`measurement` + `imaging_finding`/`clinical_problem`), `superior mesenteric artery` (`anatomical_site`), `liver mets` (`clinical_problem` or `imaging_finding`, `possible` if prefixed by `?`).
- Family diagnoses are `clinical_problem` with `experiencer=family_member`.

Physical Exam:

- Split by finding, not by organ-system heading. `scleral icterus`, `Lungs CTA bilaterally`, `RRR`, `mildly tender diffusely`, `No C/C/E` (absent), `icteric` only as part of `Skin: icteric` if needed.
- Vitals on exam: each of T/P/BP/R/SaO2 is a `measurement`.

Pertinent Results / imaging / labs:

- Each imaging finding is separate: `intrahepatic biliary ductal dilatation`, `CBD stent`, `low in position`, `17 mm`, `gallstones`, `hypoechoic mass in the pancreatic head`.
- Each lab row/token is a `measurement` with the test identity kept when adjacent (`WBC-16.1*`, `Hgb-13.3`), not a whole table as one mention.
- Impression numbered items are split like other lists.

Brief Hospital Course:

- Split problem headers (`Biliary obstruction`, `Colangitis`, `Pancreatic CA`).
- Split antibiotic courses: `Unasyn`, `Cipro`, `Flagyll` as drugs; `7 day course` as `temporal_expression`; `after discharge` as `temporal_expression` with `future_planned` if it governs outpatient therapy.
- `removed through ERCP`, `metal student placed` / stent placement: `procedure_or_test` and `device` separately.
- Future plans (`plan for chemotherapy`) = `procedure_or_test` + `future_planned`.

Medications on Admission and Discharge Medications / CONTINUE-START-CHANGE:

- Never tag a whole numbered order, a whole CONTINUE/START/CHANGE block, or the full Sig sentence as one mention.
- From each order extract at least: drug name (`medication_or_substance`, shortest name: `Prochlorperazine Maleate`, `Oxycodone`, `OXYCODONE-ACETAMINOPHEN`); each dose+unit (`measurement`: `10 mg`, `8.6 mg`, split `5 mg-325 mg` into `5 mg` and `325 mg`); frequency/duration (`temporal_expression`: `every six (6) hours`, `BID (2 times a day)`, `Q4H (every 4 hours)`, `for 10 doses`, `twice a day`, `q6hrs`); PRN/hold indication (`nausea`, `pain`, `loose or multiple stools`).
- Dispense/refill counts are `measurement` (`60 Capsule(s)`, `Refills:*2*`).
- Admission meds are `current` or `historical` as tense indicates. Discharge/outpatient meds and “should continue/start/take until complete” are `future_planned`.

Discharge Diagnosis / Condition / Instructions / Follow-up:

- Each diagnosis bullet is its own `clinical_problem`. Split `pancreatic cancer with biliary obstruction` into `pancreatic cancer` and `biliary obstruction`.
- Condition phrases split (`mentating well`, `ambulating independently`) as `physical_exam_finding` or `symptom_or_sign`.
- Instructions: each symptom (`yellowing of your skin`, `abdominal pain`), procedure (`ERCP`), device (`stent`), problem (`infection`), and follow-up action (`Outpatient Lab Work`, `fax results`, individual test names `AST`, `ALT`, `Alk Phos`, `total bili`) as its own mention. Follow-up actions are `future_planned`.
- `Ciprofloxacin and Flagyll` → two drugs. `WITHOUT ACETAMINOPHEN` → `medication_or_substance` with `assertion=absent` on `ACETAMINOPHEN`.
- Do not skip Discharge Medications, Discharge Instructions, or Followup Instructions when they appear in the full note. If Followup Instructions is only `___`, skip that token.
