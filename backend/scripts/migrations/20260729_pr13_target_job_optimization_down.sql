DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM resume_patch_proposals)
       OR EXISTS (SELECT 1 FROM readiness_actions)
       OR EXISTS (SELECT 1 FROM optimization_issues) THEN
        RAISE EXCEPTION
            'PR13 downgrade refused: optimization data exists; export or delete it explicitly first';
    END IF;
END
$guard$;

DROP TABLE IF EXISTS resume_patch_proposals;
DROP TABLE IF EXISTS readiness_actions;
DROP TABLE IF EXISTS optimization_strategy_options;
DROP TABLE IF EXISTS optimization_issue_claim_links;
DROP TABLE IF EXISTS optimization_issues;
