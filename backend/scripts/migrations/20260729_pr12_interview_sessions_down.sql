DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM interview_sessions)
       OR EXISTS (SELECT 1 FROM interview_questions)
       OR EXISTS (SELECT 1 FROM interview_answers)
       OR EXISTS (SELECT 1 FROM interview_observations) THEN
        RAISE EXCEPTION
            'PR12 downgrade refused: structured interview data exists; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP INDEX IF EXISTS ix_interview_results_structured_session;
ALTER TABLE interview_results DROP COLUMN IF EXISTS structured_session_id;
DROP TABLE IF EXISTS interview_observations;
DROP TABLE IF EXISTS interview_answers;
DROP TABLE IF EXISTS interview_questions;
DROP TABLE IF EXISTS interview_sessions;
