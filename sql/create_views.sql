CREATE OR REPLACE TEMP VIEW core_patients AS
SELECT subject_id
FROM read_csv(
    $patients_path,
    header = true,
    compression = 'gzip',
    columns = {
        'subject_id': 'BIGINT',
        'gender': 'VARCHAR',
        'anchor_age': 'INTEGER',
        'anchor_year': 'INTEGER',
        'anchor_year_group': 'VARCHAR',
        'dod': 'DATE'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW core_admissions AS
SELECT subject_id, hadm_id, admittime, dischtime
FROM read_csv(
    $admissions_path,
    header = true,
    compression = 'gzip',
    columns = {
        'subject_id': 'BIGINT',
        'hadm_id': 'BIGINT',
        'admittime': 'TIMESTAMP',
        'dischtime': 'TIMESTAMP',
        'deathtime': 'TIMESTAMP',
        'admission_type': 'VARCHAR',
        'admit_provider_id': 'VARCHAR',
        'admission_location': 'VARCHAR',
        'discharge_location': 'VARCHAR',
        'insurance': 'VARCHAR',
        'language': 'VARCHAR',
        'marital_status': 'VARCHAR',
        'race': 'VARCHAR',
        'edregtime': 'TIMESTAMP',
        'edouttime': 'TIMESTAMP',
        'hospital_expire_flag': 'INTEGER'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW discharge_raw AS
SELECT *
FROM read_csv(
    $discharge_path,
    header = true,
    compression = 'gzip',
    columns = {
        'note_id': 'VARCHAR',
        'subject_id': 'BIGINT',
        'hadm_id': 'BIGINT',
        'note_type': 'VARCHAR',
        'note_seq': 'INTEGER',
        'charttime': 'TIMESTAMP',
        'storetime': 'TIMESTAMP',
        'text': 'VARCHAR'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW radiology_raw AS
SELECT *
FROM read_csv(
    $radiology_path,
    header = true,
    compression = 'gzip',
    columns = {
        'note_id': 'VARCHAR',
        'subject_id': 'BIGINT',
        'hadm_id': 'BIGINT',
        'note_type': 'VARCHAR',
        'note_seq': 'INTEGER',
        'charttime': 'TIMESTAMP',
        'storetime': 'TIMESTAMP',
        'text': 'VARCHAR'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW discharge_detail_raw AS
SELECT *
FROM read_csv(
    $discharge_detail_path,
    header = true,
    compression = 'gzip',
    columns = {
        'note_id': 'VARCHAR',
        'subject_id': 'BIGINT',
        'field_name': 'VARCHAR',
        'field_value': 'VARCHAR',
        'field_ordinal': 'INTEGER'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW radiology_detail_raw AS
SELECT *
FROM read_csv(
    $radiology_detail_path,
    header = true,
    compression = 'gzip',
    columns = {
        'note_id': 'VARCHAR',
        'subject_id': 'BIGINT',
        'field_name': 'VARCHAR',
        'field_value': 'VARCHAR',
        'field_ordinal': 'INTEGER'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW edstays_raw AS
SELECT *
FROM read_csv(
    $edstays_path,
    header = true,
    compression = 'gzip',
    columns = {
        'subject_id': 'BIGINT',
        'hadm_id': 'BIGINT',
        'stay_id': 'BIGINT',
        'intime': 'TIMESTAMP',
        'outtime': 'TIMESTAMP',
        'gender': 'VARCHAR',
        'race': 'VARCHAR',
        'arrival_transport': 'VARCHAR',
        'disposition': 'VARCHAR'
    },
    nullstr = ''
);

CREATE OR REPLACE TEMP VIEW triage_raw AS
SELECT *
FROM read_csv(
    $triage_path,
    header = true,
    compression = 'gzip',
    columns = {
        'subject_id': 'BIGINT',
        'stay_id': 'BIGINT',
        'temperature': 'DOUBLE',
        'heartrate': 'DOUBLE',
        'resprate': 'DOUBLE',
        'o2sat': 'DOUBLE',
        'sbp': 'DOUBLE',
        'dbp': 'DOUBLE',
        'pain': 'VARCHAR',
        'acuity': 'INTEGER',
        'chiefcomplaint': 'VARCHAR'
    },
    nullstr = ''
);
