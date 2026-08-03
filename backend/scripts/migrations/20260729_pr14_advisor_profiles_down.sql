DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM advisor_messages)
       OR EXISTS (SELECT 1 FROM job_requirements)
       OR EXISTS (SELECT 1 FROM target_role_profile_snapshots) THEN
        RAISE EXCEPTION
            'PR14 downgrade refused: advisor/profile data exists; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP TABLE IF EXISTS advisor_messages;
DROP TABLE IF EXISTS job_requirements;
DROP TABLE IF EXISTS target_role_profile_snapshots;
ALTER TABLE data_source_versions DROP CONSTRAINT IF EXISTS ck_data_source_version_status;
ALTER TABLE data_source_versions DROP COLUMN IF EXISTS status;
ALTER TABLE data_sources DROP COLUMN IF EXISTS scope;
