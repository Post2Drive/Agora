from agora.policy import OPERATIONS, decide


def _subject(**extra):
    return {"subject_id": "u-1", "project_id": "project-a", **extra}


def _resource(**extra):
    return {"resource_ids": ["r-1"], "project_id": "project-a", **extra}


def test_unknown_role_is_denied_by_default():
    result = decide(_subject(), "unlisted", "import", _resource())
    assert result["decision"] == "deny"
    assert result["reason"] == "unknown_role"


def test_sensitivity_downgrade_is_denied():
    result = decide(_subject(), "operator", "binding", _resource(
        source_sensitivity="sensitive", target_sensitivity="internal"))
    assert result["decision"] == "deny"
    assert result["reason"] == "sensitivity_downgrade"


def test_missing_scope_is_denied():
    result = decide({"subject_id": "u-1"}, "operator", "import", _resource())
    assert result["decision"] == "deny"
    assert result["reason"] == "scope_missing"


def test_missing_or_unknown_sensitivity_is_denied_for_every_operation():
    for operation in OPERATIONS:
        role = "approver" if operation == "decision_approval" else "operator"
        result = decide(_subject(), role, operation, _resource())
        assert result["decision"] == "deny"
        assert result["reason"] == "sensitivity_missing"
    unknown = decide(_subject(), "operator", "binding", _resource(sensitivity="secret"))
    assert unknown["reason"] == "sensitivity_missing"


def test_sealed_holdout_is_denied_for_every_operation():
    for operation in OPERATIONS:
        role = "approver" if operation == "decision_approval" else "operator"
        result = decide(_subject(), role, operation, _resource(source_role="sealed_holdout"))
        assert result["decision"] == "deny"
        assert result["reason"] == "sealed_holdout_forbidden"


def test_personal_export_requires_purpose_and_retention():
    result = decide(_subject(), "operator", "report_export", _resource(sensitivity="personal"))
    assert result["decision"] == "deny"
    assert result["reason"] == "personal_data_policy_required"
    allowed = decide(_subject(), "operator", "report_export", _resource(
        sensitivity="personal", purpose="support", retention="30 days"))
    assert allowed["decision"] == "allow"


def test_sensitive_data_requires_policy_and_import_downstream_use_is_checked():
    denied = decide(_subject(), "operator", "report_export", _resource(sensitivity="sensitive"))
    assert denied["decision"] == "deny"
    imported_for_validation = decide(_subject(), "operator", "import", _resource(sensitivity="sensitive"))
    assert imported_for_validation["decision"] == "allow"
    imported_for_binding = decide(_subject(), "operator", "import", _resource(
        sensitivity="sensitive", will_bind=True))
    assert imported_for_binding["decision"] == "deny"
    assert imported_for_binding["reason"] == "personal_data_policy_required"


def test_cross_scope_is_denied_and_record_is_audit_safe():
    result = decide(_subject(), "operator", "import", _resource(project_id="project-b"))
    assert result["decision"] == "deny"
    assert result["reason"] == "cross_scope"
    assert set(result) == {"subject_id", "policy_version", "decision", "resource_ids", "reason"}


def test_decision_approval_is_reserved_for_approver_role():
    resource = _resource(source_sensitivity="internal")
    for role in ("operator", "reader", "reviewer"):
        result = decide(_subject(), role, "decision_approval", resource)
        assert result["decision"] == "deny"
        assert result["reason"] == "role_not_permitted"
    allowed = decide(_subject(), "approver", "decision_approval", resource)
    assert allowed["decision"] == "allow"


def test_decision_outcome_operation_role_matrix():
    resource = {"project_id": "project-a", "resource_ids": ["d1"], "source_sensitivity": "internal"}
    for role, expected in (("operator", "allow"), ("reviewer", "allow"),
                           ("approver", "deny"), ("reader", "deny")):
        assert decide(_subject(), role, "decision_outcome", resource)["decision"] == expected
