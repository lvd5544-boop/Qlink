DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM pilot_feedback)
       OR EXISTS (SELECT 1 FROM pilot_consents)
       OR EXISTS (SELECT 1 FROM pilot_participants) THEN
        RAISE EXCEPTION
            'Pilot readiness downgrade refused: participant data exists; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP TABLE IF EXISTS pilot_feedback;
DROP TABLE IF EXISTS pilot_consents;
DROP TABLE IF EXISTS pilot_participants;
