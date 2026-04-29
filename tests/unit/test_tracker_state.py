import pytest

from shortlist.tracker.state import (
    InvalidStatusTransitionError,
    allowed_next,
    validate_transition,
)


def test_new_to_tailored_allowed():
    validate_transition("new", "tailored")  # no raise


def test_tailored_to_applied_allowed():
    validate_transition("tailored", "applied")


def test_applied_to_screen_allowed():
    validate_transition("applied", "screen")


def test_invalid_backwards_transition_raises():
    with pytest.raises(InvalidStatusTransitionError):
        validate_transition("applied", "new")


def test_invalid_skip_forward_raises():
    with pytest.raises(InvalidStatusTransitionError):
        validate_transition("new", "interview")


def test_withdrawn_allowed_from_any_non_terminal_state():
    for src in ("new", "tailored", "applied", "screen", "interview"):
        validate_transition(src, "withdrawn")


def test_terminal_states_have_no_transitions():
    assert allowed_next("offer") == set()
    assert allowed_next("rejected") == set()
    assert allowed_next("withdrawn") == set()


def test_allowed_next_listing():
    assert "tailored" in allowed_next("new")
    assert "applied" in allowed_next("tailored")
    assert "withdrawn" in allowed_next("new")
