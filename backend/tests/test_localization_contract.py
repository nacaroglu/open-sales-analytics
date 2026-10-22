from dataclasses import asdict

from app.api.module_common import _add_localization_metadata
from app.errors import ApiError, error_body
from app.localization import localized_reason, reason_code
from app.validation.result import Issue


def test_availability_and_comparison_objects_receive_codes_and_parameter_maps():
    body = _add_localization_metadata(
        {
            "availability": {"state": "available", "reason": None},
            "comparison": {
                "state": "unavailable",
                "reason": "A comparison needs at least two days of history.",
            },
        }
    )
    assert body["availability"] == {
        "state": "available",
        "reason": None,
        "reason_code": None,
        "reason_params": {},
    }
    assert body["comparison"]["reason_code"] == "comparison.needs_two_days"
    assert body["comparison"]["reason_params"] == {}


def test_validation_issues_and_error_envelopes_keep_english_and_add_params():
    issue = asdict(Issue(code="empty_file", reason="The file is empty."))
    assert issue["reason_params"] == {}
    assert issue["reason"] == "The file is empty."
    missing = asdict(
        Issue(code="missing_value", reason="A value is required for order_id.", field="order_id")
    )
    assert missing["reason_params"] == {"field": "order_id"}
    oversized = asdict(
        Issue(code="file_too_large", reason="The file is larger than the 50 MB limit.")
    )
    assert oversized["reason_params"] == {"limit": "50 MB"}
    assert error_body("invalid_request", "The request is not valid.") == {
        "error": {
            "code": "invalid_request",
            "message": "The request is not valid.",
            "message_params": {},
        }
    }
    error = ApiError(400, "invalid_request", "Bad {field}", message_params={"field": "start"})
    assert error.message_params == {"field": "start"}


def test_generated_reason_codes_are_dotted_semantic_identifiers():
    code = reason_code("A new stable English fallback sentence.")
    assert code == "availability.unknown"
    assert code is not None and "." in code


def test_known_availability_reasons_have_stable_codes_and_scalar_parameters():
    result = localized_reason(
        "Customer analytics needs a customer_id on at least 50% of orders; "
        "4 of 10 orders (40%) have one."
    )
    assert result == {
        "reason_code": "customers.coverage_below_threshold",
        "reason_params": {
            "minimum_coverage_percent": 50,
            "identified_orders": 4,
            "total_orders": 10,
            "coverage_percent": 40,
        },
    }
    assert localized_reason("A new message without a mapping.") == {
        "reason_code": "availability.unknown",
        "reason_params": {},
    }
