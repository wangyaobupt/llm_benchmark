CHIEF_COMPLAINT_PROMPT = """Extract atomic chief-complaint entities from one clinical chief complaint.

Return exactly {"entities":["entity one","entity two"]}.

Rules:
- Use only the chief_complaint text.
- Include each explicitly stated reason for the current visit or admission,
  including a symptom, sign, clinical state, disease, injury, abnormal finding,
  event, or planned procedure reason.
- An atomic entity is one self-contained clinical concept, not necessarily one
  word. Split lists only when each result is independently meaningful.
- Keep anatomical site, laterality, uncertainty, and clinically meaningful
  qualifiers attached to the entity they modify. Remove framing, conjunctions,
  numbering, and standalone time expressions.
- Exclude explicitly negated entities.
- Never output a standalone modifier.
- Preserve source wording. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize terms.
- Deduplicate after trimming and collapsing whitespace and comparing English
  letters case-insensitively; preserve the first expression.
- Return an empty array when no entity qualifies. Return JSON only, with no
  explanation, evidence, categories, markdown, or original sentence.

Example:
Input: {"chief_complaint":"Worsening right foot pain and swelling for three days; no fever"}
Output: {"entities":["Worsening right foot pain","right foot swelling"]}

Input: {"chief_complaint":"Possible seizure, cardiogenic ___"}
Output: {"entities":["Possible seizure"]}"""


HISTORY_OF_PRESENT_ILLNESS_PROMPT = """Extract atomic current clinical entities from one history of present illness.

Return exactly {"entities":["entity one","entity two"]}.

Rules:
- Use only the history_of_present_illness text.
- Include explicitly stated current symptoms, signs, clinical states, diseases,
  injuries, abnormal findings, and relevant events.
- An atomic entity is one self-contained clinical concept, not the shortest
  phrase. Split lists only when each result is independently meaningful.
- Never output a standalone site, severity, course, timing, trigger, relieving
  factor, radiation direction, or other modifier. Keep it attached to the
  clinical entity it describes.
- First identify the current presentation. A condition introduced as history of,
  known for, with a history of, or status post is background even when it occurs
  in the same sentence as the current illness.
- Exclude background conditions, family history, medications, and every past,
  performed, or planned treatment, operation, procedure, or postoperative action.
- Exclude diagnostic test names and every normal or negative finding. A current
  abnormal finding explicitly stated by a test may be kept without the test name
  and with its uncertainty wording; never infer a diagnosis or abnormality.
- Do not output an isolated test value unless the source explicitly describes it
  as an abnormal or clinically significant current finding.
- Exclude explicitly negated entities. Keep uncertainty only for a qualifying
  current entity.
- Preserve source wording. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize terms.
- Deduplicate after trimming and collapsing whitespace and comparing English
  letters case-insensitively; preserve the first expression.
- Return an empty array when no entity qualifies. Return JSON only, with no
  explanation, evidence, categories, markdown, or original sentences.

Example:
Input: {"history_of_present_illness":"History of COPD. She has worsening abdominal pain (constant, epigastric and radiates to back), nausea, and no fever. Treated with IV fluids."}
Output: {"entities":["worsening abdominal pain (constant, epigastric and radiates to back)","nausea"]}

Input: {"history_of_present_illness":"Patient with AF, CAD and COPD presents for elective hernia repair. CXR was negative for acute process. The hernia contains incarcerated sigmoid colon."}
Output: {"entities":["incarcerated sigmoid colon"]}"""


PAST_MEDICAL_HISTORY_PROMPT = """Extract atomic past clinical entities from one past medical history.

Return exactly {"entities":["entity one","entity two"]}.

Rules:
- Use only the past_medical_history text.
- Include diseases, chronic conditions, complications, prior injuries, prior
  surgeries, and prior invasive procedures that existed before admission.
- An atomic entity is one self-contained clinical concept. Split lists only when
  each result is independently meaningful.
- Exclude current complaints or diseases, family history, social behaviors and
  exposures, medications, tests, non-procedural treatments, and future plans.
  Include a substance-related condition only when explicitly stated as a
  clinical diagnosis, not as mere use or exposure.
- Prior surgery and invasive procedures qualify; chemotherapy, radiotherapy,
  rehabilitation, and medication courses do not.
- Remove history framing such as history of, h/o, status post, and s/p while
  keeping the clinical entity that follows it.
- Exclude explicitly negated entities. Keep uncertainty only for a qualifying
  past entity.
- Preserve source wording. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize terms.
- Deduplicate after trimming and collapsing whitespace and comparing English
  letters case-insensitively; preserve the first expression.
- Treat None, No past medical history, Unknown, and Unable to obtain as empty.
  Return JSON only, with no explanation, evidence, categories, or markdown.

Example:
Input: {"past_medical_history":"Hypertension; h/o breast ca; s/p right lumpectomy; tobacco use"}
Output: {"entities":["Hypertension","breast ca","right lumpectomy"]}

Input: {"past_medical_history":"Craniotomy, irradiation to 6,120 cGy, 3 cycles of Temodar, depression"}
Output: {"entities":["Craniotomy","depression"]}"""


MEDICATIONS_ON_ADMISSION_PROMPT = """Extract medication-name entities from one medications-on-admission text.

Return exactly {"entities":["medication one","medication two"]}.

Rules:
- Use only the medications_on_admission text.
- Include prescription and over-the-counter medications, vitamins, supplements,
  and PRN medications taken before or at admission.
- Return medication names only. Remove doses, strengths, concentrations, units,
  routes, frequencies, dates, conditions, PRN indications, numbering, and list
  boilerplate before deduplication.
- Keep parenthetical text only when it is a brand, generic name, or ingredient
  expression. Remove parenthetical strengths, dose ratios, routes, and frequency
  descriptions.
- Preserve a number only when it is intrinsic to the medication name, such as
  HumuLIN 70/30, Vitamin D3, or CoQ10.
- A trailing number or numeric ratio is a strength even without a unit or space.
  Remove it unless it is an intrinsic medication name such as HumuLIN 70/30.
- Keep a combination product as one entity; do not split active ingredients.
- Include an explicit medication even when its dose is unknown or the source
  list may be inaccurate.
- Exclude medications described as not taken, stopped, discontinued, completed,
  or planned only for future use. Exclude allergies and non-medication content.
- Preserve source naming. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize names.
- Deduplicate cleaned names after trimming and collapsing whitespace and
  comparing English letters case-insensitively; preserve the first expression.
- Treat None, No medications, Unknown, and Unable to obtain as empty. Return JSON only,
  with no explanation, evidence, categories, markdown, or original text.

Example:
Input: {"medications_on_admission":"venlafaxine hcl er 30; Advair250/50; HumuLIN 70/30"}
Output: {"entities":["venlafaxine hcl er","Advair","HumuLIN 70/30"]}

Input: {"medications_on_admission":"PredniSONE 30 mg, then 20 mg, then 10 mg; BuPROPion XL (Once Daily)"}
Output: {"entities":["PredniSONE","BuPROPion XL"]}"""


PROMPTS = {
    "chief_complaint": CHIEF_COMPLAINT_PROMPT,
    "history_of_present_illness": HISTORY_OF_PRESENT_ILLNESS_PROMPT,
    "past_medical_history": PAST_MEDICAL_HISTORY_PROMPT,
    "medications_on_admission": MEDICATIONS_ON_ADMISSION_PROMPT,
}
