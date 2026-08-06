CREATE OR REPLACE TEMP VIEW evidence_links AS
WITH event_evidence AS (
    SELECT
        'EV:' || i.item_event_id AS evidence_link_id,
        'timeline_event' AS target_type,
        i.event_id AS target_id,
        'structured_row' AS evidence_type,
        i.source_table,
        i.native_row_key,
        NULL::VARCHAR AS note_id,
        NULL::VARCHAR AS section_name,
        NULL::BIGINT AS character_start,
        NULL::BIGINT AS character_end,
        'supports' AS relationship_type,
        'inherits_target_link_status' AS link_method
    FROM event_items i
), document_evidence AS (
    SELECT
        'DOC:' || md5(concat_ws('|', note_id, source_table)) AS evidence_link_id,
        'document' AS target_type,
        note_id AS target_id,
        'text_span' AS evidence_type,
        source_table,
        'note_id=' || note_id AS native_row_key,
        note_id,
        NULL::VARCHAR AS section_name,
        0::BIGINT AS character_start,
        LENGTH(text)::BIGINT AS character_end,
        'contains' AS relationship_type,
        link_status AS link_method
    FROM documents
), note_detail_evidence AS (
    SELECT
        'NOTEDETAIL:' || md5(concat_ws('|', x.note_id, x.subject_id, x.field_name, x.field_ordinal)) AS evidence_link_id,
        'document' AS target_type,
        x.note_id AS target_id,
        'document_metadata' AS evidence_type,
        x.source_table,
        concat_ws('|', 'note_id=' || x.note_id, 'field_name=' || x.field_name,
            'field_ordinal=' || x.field_ordinal) AS native_row_key,
        x.note_id,
        x.field_name AS section_name,
        NULL::BIGINT AS character_start,
        NULL::BIGINT AS character_end,
        'describes' AS relationship_type,
        d.link_status AS link_method
    FROM note_detail_rows x
    INNER JOIN documents d
        ON d.note_id = x.note_id
       AND d.subject_id = TRY_CAST(x.subject_id AS BIGINT)
)
SELECT * FROM event_evidence
UNION ALL
SELECT * FROM document_evidence
UNION ALL
SELECT * FROM note_detail_evidence;

CREATE OR REPLACE TEMP VIEW patient_history_refs AS
SELECT
    episode_id,
    subject_id,
    'patient_timeline_before' AS referenced_type,
    NULL::VARCHAR AS referenced_id,
    episode_start_time AS available_time,
    'available_before_episode_start' AS history_relation
FROM episode_index;

