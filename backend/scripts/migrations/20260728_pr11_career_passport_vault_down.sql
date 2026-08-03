DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM career_experiences)
       OR EXISTS (SELECT 1 FROM evidence_artifacts)
       OR EXISTS (SELECT 1 FROM resume_versions) THEN
        RAISE EXCEPTION 'PR11 downgrade refused: Career Passport/Vault contains user data; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP TABLE IF EXISTS resume_version_claim_links;
DROP TABLE IF EXISTS resume_versions;
DROP TABLE IF EXISTS migration_orphan_reports;
DROP INDEX IF EXISTS ix_claim_evidence_artifact;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS valid_until;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS valid_from;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS access_scope;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS candidate_confirmed;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS model_suggestion_id;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS link_method;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS link_created_by;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS source_span;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS relationship;
ALTER TABLE claim_evidence DROP COLUMN IF EXISTS artifact_id;
DROP INDEX IF EXISTS ix_resume_claim_experience;
DROP INDEX IF EXISTS ix_resume_claim_user_state;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS superseded_by_claim_id;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS default_visibility;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS sensitivity_level;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS confirmed_at;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS confirmation_state;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS source_span;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS source_object_id;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS source_object_type;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS origin_kind;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS career_experience_id;
ALTER TABLE resume_claims DROP COLUMN IF EXISTS user_id;
DROP TABLE IF EXISTS evidence_artifacts;
DROP TABLE IF EXISTS career_experiences;
