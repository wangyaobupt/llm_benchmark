CREATE OR REPLACE TEMP VIEW note_detail_rows AS
SELECT
    note_id,
    subject_id,
    field_name,
    field_value,
    field_ordinal,
    'mimic-iv-note-2.2/note/discharge_detail' AS source_table
FROM raw_discharge_detail
UNION ALL
SELECT
    note_id,
    subject_id,
    field_name,
    field_value,
    field_ordinal,
    'mimic-iv-note-2.2/note/radiology_detail'
FROM raw_radiology_detail;

CREATE OR REPLACE TEMP VIEW triage_counts_source AS
SELECT
    c.episode_id,
    COUNT(*) FILTER (
        WHERE COALESCE(TRIM(t.chiefcomplaint), '') <> ''
    ) AS chief_complaint_count,
    COUNT(*) FILTER (
        WHERE t.temperature IS NOT NULL
           OR t.heartrate IS NOT NULL
           OR t.resprate IS NOT NULL
           OR t.o2sat IS NOT NULL
           OR t.sbp IS NOT NULL
           OR t.dbp IS NOT NULL
    ) AS triage_vital_count
FROM raw_triage t
INNER JOIN care_contacts c
    ON c.contact_id = 'ED:' || t.stay_id
   AND c.subject_id = TRY_CAST(t.subject_id AS BIGINT)
GROUP BY c.episode_id;

CREATE OR REPLACE TEMP VIEW disposition_counts_source AS
SELECT
    episode_id,
    COUNT(*) FILTER (WHERE disposition IS NOT NULL) AS disposition_count
FROM classified_edstays
GROUP BY episode_id;
