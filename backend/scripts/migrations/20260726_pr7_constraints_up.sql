-- PR7: unique constraints and hot-path indexes.
-- Deduplicate before adding unique indexes so upgrades succeed on dirty data.

DELETE FROM match_results a
USING match_results b
WHERE a.resume_id = b.resume_id
  AND a.job_id = b.job_id
  AND (
      a.score < b.score
      OR (a.score = b.score AND a.created_at < b.created_at)
      OR (
          a.score = b.score
          AND a.created_at IS NOT DISTINCT FROM b.created_at
          AND a.id < b.id
      )
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_match_results_resume_job
    ON match_results (resume_id, job_id);

DELETE FROM job_applications a
USING job_applications b
WHERE a.candidate_id = b.candidate_id
  AND a.job_id = b.job_id
  AND (
      a.created_at < b.created_at
      OR (
          a.created_at IS NOT DISTINCT FROM b.created_at
          AND a.id < b.id
      )
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_job_applications_candidate_job
    ON job_applications (candidate_id, job_id);

CREATE INDEX IF NOT EXISTS ix_job_applications_job_status
    ON job_applications (job_id, status);

CREATE INDEX IF NOT EXISTS ix_job_applications_candidate_created
    ON job_applications (candidate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_interview_invitations_candidate_status
    ON interview_invitations (candidate_id, status);

CREATE INDEX IF NOT EXISTS ix_interview_invitations_job_created
    ON interview_invitations (job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_application_messages_application_created
    ON application_messages (application_id, created_at);
