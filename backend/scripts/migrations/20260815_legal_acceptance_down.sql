DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM legal_acceptances) THEN
        RAISE EXCEPTION 'legal_acceptances contains acceptance evidence; downgrade refused';
    END IF;
END $$;

DROP TABLE IF EXISTS legal_acceptances;
