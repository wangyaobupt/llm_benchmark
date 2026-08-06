CREATE OR REPLACE TEMP VIEW note_documents AS
WITH notes AS (
    SELECT 'discharge' AS document_type, * FROM discharge_raw
    UNION ALL
    SELECT 'radiology' AS document_type, * FROM radiology_raw
), linked AS (
    SELECT
        n.*,
        p.subject_id IS NOT NULL AS subject_in_core,
        a.hadm_id IS NOT NULL AS hadm_in_core,
        a.subject_id AS admission_subject_id,
        a.admittime,
        a.dischtime
    FROM notes n
    LEFT JOIN core_patients p ON p.subject_id = n.subject_id
    LEFT JOIN core_admissions a ON a.hadm_id = n.hadm_id
)
SELECT
    note_id,
    subject_id,
    hadm_id,
    document_type,
    note_type,
    note_seq,
    charttime,
    storetime,
    COALESCE(storetime, charttime) AS available_time,
    text,
    CASE document_type
        WHEN 'discharge' THEN 'mimic-iv-note-2.2/note/discharge'
        ELSE 'mimic-iv-note-2.2/note/radiology'
    END AS source_table,
    '2.2' AS source_version,
    subject_in_core,
    hadm_in_core,
    COALESCE(admission_subject_id = subject_id, FALSE) AS admission_subject_matches,
    CASE
        WHEN NOT subject_in_core THEN 'subject_not_in_core'
        WHEN hadm_id IS NULL THEN 'patient_level_only'
        WHEN NOT hadm_in_core THEN 'hadm_not_in_core'
        WHEN admission_subject_id <> subject_id THEN 'subject_hadm_mismatch'
        ELSE 'matched'
    END AS link_status,
    CASE
        WHEN hadm_in_core AND admission_subject_id = subject_id
        THEN charttime BETWEEN admittime AND dischtime
        ELSE FALSE
    END AS is_charttime_in_admission,
    CASE
        WHEN hadm_in_core AND admission_subject_id = subject_id
        THEN COALESCE(storetime, charttime) BETWEEN admittime AND dischtime
        ELSE FALSE
    END AS is_available_in_admission,
    CASE
        WHEN hash('mimic-benchmark-split-v1:' || CAST(subject_id AS VARCHAR)) % 100 < 80 THEN 'train'
        WHEN hash('mimic-benchmark-split-v1:' || CAST(subject_id AS VARCHAR)) % 100 < 90 THEN 'validate'
        ELSE 'test'
    END AS split
FROM linked;

CREATE OR REPLACE TEMP VIEW note_details AS
WITH details AS (
    SELECT 'discharge' AS note_type, * FROM discharge_detail_raw
    UNION ALL
    SELECT 'radiology' AS note_type, * FROM radiology_detail_raw
), linked AS (
    SELECT
        d.*,
        n.note_id AS matched_note_id,
        n.subject_id AS note_subject_id
    FROM details d
    LEFT JOIN note_documents n
        ON n.document_type = d.note_type
       AND n.note_id = d.note_id
)
SELECT
    note_id,
    subject_id,
    note_type,
    field_name,
    field_value,
    field_ordinal,
    CASE
        WHEN matched_note_id IS NULL THEN 'note_id_not_found'
        WHEN note_subject_id <> subject_id THEN 'subject_note_mismatch'
        ELSE 'matched'
    END AS detail_join_status,
    'mimic-iv-note-2.2/note/' || note_type || '_detail' AS source_table,
    '2.2' AS source_version
FROM linked;

CREATE OR REPLACE TEMP VIEW valid_edstays AS
SELECT
    e.*,
    t.chiefcomplaint,
    CASE
        WHEN p.subject_id IS NULL THEN 'subject_not_in_core'
        WHEN e.hadm_id IS NULL THEN 'patient_level_only'
        WHEN a.hadm_id IS NULL THEN 'hadm_not_in_core'
        WHEN a.subject_id <> e.subject_id THEN 'subject_hadm_mismatch'
        ELSE 'matched'
    END AS link_status
FROM edstays_raw e
LEFT JOIN triage_raw t
    ON t.subject_id = e.subject_id
   AND t.stay_id = e.stay_id
LEFT JOIN core_patients p ON p.subject_id = e.subject_id
LEFT JOIN core_admissions a ON a.hadm_id = e.hadm_id;

CREATE OR REPLACE TEMP VIEW case_index AS
WITH ranked_discharge AS (
    SELECT
        n.*,
        a.admittime,
        a.dischtime,
        ROW_NUMBER() OVER (
            PARTITION BY n.subject_id, n.hadm_id
            ORDER BY n.charttime DESC NULLS LAST, n.storetime DESC NULLS LAST, n.note_id
        ) AS note_rank,
        COUNT(*) OVER (PARTITION BY n.subject_id, n.hadm_id) AS discharge_note_count
    FROM note_documents n
    INNER JOIN core_admissions a
        ON a.subject_id = n.subject_id
       AND a.hadm_id = n.hadm_id
    WHERE n.document_type = 'discharge'
      AND n.link_status = 'matched'
), radiology_counts AS (
    SELECT subject_id, hadm_id, COUNT(*) AS radiology_note_count
    FROM note_documents
    WHERE document_type = 'radiology'
      AND link_status = 'matched'
      AND is_charttime_in_admission
    GROUP BY subject_id, hadm_id
), ranked_ed AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY subject_id, hadm_id
            ORDER BY intime, stay_id
        ) AS stay_rank
    FROM valid_edstays
    WHERE link_status = 'matched'
)
SELECT
    d.subject_id,
    d.hadm_id,
    d.admittime,
    d.dischtime,
    d.note_id AS discharge_note_id,
    d.charttime AS discharge_charttime,
    d.available_time AS discharge_available_time,
    d.is_available_in_admission AS discharge_available_by_discharge,
    d.discharge_note_count,
    COALESCE(r.radiology_note_count, 0) AS radiology_note_count,
    e.stay_id AS ed_stay_id,
    COALESCE(TRIM(e.chiefcomplaint), '') <> '' AS has_chiefcomplaint,
    d.split
FROM ranked_discharge d
LEFT JOIN radiology_counts r
    ON r.subject_id = d.subject_id
   AND r.hadm_id = d.hadm_id
LEFT JOIN ranked_ed e
    ON e.subject_id = d.subject_id
   AND e.hadm_id = d.hadm_id
   AND e.stay_rank = 1
WHERE d.note_rank = 1;
