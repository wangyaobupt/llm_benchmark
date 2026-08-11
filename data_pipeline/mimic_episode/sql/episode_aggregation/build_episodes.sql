CREATE OR REPLACE TEMP VIEW typed_patients AS
SELECT TRY_CAST(subject_id AS BIGINT) AS subject_id
FROM raw_patients;

CREATE OR REPLACE TEMP VIEW typed_admissions AS
SELECT
    TRY_CAST(subject_id AS BIGINT) AS subject_id,
    TRY_CAST(hadm_id AS BIGINT) AS hadm_id,
    TRY_CAST(admittime AS TIMESTAMP) AS admittime,
    TRY_CAST(dischtime AS TIMESTAMP) AS dischtime,
    TRY_CAST(deathtime AS TIMESTAMP) AS deathtime,
    admission_type,
    admit_provider_id,
    admission_location,
    discharge_location,
    insurance,
    language,
    marital_status,
    race,
    TRY_CAST(edregtime AS TIMESTAMP) AS edregtime,
    TRY_CAST(edouttime AS TIMESTAMP) AS edouttime,
    TRY_CAST(hospital_expire_flag AS INTEGER) AS hospital_expire_flag
FROM raw_admissions;

CREATE OR REPLACE TEMP VIEW typed_edstays AS
SELECT
    TRY_CAST(subject_id AS BIGINT) AS subject_id,
    TRY_CAST(hadm_id AS BIGINT) AS hadm_id,
    TRY_CAST(stay_id AS BIGINT) AS stay_id,
    TRY_CAST(intime AS TIMESTAMP) AS intime,
    TRY_CAST(outtime AS TIMESTAMP) AS outtime,
    gender,
    race,
    arrival_transport,
    disposition
FROM raw_edstays;

CREATE OR REPLACE TEMP VIEW classified_edstays AS
SELECT
    e.*,
    a.hadm_id AS matched_hadm_id,
    CASE
        WHEN e.hadm_id IS NULL THEN 'no_hadm_id'
        WHEN a.hadm_id IS NULL THEN 'hadm_not_found_or_subject_mismatch'
        ELSE 'matched'
    END AS admission_link_status,
    CASE
        WHEN a.hadm_id IS NOT NULL THEN 'H:' || CAST(a.hadm_id AS VARCHAR)
        ELSE 'E:' || CAST(e.stay_id AS VARCHAR)
    END AS episode_id
FROM typed_edstays e
LEFT JOIN typed_admissions a
    ON a.hadm_id = e.hadm_id
   AND a.subject_id = e.subject_id;

CREATE OR REPLACE TEMP VIEW typed_icustays AS
SELECT
    TRY_CAST(subject_id AS BIGINT) AS subject_id,
    TRY_CAST(hadm_id AS BIGINT) AS hadm_id,
    TRY_CAST(stay_id AS BIGINT) AS stay_id,
    first_careunit,
    last_careunit,
    TRY_CAST(intime AS TIMESTAMP) AS intime,
    TRY_CAST(outtime AS TIMESTAMP) AS outtime,
    TRY_CAST(los AS DOUBLE) AS los
FROM raw_icustays;

CREATE OR REPLACE TEMP VIEW typed_transfers AS
SELECT
    TRY_CAST(subject_id AS BIGINT) AS subject_id,
    TRY_CAST(hadm_id AS BIGINT) AS hadm_id,
    TRY_CAST(transfer_id AS BIGINT) AS transfer_id,
    eventtype,
    careunit,
    TRY_CAST(intime AS TIMESTAMP) AS intime,
    TRY_CAST(outtime AS TIMESTAMP) AS outtime
FROM raw_transfers;

