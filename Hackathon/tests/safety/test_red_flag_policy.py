import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from clinical_triage.conversation import (
    ConversationConfig,
    QuestionSpec,
    offer_slot,
    reduce,
)
from clinical_triage.domain.conversation import (
    AnswerCorrected,
    AnswerRecorded,
    CallStarted,
    ConsentRecorded,
    Escalate,
    SessionPhase,
    SessionState,
)
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact, ClinicalState, FactSource, FactValue
from clinical_triage.domain.policy import PolicyBundle, PolicyReviewStatus
from clinical_triage.domain.scheduling import AvailabilitySnapshot
from clinical_triage.safety import (
    PolicyLoadError,
    SafetyPolicyEngine,
    canonical_checksum,
    load_policy_bundle,
)
from clinical_triage.scheduling import (
    SchedulingPolicy,
    SchedulingPolicyError,
    rank_appointment_options,
)

HACKATHON = Path(__file__).parents[2]
POLICY_PATH = HACKATHON / "config" / "policies" / "example-red-flags.json"
BUNDLE = load_policy_bundle(POLICY_PATH, allow_example_unreviewed=True)
ENGINE = SafetyPolicyEngine(BUNDLE)
RED_FLAGS = (
    "red_flag.chest_pain_now",
    "red_flag.trouble_breathing_now",
    "red_flag.new_confusion_or_one_sided_weakness",
    "red_flag.heavy_bleeding_now",
)


def fact(fact_id: str, value: FactValue, unit: str | None = None) -> ClinicalFact:
    return ClinicalFact(
        fact_id=fact_id, value=value, source=FactSource.CALLER, confirmed=True, unit_code=unit
    )


def state(*facts: ClinicalFact) -> ClinicalState:
    return ClinicalState(facts=facts)


def screened(**extra: Any) -> ClinicalState:
    facts = [fact(f, False) for f in RED_FLAGS]
    for key, value in extra.items():
        fact_id = key.replace("__", ".")
        if isinstance(value, tuple):
            facts.append(fact(fact_id, value[0], value[1]))
        else:
            facts.append(fact(fact_id, value))
    return state(*facts)


# --- bundle integrity and marking ---------------------------------------------------


def test_example_bundle_is_marked_and_checksummed() -> None:
    assert BUNDLE.review_status is PolicyReviewStatus.EXAMPLE_UNREVIEWED
    assert "EXAMPLE_UNREVIEWED" in BUNDLE.policy_id
    assert BUNDLE.approved_by is None
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert canonical_checksum(document) == BUNDLE.checksum_sha256
    assert all(
        (r.approved_script_id or "").startswith("EXAMPLE_UNREVIEWED")
        for r in BUNDLE.rules
        if r.disposition is Disposition.EMERGENCY
    )


def test_tampered_bundle_is_rejected(tmp_path: Path) -> None:
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document["rules"][0]["priority"] = 99
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="POLICY_CHECKSUM_MISMATCH"):
        load_policy_bundle(tampered, allow_example_unreviewed=True)


def test_unreviewed_bundle_is_refused_unless_explicitly_allowed() -> None:
    with pytest.raises(PolicyLoadError, match="POLICY_NOT_CLINICIAN_REVIEWED"):
        load_policy_bundle(POLICY_PATH, allow_example_unreviewed=False)


def _bundle(**changes: Any) -> PolicyBundle:
    document = BUNDLE.model_dump(mode="json")
    document.update(changes)
    return PolicyBundle.model_validate(document)


def test_unmarked_example_policy_and_scriptless_emergency_rules_are_refused() -> None:
    with pytest.raises(PolicyLoadError, match="EXAMPLE_POLICY_ID_MUST_BE_MARKED"):
        SafetyPolicyEngine(_bundle(policy_id="family-medicine"))
    rules = BUNDLE.model_dump(mode="json")["rules"]
    rules[0]["approved_script_id"] = None
    with pytest.raises(PolicyLoadError, match="EMERGENCY_RULE_REQUIRES_SCRIPT"):
        SafetyPolicyEngine(_bundle(rules=rules))


def test_example_content_makes_no_diagnostic_claims() -> None:
    raw = POLICY_PATH.read_text(encoding="utf-8").lower()
    for term in ("diagnos", "heart attack", "stroke", "infarction", "sepsis", "pneumonia", "safe"):
        assert term not in raw, term
    assert all(re.fullmatch(r"EX-[A-Z]+-\d{3}", r.rule_id) for r in BUNDLE.rules)


# --- emergency first ----------------------------------------------------------------


def test_nothing_known_fails_closed_and_screens_red_flags_first() -> None:
    evaluation = ENGINE.evaluate(state())
    assert evaluation.disposition is None
    assert evaluation.fail_closed_reason == "EMERGENCY_NOT_RULED_OUT"
    assert evaluation.next_required_fact_ids == RED_FLAGS


