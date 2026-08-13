DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM inference_hypotheses) THEN
        RAISE EXCEPTION
            'C5 downgrade refused: inference hypothesis data exists; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP TABLE IF EXISTS inference_hypotheses;
