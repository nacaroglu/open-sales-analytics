from scripts.validate_alert_demo import validate_documents


def valid_documents():
    runbook = """
    authenticated development deployment
    Never run against production
    OSARepeatedDatasetCreationFailures
    10-minute query window and 5-minute pending period
    python -m app.controlled_failure --confirm-controlled-failure
    three internal creation failures
    test webhook
    sample workflow
    bounded intervals
    issue #270
    AWS
    webhook
    """
    evidence = """
    **Status: Pending. No live development demonstration has been performed.**
    | Alert firing after pending period for development/release | Pending | Pending |
    | Test webhook delivery succeeded; bounded labels only | Pending | Pending |
    | Correlated logs captured | Pending | Pending |
    | Correlated trace captured | Pending | Pending |
    | App readiness and sample workflow recovered | Pending | Pending |
    | Alert resolved after failures aged out of 10m window | Pending | Pending |
    """
    return runbook, evidence


def test_offline_validator_accepts_complete_pending_runbook_and_evidence():
    runbook, evidence = valid_documents()
    assert validate_documents(runbook, evidence) == []


def test_offline_validator_rejects_missing_safety_or_evidence_requirements():
    runbook, evidence = valid_documents()
    errors = validate_documents(
        runbook.replace("Never run against production", ""),
        evidence.replace("| Correlated trace captured | Pending | Pending |", ""),
    )
    assert any("Never run against production" in error for error in errors)
    assert any("Correlated trace captured" in error for error in errors)


def test_offline_validator_requires_runtime_evidence_to_remain_pending():
    runbook, evidence = valid_documents()
    errors = validate_documents(runbook, evidence.replace("Status: Pending", "Status: Complete"))
    assert any("evidence must remain pending" in error for error in errors)
