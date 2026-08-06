CREATE OR REPLACE TEMP VIEW lab_item_rows AS
SELECT
    'LAB:' || l.subject_id || ':' || l.specimen_id AS event_id,
    TRY_CAST(l.labevent_id AS BIGINT) AS labevent_id,
    TRY_CAST(l.subject_id AS BIGINT) AS subject_id,
    TRY_CAST(l.hadm_id AS BIGINT) AS native_hadm_id,
    TRY_CAST(l.specimen_id AS BIGINT) AS specimen_id,
    l.itemid,
    d.label AS concept_name,
    TRY_CAST(l.charttime AS TIMESTAMP) AS event_time,
    TRY_CAST(l.storetime AS TIMESTAMP) AS available_time,
    l.value,
    l.valuenum,
    l.valueuom,
    l.flag,
    l.priority,
    l.comments,
    l._source_row_number,
    to_json(l) AS raw_payload
FROM raw_labevents l
LEFT JOIN raw_d_labitems d ON d.itemid = l.itemid;

CREATE OR REPLACE TEMP VIEW micro_item_rows AS
SELECT
    'MICRO:' || m.subject_id || ':' || m.micro_specimen_id AS event_id,
    TRY_CAST(m.microevent_id AS BIGINT) AS microevent_id,
    TRY_CAST(m.subject_id AS BIGINT) AS subject_id,
    TRY_CAST(m.hadm_id AS BIGINT) AS native_hadm_id,
    TRY_CAST(m.micro_specimen_id AS BIGINT) AS micro_specimen_id,
    COALESCE(TRY_CAST(m.charttime AS TIMESTAMP), TRY_CAST(m.chartdate AS TIMESTAMP)) AS event_time,
    COALESCE(TRY_CAST(m.storetime AS TIMESTAMP), TRY_CAST(m.storedate AS TIMESTAMP)) AS available_time,
    m.spec_itemid,
    m.spec_type_desc,
    m.test_seq,
    m.test_itemid,
    m.test_name,
    m.org_itemid,
    m.org_name,
    m.ab_itemid,
    m.ab_name,
    m.dilution_text,
    m.dilution_value,
    m.interpretation,
    m.comments,
    m._source_row_number,
    to_json(m) AS raw_payload
FROM raw_microbiologyevents m;

CREATE OR REPLACE TEMP VIEW omr_item_rows AS
SELECT
    'OMR:' || subject_id || ':' || chartdate AS event_id,
    TRY_CAST(subject_id AS BIGINT) AS subject_id,
    TRY_CAST(chartdate AS TIMESTAMP) AS event_time,
    TRY_CAST(seq_num AS BIGINT) AS seq_num,
    result_name,
    result_value,
    o._source_row_number,
    to_json(o) AS raw_payload
FROM raw_omr o;

CREATE OR REPLACE TEMP VIEW special_unlinked_events AS
SELECT
    event_id,
    event_id AS event_group_id,
    subject_id,
    CASE
        WHEN COUNT(DISTINCT native_hadm_id) FILTER (WHERE native_hadm_id IS NOT NULL) <= 1
        THEN MAX(native_hadm_id)
        ELSE NULL
    END AS native_hadm_id,
    NULL::VARCHAR AS native_contact_id,
    'laboratory_panel' AS event_type,
    'specimen' AS event_subtype,
    MIN(event_time) AS event_time,
    MAX(available_time) AS available_time,
    MAX(available_time) AS recorded_time,
    MIN(event_time) AS start_time,
    MAX(event_time) AS end_time,
    'timestamp' AS time_precision,
    CASE WHEN COUNT(*) FILTER (WHERE flag IS NOT NULL) > 0 THEN 'abnormal_result_present' END AS status,
    'not_a_decision' AS decision_evidence_level,
    TRUE AS allow_temporal,
    'mimic-iv-3.1/hosp/labevents' AS source_table,
    '3.1' AS source_version
FROM lab_item_rows
GROUP BY event_id, subject_id

UNION ALL

SELECT
    event_id,
    event_id,
    subject_id,
    CASE
        WHEN COUNT(DISTINCT native_hadm_id) FILTER (WHERE native_hadm_id IS NOT NULL) <= 1
        THEN MAX(native_hadm_id)
        ELSE NULL
    END,
    NULL::VARCHAR,
    'microbiology_specimen',
    MAX(spec_type_desc),
    MIN(event_time),
    MAX(available_time),
    MAX(available_time),
    MIN(event_time),
    MAX(event_time),
    CASE WHEN COUNT(*) FILTER (WHERE event_time <> DATE_TRUNC('day', event_time)) > 0
         THEN 'timestamp' ELSE 'date' END,
    MAX(interpretation),
    'not_a_decision',
    TRUE,
    'mimic-iv-3.1/hosp/microbiologyevents',
    '3.1'
FROM micro_item_rows
GROUP BY event_id, subject_id

UNION ALL

SELECT
    event_id,
    event_id,
    subject_id,
    NULL::BIGINT,
    NULL::VARCHAR,
    'outpatient_measurement_group',
    'omr',
    event_time,
    event_time,
    event_time,
    event_time,
    event_time,
    'date',
    NULL::VARCHAR,
    'not_a_decision',
    FALSE,
    'mimic-iv-3.1/hosp/omr',
    '3.1'
FROM omr_item_rows
GROUP BY event_id, subject_id, event_time

UNION ALL

SELECT
    'POE:' || d.poe_id,
    'POE:' || d.poe_id,
    TRY_CAST(d.subject_id AS BIGINT),
    NULL::BIGINT,
    NULL::VARCHAR,
    'provider_order_detail_orphan',
    'poe_detail_without_parent',
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    'unknown',
    'orphan_detail_parent',
    'observed_decision',
    FALSE,
    'mimic-iv-3.1/hosp/poe_detail',
    '3.1'