CREATE OR REPLACE TEMP VIEW episode_index AS
WITH linked_ed AS (
    SELECT
        matched_hadm_id AS hadm_id,
        MIN(intime) AS earliest_ed_intime,
        COUNT(*) AS linked_ed_contact_count
    FROM classified_edstays
    WHERE admission_link_status = 'matched'
    GROUP BY matched_hadm_id
), icu_counts AS (
    SELECT i.hadm_id, COUNT(*) AS icu_contact_count
    FROM typed_icustays i
    INNER JOIN typed_admissions a
        ON a.hadm_id = i.hadm_id
       AND a.subject_id = i.subject_id
    GROUP BY i.hadm_id
), transfer_counts AS (
    SELECT t.hadm_id, COUNT(*) AS transfer_contact_count
    FROM typed_transfers t
    INNER JOIN typed_admissions a
        ON a.hadm_id = t.hadm_id
       AND a.subject_id = t.subject_id
    GROUP BY t.hadm_id
), hospital_episodes AS (
    SELECT
        'H:' || CAST(a.hadm_id AS VARCHAR) AS episode_id,
        'hospital' AS episode_type,
        a.subject_id,
        a.hadm_id,
        CASE
            WHEN e.earliest_ed_intime IS NOT NULL
             AND e.earliest_ed_intime < a.admittime
            THEN e.earliest_ed_intime
            ELSE a.admittime
        END AS episode_start_time,
        CASE
            WHEN a.deathtime IS NOT NULL
             AND (a.dischtime IS NULL OR a.deathtime < a.dischtime)
            THEN a.deathtime
            ELSE a.dischtime
        END AS clinical_end_time,
        a.dischtime AS administrative_end_time,
        CASE
            WHEN a.hospital_expire_flag = 1 OR a.deathtime IS NOT NULL THEN 'death'
            ELSE 'discharge'
        END AS outcome_type,
        COALESCE(e.linked_ed_contact_count, 0) AS linked_ed_contact_count,
        COALESCE(i.icu_contact_count, 0) AS icu_contact_count,
        COALESCE(t.transfer_contact_count, 0) AS transfer_contact_count,
        'mimic-iv=3.1;mimic-iv-ed=2.2;mimic-iv-note=2.2' AS source_versions,
        'matched' AS admission_link_status,
        a.hadm_id AS candidate_hadm_id,
        a.admission_type,
        a.admission_location,
        a.discharge_location,
        a.hospital_expire_flag
    FROM typed_admissions a
    LEFT JOIN linked_ed e ON e.hadm_id = a.hadm_id
    LEFT JOIN icu_counts i ON i.hadm_id = a.hadm_id
    LEFT JOIN transfer_counts t ON t.hadm_id = a.hadm_id
), standalone_ed_episodes AS (
    SELECT
        'E:' || CAST(e.stay_id AS VARCHAR) AS episode_id,
        'emergency_department' AS episode_type,
        e.subject_id,
        NULL::BIGINT AS hadm_id,
        e.intime AS episode_start_time,
        e.outtime AS clinical_end_time,
        e.outtime AS administrative_end_time,
        e.disposition AS outcome_type,
        1::BIGINT AS linked_ed_contact_count,
        0::BIGINT AS icu_contact_count,
        0::BIGINT AS transfer_contact_count,
        'mimic-iv=3.1;mimic-iv-ed=2.2;mimic-iv-note=2.2' AS source_versions,
        e.admission_link_status,
        e.hadm_id AS candidate_hadm_id,
        NULL::VARCHAR AS admission_type,
        NULL::VARCHAR AS admission_location,
        NULL::VARCHAR AS discharge_location,
        NULL::INTEGER AS hospital_expire_flag
    FROM classified_edstays e
    WHERE e.admission_link_status <> 'matched'
)
SELECT * FROM (
    SELECT * FROM hospital_episodes
    UNION ALL
    SELECT * FROM standalone_ed_episodes
)
WHERE clinical_end_time >= episode_start_time;

CREATE OR REPLACE TEMP VIEW care_contacts AS
WITH contacts AS (
    SELECT
        'IP:' || CAST(a.hadm_id AS VARCHAR) AS contact_id,
        'H:' || CAST(a.hadm_id AS VARCHAR) AS episode_id,
        a.subject_id,
        'inpatient' AS contact_type,
        a.hadm_id,
        NULL::BIGINT AS stay_id,
        NULL::BIGINT AS transfer_id,
        a.admittime AS start_time,
        a.dischtime AS end_time,
        NULL::VARCHAR AS ed_disposition,
        NULL::VARCHAR AS first_careunit,
        NULL::VARCHAR AS last_careunit,
        NULL::DOUBLE AS los_days,
        'native_link' AS link_method,
        'mimic-iv-3.1/hosp/admissions' AS source_table
    FROM typed_admissions a

    UNION ALL

    SELECT
        'ED:' || CAST(e.stay_id AS VARCHAR),
        e.episode_id,
        e.subject_id,
        'emergency_department',
        e.matched_hadm_id,
        e.stay_id,
        NULL::BIGINT,
        e.intime,
        e.outtime,
        e.disposition,
        NULL::VARCHAR,
        NULL::VARCHAR,
        NULL::DOUBLE,
        'native_link',
        'mimic-iv-ed/ed/edstays'
    FROM classified_edstays e

    UNION ALL

    SELECT
        'ICU:' || CAST(i.stay_id AS VARCHAR),
        'H:' || CAST(i.hadm_id AS VARCHAR),
        i.subject_id,
        'icu',
        i.hadm_id,
        i.stay_id,
        NULL::BIGINT,
        i.intime,
        i.outtime,
        NULL::VARCHAR,
        i.first_careunit,
        i.last_careunit,
        i.los,
        'native_link',
        'mimic-iv-3.1/icu/icustays'
    FROM typed_icustays i
    INNER JOIN typed_admissions a
        ON a.hadm_id = i.hadm_id
       AND a.subject_id = i.subject_id

    UNION ALL

    SELECT
        'TR:' || CAST(t.transfer_id AS VARCHAR),
        'H:' || CAST(t.hadm_id AS VARCHAR),
        t.subject_id,
        'transfer',
        t.hadm_id,
        NULL::BIGINT,
        t.transfer_id,
        t.intime,
        t.outtime,
        NULL::VARCHAR,
        NULL::VARCHAR,
        NULL::VARCHAR,
        NULL::DOUBLE,
        'native_link',
        'mimic-iv-3.1/hosp/transfers'
    FROM typed_transfers t
    INNER JOIN typed_admissions a
        ON a.hadm_id = t.hadm_id
       AND a.subject_id = t.subject_id
)
SELECT
    *,
    ROW_NUMBER() OVER (
        PARTITION BY episode_id
        ORDER BY start_time NULLS LAST, end_time NULLS LAST, contact_id
    ) AS contact_sequence
FROM contacts
WHERE episode_id IN (SELECT episode_id FROM episode_index);