@pytest.mark.parametrize(
    ("flag", "rule"),
    list(zip(RED_FLAGS, ["EX-EMERG-00" + str(i) for i in range(1, 5)], strict=True)),
)
def test_any_red_flag_escalates_immediately_with_nothing_else_known(flag: str, rule: str) -> None:
    outcome = ENGINE(state(fact(flag, True)))
    assert outcome.evaluation.disposition is Disposition.EMERGENCY
    assert outcome.evaluation.matched_rule_ids == (rule,)
    assert outcome.escalation_script_id == "EXAMPLE_UNREVIEWED_SCRIPT_EMERGENCY_SERVICES"


def test_volunteered_red_flag_escalates_even_for_administrative_calls_and_invalid_facts() -> None:
    evaluation = ENGINE.evaluate(
        state(
            fact("call.reason", "MEDICATION_REFILL"),
            fact("symptom.measured_temperature", "hot"),
            fact("red_flag.heavy_bleeding_now", True),
        )
    )
    assert evaluation.disposition is Disposition.EMERGENCY


def test_one_unanswered_red_flag_blocks_ordinary_routing() -> None:
    facts = [fact(f, False) for f in RED_FLAGS[:3]] + [fact("call.reason", "ADMINISTRATIVE")]
    evaluation = ENGINE.evaluate(state(*facts))
    assert evaluation.fail_closed_reason == "EMERGENCY_NOT_RULED_OUT"
    assert evaluation.next_required_fact_ids == (RED_FLAGS[3],)


def test_integer_is_not_a_boolean_red_flag() -> None:
    evaluation = ENGINE.evaluate(state(fact("red_flag.chest_pain_now", 1)))
    assert evaluation.disposition is None
    assert "red_flag.chest_pain_now" in evaluation.next_required_fact_ids


# --- ordinary routing, adaptive requirements, fail closed ---------------------------


def test_reason_is_requested_after_screening() -> None:
    evaluation = ENGINE.evaluate(screened())
    assert evaluation.fail_closed_reason == "RULES_UNRESOLVED"
    assert evaluation.next_required_fact_ids[0] == "call.reason"


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        (
            {"call__reason": "SYMPTOM", "symptom__caller_rated_severity": "SEVERE"},
            Disposition.URGENT_SAME_DAY,
        ),
        (
            {
                "call__reason": "SYMPTOM",
                "symptom__caller_rated_severity": "MILD",
                "symptom__measured_temperature": (39.6, "Cel"),
            },
            Disposition.URGENT_SAME_DAY,
        ),
        (
            {
                "call__reason": "SYMPTOM",
                "symptom__caller_rated_severity": "MODERATE",
                "symptom__measured_temperature": (37.0, "Cel"),
            },
            Disposition.SOON,
        ),
        (
            {
                "call__reason": "SYMPTOM",
                "symptom__caller_rated_severity": "MILD",
                "symptom__measured_temperature": (37.0, "Cel"),
            },
            Disposition.ROUTINE,
        ),
        ({"call__reason": "FOLLOW_UP"}, Disposition.ROUTINE),
        ({"call__reason": "MEDICATION_REFILL"}, Disposition.ADMINISTRATIVE),
    ],
)
def test_ordinary_dispositions(extra: dict[str, Any], expected: Disposition) -> None:
    evaluation = ENGINE.evaluate(screened(**extra))
    assert evaluation.disposition is expected, evaluation


def test_higher_precedence_rule_must_be_resolved_before_lower_one_applies() -> None:
    evaluation = ENGINE.evaluate(
        screened(call__reason="SYMPTOM", symptom__caller_rated_severity="MILD")
    )
    assert evaluation.fail_closed_reason == "HIGHER_PRECEDENCE_RULE_UNRESOLVED"
    assert evaluation.next_required_fact_ids == ("symptom.measured_temperature",)


@pytest.mark.parametrize("temperature", [(39.6, None), (103.0, "[degF]"), ("39.6", "Cel")])
def test_unnormalized_measurements_fail_closed(temperature: tuple[Any, str | None]) -> None:
    evaluation = ENGINE.evaluate(
        screened(
            call__reason="SYMPTOM",
            symptom__caller_rated_severity="MILD",
            symptom__measured_temperature=temperature,
        )
    )
    assert evaluation.disposition is None
    assert evaluation.fail_closed_reason == "INVALID_FACT_VALUE"


def test_unrecognized_reason_matches_nothing_and_fails_closed() -> None:
    evaluation = ENGINE.evaluate(screened(call__reason="SOMETHING_ELSE"))
    assert evaluation.fail_closed_reason == "NO_RULE_MATCHED"
    assert evaluation.disposition is None


