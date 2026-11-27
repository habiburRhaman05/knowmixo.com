"""app/api_errors.py's RFC 9457 shape (ADR 007), for Day 9's public API."""
from app.api_errors import TYPE_BASE_URL, problem_detail


def test_minimal_shape_has_required_fields_only():
    body = problem_detail(404, "bot_not_found", "Assistant not found.", request_id="req-1")
    assert body == {
        "type": f"{TYPE_BASE_URL}/bot_not_found",
        "title": "Bot Not Found",
        "status": 404,
        "code": "bot_not_found",
        "message": "Assistant not found.",
        "request_id": "req-1",
    }


def test_retry_after_seconds_included_only_when_given():
    body = problem_detail(429, "rate_limited", "Slow down.", retry_after_seconds=60)
    assert body["retry_after_seconds"] == 60

    body_no_retry = problem_detail(404, "bot_not_found", "x")
    assert "retry_after_seconds" not in body_no_retry


def test_fields_included_only_when_given():
    body = problem_detail(422, "required_fields_missing", "x", fields=["email"])
    assert body["fields"] == ["email"]

    body_no_fields = problem_detail(422, "required_fields_missing", "x")
    assert "fields" not in body_no_fields
