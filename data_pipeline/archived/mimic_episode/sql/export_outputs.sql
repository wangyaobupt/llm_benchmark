COPY (
    SELECT * FROM case_index
    ORDER BY subject_id, hadm_id
) TO $case_index_path (FORMAT PARQUET, COMPRESSION ZSTD);

-- Wide text and EAV detail rows are streamed without a physical sort. Sorting
-- full text exhausts bounded memory, and Parquet row order is not a data contract.
COPY (
    SELECT * FROM note_documents
) TO $text_documents_path (FORMAT PARQUET, COMPRESSION ZSTD);

COPY (
    SELECT * FROM note_details
) TO $note_details_path (FORMAT PARQUET, COMPRESSION ZSTD);
