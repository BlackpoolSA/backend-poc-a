create or replace PROCEDURE SP_SEL_AI_PROFILE
    AS
        l_profile_name    VARCHAR2(255)  := 'OCIPROFILE';
        l_model           VARCHAR2(255)  := 'meta.llama-4-maverick-17b-128e-instruct-fp8';
        l_credential      VARCHAR2(4000) := 'OCI_CRED';
        l_region          VARCHAR2(255)  := 'us-chicago-1';
        l_compartment_id  VARCHAR2(255)  := 'ocid1.compartment.oc1..aaaaaaaavlce4ue4nvd56v6ijrluwovk5y4ezcg6xxk44vkt3wgsznqf4irq';
        l_object_list     CLOB;
        l_json_attributes CLOB;
        CURSOR c_objects IS
            SELECT
            'ATP23AI' AS owner,
            table_name AS name
            FROM user_tables
            WHERE table_name LIKE 'REPO\_%' ESCAPE '\'
            ORDER BY table_name;
    BEGIN
        /* 1) Drop the profile if it exists */
        DBMS_CLOUD_AI.DROP_PROFILE(profile_name => l_profile_name, force => TRUE);

        /* 2) Build object_list JSON array from FILES table */
        l_object_list := '[';
        FOR rec IN c_objects LOOP
            l_object_list := l_object_list || '{"owner": "' || rec.owner || '", "name": "' || rec.name || '"},';
        END LOOP;

        /* Remove trailing comma and close JSON array */
        IF l_object_list LIKE '%,' THEN
            l_object_list := SUBSTR(l_object_list, 1, LENGTH(l_object_list) - 1);
        END IF;
        l_object_list := l_object_list || ']';

        /* 3) Construct the JSON attributes */
        l_json_attributes := '{
            "provider":"oci",
            "model":"' || l_model || '",
            "credential_name":"' || l_credential || '",
            "comments":"true",
            "object_list": ' || l_object_list || ',
            "region":"' || l_region || '",
            "oci_compartment_id": "' || l_compartment_id || '"
        }';

        /* 4) Create the profile */
        DBMS_CLOUD_AI.CREATE_PROFILE(
            profile_name => l_profile_name,
            attributes   => l_json_attributes
        );
    END;
