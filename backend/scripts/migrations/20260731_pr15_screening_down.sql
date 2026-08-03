DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM screening_results)
       OR EXISTS (SELECT 1 FROM screening_rules)
       OR EXISTS (SELECT 1 FROM screening_runs)
       OR EXISTS (
            SELECT 1 FROM decision_traces
            WHERE decision_type LIKE 'screening%'
       ) THEN
        RAISE EXCEPTION
            'PR15 downgrade refused: screening/decision data exists; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP TABLE IF EXISTS screening_results;
DROP TABLE IF EXISTS screening_rules;
DROP TABLE IF EXISTS screening_runs;
DROP TABLE IF EXISTS decision_traces;