CREATE OR REPLACE TEMP VIEW episode_coverage AS
WITH event_counts AS (
    SELECT
        episode_id,
        COUNT(*) AS linked_event_count,
        COUNT(*) FILTER (WHERE event_type = 'laboratory_panel') AS laboratory_count,
        COUNT(*) FILTER (WHERE event_type = 'microbiology_specimen') AS microbiology_count,
        COUNT(*) FILTER (WHERE event_type = 'ed_vital_signs') AS serial_vital_count,
        COUNT(*) FILTER (WHERE event_type = 'provider_order') AS order_count,
        COUNT(*) FILTER (WHERE event_type IN ('prescription', 'pharmacy_order')) AS prescription_count,
        COUNT(*) FILTER (WHERE event_type = 'medication_administration') AS medication_administration_count,
        COUNT(*) FILTER (WHERE event_type IN ('procedure_code', 'icu_procedure', 'hcpcs_event')) AS procedure_count,
        COUNT(*) FILTER (WHERE event_type IN ('diagnosis_code', 'ed_diagnosis_code')) AS diagnosis_count,
        COUNT(*) FILTER (WHERE link_status = 'native_link') AS native_link_count,
        COUNT(*) FILTER (WHERE link_status = 'unique_temporal_link') AS temporal_link_count,
        MIN(event_time) AS first_event_time,
        MAX(event_time) AS last_event_time
    FROM timeline_events
    WHERE episode_id IS NOT NULL
    GROUP BY episode_id
), document_counts AS (
    SELECT
        episode_id,
        COUNT(*) FILTER (WHERE document_type = 'radiology') AS radiology_report_count,
        COUNT(*) FILTER (WHERE document_type = 'discharge') AS discharge_summary_count
    FROM documents
    WHERE episode_id IS NOT NULL
    GROUP BY episode_id
), unresolved_counts AS (
    SELECT
        e.episode_id,
        COUNT(u.event_id) AS unresolved_event_count
    FROM episode_index e
    LEFT JOIN timeline_events u
        ON u.subject_id = e.subject_id
       AND u.link_status = 'unresolved'
       AND u.event_time BETWEEN e.episode_start_time AND e.administrative_end_time
    GROUP BY e.episode_id
)
SELECT
    e.episode_id,
    COALESCE(t.chief_complaint_count, 0) > 0 AS has_chief_complaint,
    COALESCE(t.triage_vital_count, 0) > 0 AS has_triage_vitals,
    COALESCE(v.serial_vital_count, 0) > 0 AS has_serial_vitals,
    COALESCE(v.laboratory_count, 0) > 0 AS has_laboratory,
    COALESCE(v.microbiology_count, 0) > 0 AS has_microbiology,
    COALESCE(d.radiology_report_count, 0) > 0 AS has_radiology,
    COALESCE(v.order_count, 0) > 0 AS has_orders,
    COALESCE(v.prescription_count, 0) > 0 AS has_prescriptions,
    COALESCE(v.medication_administration_count, 0) > 0 AS has_medication_administration,
    COALESCE(v.procedure_count, 0) > 0 AS has_procedures,
    COALESCE(v.diagnosis_count, 0) > 0 AS has_diagnoses,
    COALESCE(x.disposition_count, 0) > 0 AS has_disposition,
    COALESCE(d.discharge_summary_count, 0) > 0 AS has_discharge_summary,
    COALESCE(v.laboratory_count, 0) AS laboratory_count,
    COALESCE(d.radiology_report_count, 0) AS radiology_report_count,
    COALESCE(v.native_link_count, 0) AS native_link_count,
    COALESCE(v.temporal_link_count, 0) AS temporal_link_count,
    COALESCE(u.unresolved_event_count, 0) AS unresolved_event_count,
    v.first_event_time,
    v.last_event_time
FROM episode_index e
LEFT JOIN event_counts v ON v.episode_id = e.episode_id
LEFT JOIN document_counts d ON d.episode_id = e.episode_id
LEFT JOIN triage_counts_source t ON t.episode_id = e.episode_id
LEFT JOIN disposition_counts_source x ON x.episode_id = e.episode_id
LEFT JOIN unresolved_counts u ON u.episode_id = e.episode_id;

CREATE OR REPLACE TEMP VIEW unresolved_events AS
WITH unresolved_event_base AS (
    SELECT
        event_id,
        subject_id,
        event_type,
        event_time,
        available_time,
        native_hadm_id,
        native_contact_id,
        candidate_episode_count,
        unresolved_reason,
        source_table
    FROM timeline_events
    WHERE link_status = 'unresolved'
),
event_keys AS (
    SELECT i.event_id, MIN(i.native_row_key) AS native_row_key
    FROM event_items i
    INNER JOIN unresolved_event_base b ON b.event_id = i.event_id
    GROUP BY i.event_id
)
SELECT
    b.event_id,
    b.subject_id,
    b.event_type,
    b.event_time,
    b.available_time,
    b.native_hadm_id,
    TRY_CAST(SPLIT_PART(b.native_contact_id, ':', 2) AS BIGINT) AS native_stay_id,
    b.candidate_episode_count,
    b.unresolved_reason,
    b.source_table,
    k.native_row_key
FROM unresolved_event_base b
LEFT JOIN event_keys k ON k.event_id = b.event_id

UNION ALL

SELECT
    'DOCUMENT:' || d.note_id,
    d.subject_id,
    'document',
    d.event_time,
    d.available_time,
    d.native_hadm_id,
    NULL::BIGINT,
    d.candidate_episode_count,
    d.unresolved_reason,
    d.source_table,
    'note_id=' || d.note_id
FROM documents d
WHERE d.link_status = 'unresolved';