def test_tied_rules_that_disagree_fail_closed() -> None:
    rules = BUNDLE.model_dump(mode="json")["rules"]
    rules.append(
        {
            "rule_id": "EX-CONFLICT-001",
            "priority": 30,
            "disposition": "SOON",
            "all_of": [{"fact_id": "call.reason", "operator": "EQUALS", "value": "FOLLOW_UP"}],
        }
    )
    engine = SafetyPolicyEngine(_bundle(rules=rules))
    evaluation = engine.evaluate(screened(call__reason="FOLLOW_UP"))
    assert evaluation.fail_closed_reason == "CONFLICTING_RULES"


def test_undefined_facts_are_ignored_not_considered() -> None:
    evaluation = ENGINE.evaluate(screened(call__reason="FOLLOW_UP", unrelated__note="anything"))
    assert "unrelated.note" not in evaluation.considered_fact_ids
    assert evaluation.disposition is Disposition.ROUTINE


# --- determinism and audit trace ------------------------------------------------------


def test_evaluation_is_order_independent_and_repeatable() -> None:
    facts = list(screened(call__reason="SYMPTOM", symptom__caller_rated_severity="SEVERE").facts)
    forward = ENGINE.evaluate(state(*facts))
    backward = ENGINE.evaluate(state(*reversed(facts)))
    assert forward == backward == ENGINE.evaluate(state(*facts))
    assert forward.policy_checksum_sha256 == BUNDLE.checksum_sha256


def test_trace_names_every_rule_with_trigger_and_evidence() -> None:
    trace = ENGINE.trace(state(fact("red_flag.chest_pain_now", True)))
    assert [t.rule_id for t in trace][:4] == [
        "EX-EMERG-001",
        "EX-EMERG-002",
        "EX-EMERG-003",
        "EX-EMERG-004",
    ]
    assert len(trace) == len(BUNDLE.rules)
    first = trace[0]
    assert first.triggered and first.evidence_fact_ids == ("red_flag.chest_pain_now",)
    assert not any(t.triggered for t in trace[1:])


# --- emergency interrupts ordinary scheduling (with the reducer) ----------------------

QUESTIONS = ConversationConfig(
    questions=tuple(QuestionSpec(f"q.{d.fact_id}", d.fact_id) for d in BUNDLE.fact_definitions),
    consent_question_id="q.consent",
    accepted_consent_codes=frozenset({"CONSENT_GIVEN"}),
    scheduling_windows={
        Disposition.URGENT_SAME_DAY: "SAME_DAY",
        Disposition.SOON: "WITHIN_3_DAYS",
        Disposition.ROUTINE: "WITHIN_14_DAYS",
        Disposition.ADMINISTRATIVE: "NEXT_AVAILABLE",
    },
    fallback_emergency_script_id="EXAMPLE_UNREVIEWED_SCRIPT_EMERGENCY_SERVICES",
)


def test_red_flag_correction_interrupts_an_active_appointment_offer() -> None:
    session = SessionState(call_id="call-1")
    n = 0

    def step(event_cls: Any, **fields: Any) -> tuple[Any, ...]:
        nonlocal session, n
        n += 1
        transition = reduce(
            session,
            event_cls(
                event_id=f"e{n}", call_id="call-1", expected_state_version=session.version, **fields
            ),
            config=QUESTIONS,
            evaluate=ENGINE,
        )
        assert transition.accepted, transition.rejected_reason
        session = transition.state
        return transition.commands

    step(CallStarted)
    step(ConsentRecorded, consent_code="CONSENT_GIVEN")
    for flag in RED_FLAGS:
        step(AnswerRecorded, fact=fact(flag, False))
    commands = step(AnswerRecorded, fact=fact("call.reason", "FOLLOW_UP"))
    assert [c.kind for c in commands] == ["SEARCH_APPOINTMENTS"]
    session = offer_slot(session, slot_id="SLOT-SYN-OPEN-1", expected_version=session.version).state
    assert session.phase is SessionPhase.SLOT_OFFERED

    commands = step(
        AnswerCorrected, fact=fact("red_flag.chest_pain_now", True), replaces_event_id="e3"
    )
    assert commands == (
        Escalate(
            script_id="EXAMPLE_UNREVIEWED_SCRIPT_EMERGENCY_SERVICES",
            trigger_rule_ids=("EX-EMERG-001",),
        ),
    )
    final: SessionState = session
    assert final.phase in {SessionPhase.ESCALATE} and final.offered_slot_id is None


def test_scheduling_policy_refuses_emergency_disposition() -> None:
    policy = SchedulingPolicy.model_validate_json(
        (HACKATHON / "config" / "scheduling" / "example.json").read_text(encoding="utf-8")
    )
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    snapshot = AvailabilitySnapshot(
        snapshot_id="s", observed_at=now, expires_at=now.replace(hour=13), slots=()
    )
    with pytest.raises(SchedulingPolicyError, match="EMERGENCY_PROHIBITS_SCHEDULING"):
        rank_appointment_options(
            snapshot=snapshot, disposition=Disposition.EMERGENCY, policy=policy, now=now
        )
