import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "conversation"))

from conversation_harness import CONFIG, Session  # noqa: E402

from clinical_triage.domain.disposition import Disposition  # noqa: E402
from clinical_triage.domain.triage import TriageResult  # noqa: E402
from clinical_triage.triage import build_triage_result  # noqa: E402


def result_for(session: Session) -> TriageResult:
    outcome = next(t.outcome for t in reversed(session.transitions) if t.outcome is not None)
    return build_triage_result(session.state, outcome, CONFIG)


def test_ordinary_result_recommends_window_and_has_no_confidence() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.b", "x")
    result = result_for(session)
    assert result.disposition is Disposition.ROUTINE
    assert result.recommended_scheduling_window == "WINDOW_ROUTINE"
    assert result.confidence is None
    assert not result.requires_human_review
    assert result.red_flag_ids == ()
    assert result.symptom_fact_ids == ("fact.a", "fact.b")
    assert result.rationale_code == "POLICY_ROUTED_ROUTINE"


def test_emergency_result_carries_rule_evidence_and_no_window() -> None:
    session = Session().ready()
    session.answer("fact.flag", True)
    result = result_for(session)
    assert result.disposition is Disposition.EMERGENCY
    assert result.trigger_rule_ids == ("TEST-EMERGENCY",) == result.red_flag_ids
    assert result.requires_human_review
    assert result.recommended_scheduling_window is None


def test_incomplete_session_is_human_review_with_unanswered_questions() -> None:
    session = Session().ready()
    result = result_for(session)
    assert result.disposition is Disposition.HUMAN_REVIEW
    assert result.unanswered_critical_question_ids == ("q.a", "q.b")
    assert result.requires_human_review
    assert result.rationale_code == "SESSION_INCOMPLETE"


def test_fail_closed_result_names_reason() -> None:
    session = Session().ready()
    session.answer("fact.b", "x")
    session.answer("fact.a", "conflict")
    result = result_for(session)
    assert result.disposition is Disposition.HUMAN_REVIEW
    assert result.rationale_code == "FAIL_CLOSED_CONFLICTING_RULES"