FROM raw_poe_detail d
LEFT JOIN raw_poe p
    ON p.poe_id = d.poe_id
   AND p.subject_id = d.subject_id
WHERE p.poe_id IS NULL
GROUP BY d.poe_id, d.subject_id

UNION ALL

SELECT
    'EMAR:' || d.emar_id,
    'EMAR:' || d.emar_id,
    TRY_CAST(d.subject_id AS BIGINT),
    NULL::BIGINT,
    NULL::VARCHAR,
    'medication_administration_detail_orphan',
    'emar_detail_without_parent',
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    NULL::TIMESTAMP,
    'unknown',
    'orphan_detail_parent',
    'observed_decision',
    FALSE,
    'mimic-iv-3.1/hosp/emar_detail',
    '3.1'
FROM raw_emar_detail d
LEFT JOIN raw_emar e
    ON e.emar_id = d.emar_id
   AND e.subject_id = d.subject_id
WHERE e.emar_id IS NULL
GROUP BY d.emar_id, d.subject_id;

CREATE OR REPLACE TEMP VIEW special_event_items AS
SELECT
    'ITEM:labevents:' || CAST(_source_row_number AS VARCHAR) AS item_event_id,
    event_id,
    'labevent_id=' || CAST(labevent_id AS VARCHAR) AS native_row_key,
    itemid AS concept_id,
    concept_name,
    itemid AS raw_code,
    value AS raw_value,
    valueuom AS raw_unit,
    TRY_CAST(valuenum AS DOUBLE) AS normalized_value,
    valueuom AS normalized_unit,
    flag,
    _source_row_number AS item_ordinal,
    raw_payload,
    'mimic-iv-3.1/hosp/labevents' AS source_table,
    '3.1' AS source_version
FROM lab_item_rows

UNION ALL

SELECT
    'ITEM:microbiologyevents:' || CAST(_source_row_number AS VARCHAR),
    event_id,
    'microevent_id=' || CAST(microevent_id AS VARCHAR),
    COALESCE(test_itemid, org_itemid, ab_itemid),
    COALESCE(test_name, org_name, ab_name, spec_type_desc),
    COALESCE(test_itemid, org_itemid, ab_itemid),
    COALESCE(interpretation, dilution_text, org_name, test_name),
    NULL::VARCHAR,
    TRY_CAST(dilution_value AS DOUBLE),
    NULL::VARCHAR,
    interpretation,
    _source_row_number,
    raw_payload,
    'mimic-iv-3.1/hosp/microbiologyevents',
    '3.1'
FROM micro_item_rows

UNION ALL

SELECT
    'ITEM:omr:' || CAST(_source_row_number AS VARCHAR),
    event_id,
    concat_ws('|', 'subject_id=' || CAST(subject_id AS VARCHAR),
        'chartdate=' || CAST(event_time AS DATE), 'seq_num=' || CAST(seq_num AS VARCHAR)),
    result_name,
    result_name,
    result_name,
    result_value,
    NULL::VARCHAR,
    TRY_CAST(result_value AS DOUBLE),
    NULL::VARCHAR,
    NULL::VARCHAR,
    _source_row_number,
    raw_payload,
    'mimic-iv-3.1/hosp/omr',
    '3.1'
FROM omr_item_rows;

CREATE OR REPLACE TEMP VIEW poe_detail_event_items AS
SELECT
    'ITEM:poe_detail:' || CAST(p._source_row_number AS VARCHAR) AS item_event_id,
    'POE:' || poe_id AS event_id,
    concat_ws('|', 'poe_id=' || poe_id, 'poe_seq=' || poe_seq,
        'field_name=' || field_name, 'field_value=' || field_value) AS native_row_key,
    field_name AS concept_id,
    field_name AS concept_name,
    field_name AS raw_code,
    field_value AS raw_value,
    NULL::VARCHAR AS raw_unit,
    TRY_CAST(field_value AS DOUBLE) AS normalized_value,
    NULL::VARCHAR AS normalized_unit,
    NULL::VARCHAR AS flag,
    p._source_row_number AS item_ordinal,
    to_json(p) AS raw_payload,
    'mimic-iv-3.1/hosp/poe_detail' AS source_table,
    '3.1' AS source_version
FROM raw_poe_detail p;

CREATE OR REPLACE TEMP VIEW emar_detail_event_items AS
SELECT
    'ITEM:emar_detail:' || CAST(e._source_row_number AS VARCHAR) AS item_event_id,
    'EMAR:' || emar_id AS event_id,
    concat_ws('|', 'emar_id=' || emar_id, 'emar_seq=' || emar_seq,
        'parent_field_ordinal=' || parent_field_ordinal) AS native_row_key,
    COALESCE(product_code, administration_type) AS concept_id,
    COALESCE(product_description, administration_type) AS concept_name,
    product_code AS raw_code,
    COALESCE(dose_given, product_amount_given, infusion_rate) AS raw_value,
    COALESCE(dose_given_unit, product_unit, infusion_rate_unit) AS raw_unit,
    TRY_CAST(COALESCE(dose_given, product_amount_given, infusion_rate) AS DOUBLE) AS normalized_value,
    COALESCE(dose_given_unit, product_unit, infusion_rate_unit) AS normalized_unit,
    complete_dose_not_given AS flag,
    e._source_row_number AS item_ordinal,
    to_json(e) AS raw_payload,
    'mimic-iv-3.1/hosp/emar_detail' AS source_table,
    '3.1' AS source_version
FROM raw_emar_detail e;
