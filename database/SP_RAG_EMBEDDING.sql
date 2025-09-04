create or replace PROCEDURE SP_RAG_EMBEDDING (
       p_file_id IN NUMBER
    ) AS
    BEGIN
        DELETE FROM RAG_DOCS WHERE FILE_ID = p_file_id;
        COMMIT;

        INSERT INTO RAG_DOCS (FILE_ID, TEXT, METADATA, EMBEDDING)
        SELECT
            a.FILE_ID                  AS FILE_ID,
            TO_CLOB(ct.chunk_data)     AS TEXT,
            a.METADATA                 AS METADATA,
            TO_VECTOR(et.embed_vector) AS EMBEDDING
        FROM VW_RAG_DOCS_FILES a
            CROSS JOIN dbms_vector_chain.utl_to_chunks(
                a.TEXT,
                json('{
                    "by"        : "characters",
                    "max"       : "512",
                    "overlap"   : "51",
                    "split"     : "recursively",
                    "language"  : "esa",
                    "normalize" : "all"
                }')
            ) c
            CROSS JOIN JSON_TABLE(
                c.column_value, '$[*]'
                COLUMNS (
                    chunk_id     NUMBER         PATH '$.chunk_id',
                    chunk_offset NUMBER         PATH '$.chunk_offset',
                    chunk_length NUMBER         PATH '$.chunk_length',
                    chunk_data   VARCHAR2(4000) PATH '$.chunk_data'
                )
            ) ct
            CROSS JOIN dbms_vector_chain.utl_to_embeddings(
                ct.chunk_data,
                json('{
                    "provider"        : "ocigenai",
                    "credential_name" : "OCI_CRED",
                    "url"             : "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/20231130/actions/embedText",
                    "model"           : "cohere.embed-v4.0"
                }')
            ) e
            CROSS JOIN JSON_TABLE(
                e.column_value, '$[*]'
                COLUMNS (
                    embed_id     NUMBER         PATH '$.embed_id',
                    embed_data   VARCHAR2(4000) PATH '$.embed_data',
                    embed_vector CLOB           PATH '$.embed_vector'
                )
            ) et
        WHERE
            a.FILE_ID = p_file_id;
        COMMIT;

    END;
