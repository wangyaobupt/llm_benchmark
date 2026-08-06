CREATE OR REPLACE TEMP VIEW event_temporal_candidates AS
SELECT
    u.event_id,
    COUNT(DISTINCT e.episode_id) AS candidate_episode_count,
    MIN(e.episode_id) AS candidate_episode_id
FROM unlinked_events u
INNER JOIN episode_index e
    ON e.subject_id = u.subject_id
   AND u.event_time BETWEEN e.episode_start_time AND e.administrative_end_time
WHERE u.native_hadm_id IS NULL
  AND u.native_contact_id IS NULL
  AND u.allow_temporal
GROUP BY u.event_id;

CREATE OR REPLACE TEMP VIEW timeline_events AS
WITH linked AS (
    SELECT
        u.*,
        c.contact_id AS matched_contact_id,
        c.episode_id AS contact_episode_id,
        a.hadm_id AS matched_hadm_id,
        a.episode_id AS admission_episode_id,
        a.subject_id AS admission_subject_id,
        t.candidate_episode_count,
        t.candidate_episode_id
    FROM unlinked_events u
    LEFT JOIN care_contacts c
        ON c.contact_id = u.native_contact_id
       AND c.subject_id = u.subject_id
    LEFT JOIN episode_index a
        ON a.hadm_id = u.native_hadm_id
       AND a.episode_type = 'hospital'
    LEFT JOIN event_temporal_candidates t ON t.event_id = u.event_id
)
SELECT
    event_id,
    event_group_id,
    CASE
        WHEN native_contact_id IS NOT NULL AND matched_contact_id IS NOT NULL
        THEN contact_episode_id
        WHEN native_contact_id IS NULL
         AND native_hadm_id IS NOT NULL
         AND matched_hadm_id IS NOT NULL
         AND admission_subject_id = subject_id
        THEN admission_episode_id
        WHEN native_contact_id IS NULL
         AND native_hadm_id IS NULL
         AND allow_temporal
         AND candidate_episode_count = 1
        THEN candidate_episode_id
        ELSE NULL
    END AS episode_id,
    matched_contact_id AS contact_id,
    subject_id,
    event_type,
    event_subtype,
    event_time,
    available_time,
    recorded_time,
    start_time,
    end_time,
    time_precision,
    status,
    decision_evidence_level,
    CASE
        WHEN native_contact_id IS NOT NULL AND matched_contact_id IS NOT NULL
        THEN 'native_link'
        WHEN native_contact_id IS NULL
         AND native_hadm_id IS NOT NULL
         AND matched_hadm_id IS NOT NULL
         AND admission_subject_id = subject_id
        THEN 'native_link'
        WHEN native_contact_id IS NULL
         AND native_hadm_id IS NULL
         AND allow_temporal
         AND candidate_episode_count = 1
        THEN 'unique_temporal_link'
        ELSE 'unresolved'
    END AS link_status,
    'raw_mapped' AS normalization_status,
    CASE
        WHEN native_contact_id IS NOT NULL AND matched_contact_id IS NULL
        THEN 'contact_not_found_or_subject_mismatch'
        WHEN native_contact_id IS NULL AND native_hadm_id IS NOT NULL AND matched_hadm_id IS NULL
        THEN 'hadm_not_found'
        WHEN native_contact_id IS NULL AND native_hadm_id IS NOT NULL AND admission_subject_id <> subject_id
        THEN 'subject_hadm_mismatch'
        WHEN native_contact_id IS NULL AND native_hadm_id IS NULL AND NOT allow_temporal
        THEN 'patient_level_no_encounter_id'
        WHEN native_contact_id IS NULL AND native_hadm_id IS NULL
         AND allow_temporal AND COALESCE(candidate_episode_count, 0) = 0
        THEN 'no_temporal_episode'
        WHEN native_contact_id IS NULL AND native_hadm_id IS NULL
         AND allow_temporal AND candidate_episode_count > 1
        THEN 'multiple_temporal_episodes'
        ELSE NULL
    END AS unresolved_reason,
    native_hadm_id,
    native_contact_id,
    COALESCE(candidate_episode_count, 0) AS candidate_episode_count,
    source_table,
    source_version
FROM linked;
