"""F.1 minimal v1 trigger: pure regex, no DB/network, so this runs in
every quick test pass -- see app.chat.v1_escalation_trigger's docstring
for why it exists."""
from app.chat.v1_escalation_trigger import detect


def test_detects_safety_language_as_critical():
    severity, intent, _reason = detect("I'm thinking about suicide and don't know what to do")
    assert severity == "critical"
    assert intent == "emergency"


def test_detects_human_handoff_request_as_high():
    severity, intent, _reason = detect("I need to talk to a human right now, this is urgent")
    assert severity == "high"
    assert intent == "action"


def test_safety_wins_when_both_match():
    severity, _intent, _reason = detect("this is urgent, I want to kill myself")
    assert severity == "critical"


def test_ordinary_message_returns_none():
    assert detect("What are your opening hours?") is None


def test_cancel_requires_word_boundary_not_substring():
    # "cancellation" must not false-positive on "cancel my order"'s pattern
    assert detect("What's your cancellation policy?") is None
    assert detect("I want to cancel my order") is not None
