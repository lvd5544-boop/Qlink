DROP INDEX IF EXISTS ix_application_messages_application_created;
DROP INDEX IF EXISTS ix_interview_invitations_job_created;
DROP INDEX IF EXISTS ix_interview_invitations_candidate_status;
DROP INDEX IF EXISTS ix_job_applications_candidate_created;
DROP INDEX IF EXISTS ix_job_applications_job_status;
ALTER TABLE job_applications
    DROP CONSTRAINT IF EXISTS uq_job_applications_candidate_job;
DROP INDEX IF EXISTS uq_job_applications_candidate_job;
ALTER TABLE match_results
    DROP CONSTRAINT IF EXISTS uq_match_results_resume_job;
DROP INDEX IF EXISTS uq_match_results_resume_job;
