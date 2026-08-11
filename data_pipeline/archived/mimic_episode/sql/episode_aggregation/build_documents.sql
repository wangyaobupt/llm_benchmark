CREATE OR REPLACE TEMP VIEW note_rows AS
SELECT
    note_id,
    TRY_CAST(subject_id AS BIGINT) AS subject_id,
    TRY_CAST(hadm_id AS BIGINT) AS native_hadm_id,
    note_type,
    TRY_CAST(note_seq AS INTEGER) AS note_seq,
    TRY_CAST(charttime AS TIMESTAMP) AS event_time,
    TRY_CAST(storetime AS TIMESTAMP) AS available_time,
    TRY_CAST(storetime AS TIMESTAMP) AS recorded_time,
    text,
    'discharge' AS document_type,
    'mimic-iv-note-2.2/note/discharge' AS source_table,
    '2.2' AS source_version
FROM raw_discharge

UNION ALL

SELECT
    note_id,
    TRY_CAST(subject_id AS BIGINT),
    TRY_CAST(hadm_id AS BIGINT),
    note_type,
    TRY_CAST(note_seq AS INTEGER),
    TRY_CAST(charttime AS TIMESTAMP),
    TRY_CAST(storetime AS TIMESTAMP),
    TRY_CAST(storetime AS TIMESTAMP),
    text,
    'radiology',
    'mimic-iv-note-2.2/note/radiology',
    '2.2'
FROM raw_radiology;

CREATE OR REPLACE TEMP VIEW note_detail_relations AS
WITH details AS (
    SELECT
        note_id,
        TRY_CAST(subject_id AS BIGINT) AS subject_id,
        field_name,
        field_value
    FROM raw_discharge_detail

    UNION ALL

    SELECT
        note_id,
        TRY_CAST(subject_id AS BIGINT),
        field_name,
        field_value
    FROM raw_radiology_detail
)
SELECT
    note_id,
    subject_id,
    MAX(field_value) FILTER (WHERE field_name = 'parent_note_id') AS parent_note_id,
    MAX(field_value) FILTER (WHERE field_name = 'addendum_note_id') AS addendum_note_id
FROM details
GROUP BY note_id, subject_id;

CREATE OR REPLACE TEMP VIEW note_temporal_candidates AS
SELECT
    n.note_id,
    COUNT(DISTINCT e.episode_id) AS candidate_episode_count,
    MIN(e.episode_id) AS candidate_episode_id
FROM note_rows n
INNER JOIN episode_index e
    ON e.subject_id = n.subject_id
   AND n.event_time BETWEEN e.episode_start_time AND e.administrative_end_time
WHERE n.native_hadm_id IS NULL
GROUP BY n.note_id;

CREATE OR REPLACE TEMP VIEW documents AS
WITH linked AS (
    SELECT
        n.*,
        a.hadm_id AS matched_hadm_id,
        a.subject_id AS admission_subject_id,
        t.candidate_episode_count,
        t.candidate_episode_id,
        r.parent_note_id,
        r.addendum_note_id
    FROM note_rows n
    LEFT JOIN typed_admissions a ON a.hadm_id = n.native_hadm_id
    LEFT JOIN note_temporal_candidates t ON t.note_id = n.note_id
    LEFT JOIN note_detail_relations r
        ON r.note_id = n.note_id
       AND r.subject_id = n.subject_id
)
SELECT
    note_id,
    subject_id,
    CASE
        WHEN native_hadm_id IS NOT NULL
         AND matched_hadm_id IS NOT NULL
         AND admission_subject_id = subject_id
        THEN 'H:' || CAST(native_hadm_id AS VARCHAR)
        WHEN native_hadm_id IS NULL AND candidate_episode_count = 1
        THEN candidate_episode_id
        ELSE NULL
    END AS episode_id,
    NULL::VARCHAR AS contact_id,
    document_type,
    note_type,
    note_seq,
    event_time,
    available_time,
    recorded_time,
    'timestamp' AS time_precision,
    text,
    parent_note_id,
    addendum_note_id,
    CASE
        WHEN native_hadm_id IS NOT NULL
         AND matched_hadm_id IS NOT NULL
         AND admission_subject_id = subject_id
        THEN 'native_link'
        WHEN native_hadm_id IS NULL AND candidate_episode_count = 1
        THEN 'unique_temporal_link'
        ELSE 'unresolved'
    END AS link_status,
    CASE
        WHEN native_hadm_id IS NOT NULL AND matched_hadm_id IS NULL
        THEN 'hadm_not_found'
        WHEN native_hadm_id IS NOT NULL AND admission_subject_id <> subject_id
        THEN 'subject_hadm_mismatch'
        WHEN native_hadm_id IS NULL AND COALESCE(candidate_episode_count, 0) = 0
        THEN 'no_temporal_episode'
        WHEN native_hadm_id IS NULL AND candidate_episode_count > 1
        THEN 'multiple_temporal_episodes'
        ELSE NULL
    END AS unresolved_reason,
    native_hadm_id,
    COALESCE(candidate_episode_count, 0) AS candidate_episode_count,
    source_table,
    source_version
FROM linked;
