CREATE OR REPLACE TEMP TABLE quality_metrics (
    section VARCHAR NOT NULL,
    dataset VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    value BIGINT NOT NULL
);

CREATE OR REPLACE TEMP VIEW exported_case_index AS
SELECT * FROM read_parquet($case_index_path);

CREATE OR REPLACE TEMP VIEW exported_text_documents AS
SELECT * FROM read_parquet($text_documents_path);

CREATE OR REPLACE TEMP VIEW exported_note_details AS
SELECT * FROM read_parquet($note_details_path);

INSERT INTO quality_metrics
SELECT 'core', 'patients', 'rows', COUNT(*) FROM core_patients;

INSERT INTO quality_metrics
SELECT 'core', 'admissions', 'rows', COUNT(*) FROM core_admissions;

INSERT INTO quality_metrics
WITH note_counts AS (
    SELECT
        document_type,
        COUNT(*) AS rows,
        COUNT(DISTINCT subject_id) AS unique_subjects,
        COUNT(*) FILTER (WHERE hadm_id IS NULL) AS missing_hadm_id,
        COUNT(*) FILTER (WHERE NOT subject_in_core) AS subject_not_in_core,
        COUNT(*) FILTER (WHERE link_status = 'matched') AS matched_admission,
        COUNT(DISTINCT hadm_id) FILTER (WHERE link_status = 'matched') AS matched_unique_hadm,
        COUNT(*) FILTER (WHERE hadm_id IS NOT NULL AND NOT hadm_in_core) AS hadm_not_in_core,
        COUNT(*) FILTER (WHERE link_status = 'subject_hadm_mismatch') AS subject_hadm_mismatch,
        COUNT(*) FILTER (WHERE is_charttime_in_admission) AS charttime_in_admission,
        COUNT(*) FILTER (WHERE is_available_in_admission) AS available_in_admission
    FROM exported_text_documents
    GROUP BY document_type
)
SELECT 'notes', document_type, metric, value
FROM note_counts
CROSS JOIN LATERAL (
    VALUES
        ('rows', rows),
        ('unique_subjects', unique_subjects),
        ('missing_hadm_id', missing_hadm_id),
        ('subject_not_in_core', subject_not_in_core),
        ('matched_admission', matched_admission),
        ('matched_unique_hadm', matched_unique_hadm),
        ('hadm_not_in_core', hadm_not_in_core),
        ('subject_hadm_mismatch', subject_hadm_mismatch),
        ('charttime_in_admission', charttime_in_admission),
        ('available_in_admission', available_in_admission)
) AS metrics(metric, value);

INSERT INTO quality_metrics
WITH note_counts AS (
    SELECT
        COUNT(DISTINCT subject_id) AS unique_subjects,
        COUNT(DISTINCT subject_id) FILTER (WHERE subject_in_core) AS subjects_in_core,
        COUNT(DISTINCT hadm_id) FILTER (WHERE link_status = 'matched') AS matched_unique_hadm
    FROM exported_text_documents
)
SELECT 'notes', 'all', metric, value
FROM note_counts
CROSS JOIN LATERAL (
    VALUES
        ('unique_subjects', unique_subjects),
        ('subjects_in_core', subjects_in_core),
        ('matched_unique_hadm', matched_unique_hadm)
) AS metrics(metric, value);

INSERT INTO quality_metrics
WITH ed_counts AS (
    SELECT
        COUNT(*) AS rows,
        COUNT(DISTINCT subject_id) AS unique_subjects,
        COUNT(*) FILTER (WHERE hadm_id IS NULL) AS missing_hadm_id,
        COUNT(*) FILTER (WHERE link_status = 'matched') AS matched_admission,
        COUNT(DISTINCT hadm_id) FILTER (WHERE link_status = 'matched') AS matched_unique_hadm
    FROM valid_edstays
)
SELECT 'ed', 'edstays', metric, value
FROM ed_counts
CROSS JOIN LATERAL (
    VALUES
        ('rows', rows),
        ('unique_subjects', unique_subjects),
        ('missing_hadm_id', missing_hadm_id),
        ('matched_admission', matched_admission),
        ('matched_unique_hadm', matched_unique_hadm)
) AS metrics(metric, value);

INSERT INTO quality_metrics
SELECT 'ed', 'triage', 'rows', COUNT(*) FROM triage_raw;

INSERT INTO quality_metrics
SELECT
    'ed',
    'triage',
    'chiefcomplaint_nonempty',
    COUNT(*) FILTER (WHERE COALESCE(TRIM(chiefcomplaint), '') <> '')
FROM triage_raw;

INSERT INTO quality_metrics
WITH detail_counts AS (
    SELECT
        note_type,
        COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE detail_join_status = 'matched') AS matched,
        COUNT(*) FILTER (WHERE detail_join_status = 'note_id_not_found') AS note_id_not_found,
        COUNT(*) FILTER (WHERE detail_join_status = 'subject_note_mismatch') AS subject_note_mismatch
    FROM exported_note_details
    GROUP BY note_type
)
SELECT 'details', note_type, metric, value
FROM detail_counts
CROSS JOIN LATERAL (
    VALUES
        ('rows', rows),
        ('matched', matched),
        ('note_id_not_found', note_id_not_found),
        ('subject_note_mismatch', subject_note_mismatch)
) AS metrics(metric, value);

INSERT INTO quality_metrics
SELECT 'outputs', 'case_index', 'rows', COUNT(*) FROM exported_case_index;

INSERT INTO quality_metrics
SELECT 'outputs', 'text_documents', 'rows', COUNT(*) FROM exported_text_documents;

INSERT INTO quality_metrics
SELECT 'outputs', 'note_details', 'rows', COUNT(*) FROM exported_note_details;

INSERT INTO quality_metrics
SELECT 'outputs', 'splits', 'subjects_in_multiple_splits', COUNT(*)
FROM (
    SELECT subject_id
    FROM exported_text_documents
    GROUP BY subject_id
    HAVING COUNT(DISTINCT split) > 1
);

SELECT section, dataset, metric, value
FROM quality_metrics
ORDER BY section, dataset, metric;
