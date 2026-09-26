"""Content-free test policy and config. These abstract rules are not clinical."""

from dataclasses import dataclass, field
from typing import Any

from clinical_triage.conversation import (
    ConversationConfig,
    PolicyOutcome,
    QuestionKind,
    QuestionSpec,
    Transition,
    reduce,
)
from clinical_triage.domain.conversation import (
    AnswerCorrected,
    AnswerRecorded,
    CallStarted,
    ConsentRecorded,
    DomainEvent,
    SessionState,
    TaskCompleted,
)
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact, ClinicalState, FactSource
from clinical_triage.domain.policy import PolicyEvaluation

CHECKSUM = "0" * 64
REQUIRED = ("fact.a", "fact.b")

CONFIG = ConversationConfig(
    questions=(
        QuestionSpec("q.a", "fact.a"),
        QuestionSpec("q.b", "fact.b"),
        QuestionSpec("q.a.clarify", "fact.a", QuestionKind.CLARIFICATION),
        QuestionSpec("q.flag", "fact.flag"),
    ),
    consent_question_id="q.consent",
    accepted_consent_codes=frozenset({"CONSENT_GIVEN"}),
    scheduling_windows={
        Disposition.URGENT_SAME_DAY: "WINDOW_SAME_DAY",
        Disposition.SOON: "WINDOW_SOON",
        Disposition.ROUTINE: "WINDOW_ROUTINE",
        Disposition.ADMINISTRATIVE: "WINDOW_ADMIN",
    },
    fallback_emergency_script_id="SCRIPT_FALLBACK",
)


@dataclass
class FakePolicy:
    """flag=True -> EMERGENCY; missing a/b -> fail closed; a=review -> HUMAN_REVIEW."""

    required: tuple[str, ...] = REQUIRED
    raise_error: bool = False
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, clinical: ClinicalState) -> PolicyOutcome:
        self.calls.append(tuple(f.fact_id for f in clinical.facts))
        if self.raise_error:
            raise RuntimeError("synthetic evaluator failure")
        present = {f.fact_id: f.value for f in clinical.facts}
        considered = tuple(sorted(k for k in present if k.startswith("fact.")))
        base: dict[str, Any] = {
            "policy_id": "test-policy",
            "policy_version": "0",
            "policy_checksum_sha256": CHECKSUM,
            "considered_fact_ids": considered,
        }
        if present.get("fact.flag") is True:
            evaluation = PolicyEvaluation(
                **base, matched_rule_ids=("TEST-EMERGENCY",), disposition=Disposition.EMERGENCY
            )
            return PolicyOutcome(evaluation, escalation_script_id="SCRIPT_TEST_EMERGENCY")
        missing = tuple(f for f in self.required if f not in present)
        if missing:
            evaluation = PolicyEvaluation(
                **base,
                matched_rule_ids=(),
                next_required_fact_ids=missing,
                fail_closed_reason="MISSING_REQUIRED_FACT",
            )
        elif present.get("fact.a") == "review":
            evaluation = PolicyEvaluation(
                **base, matched_rule_ids=("TEST-REVIEW",), disposition=Disposition.HUMAN_REVIEW
            )
        elif present.get("fact.a") == "conflict":
            evaluation = PolicyEvaluation(
                **base, matched_rule_ids=(), fail_closed_reason="CONFLICTING_RULES"
            )
        else:
            disposition = (
                Disposition.URGENT_SAME_DAY
                if present.get("fact.a") == "urgent"
                else Disposition.ROUTINE
            )
            evaluation = PolicyEvaluation(
                **base, matched_rule_ids=("TEST-ORDINARY",), disposition=disposition
            )
        return PolicyOutcome(evaluation)


def fact(fact_id: str, value: str | bool, confirmed: bool = True) -> ClinicalFact:
    return ClinicalFact(fact_id=fact_id, value=value, source=FactSource.CALLER, confirmed=confirmed)


class Session:
    """Drives the reducer with auto-numbered, correctly versioned events."""

    def __init__(self, policy: FakePolicy | None = None, call_id: str = "call-1") -> None:
        self.policy = policy or FakePolicy()
        self.state = SessionState(call_id=call_id)
        self.transitions: list[Transition] = []
        self._n = 0

    def _ids(self) -> dict[str, Any]:
        self._n += 1
        return {
            "event_id": f"e{self._n}",
            "call_id": self.state.call_id,
            "expected_state_version": self.state.version,
        }

    def apply(self, event: DomainEvent) -> Transition:
        transition = reduce(self.state, event, config=CONFIG, evaluate=self.policy)
        self.transitions.append(transition)
        self.state = transition.state
        return transition

    def start(self) -> Transition:
        return self.apply(CallStarted(**self._ids()))

    def consent(self, code: str = "CONSENT_GIVEN") -> Transition:
        return self.apply(ConsentRecorded(**self._ids(), consent_code=code))

    def answer(self, fact_id: str, value: str | bool, confirmed: bool = True) -> Transition:
        return self.apply(AnswerRecorded(**self._ids(), fact=fact(fact_id, value, confirmed)))

    def correct(self, fact_id: str, value: str | bool, confirmed: bool = True) -> Transition:
        return self.apply(
            AnswerCorrected(
                **self._ids(), fact=fact(fact_id, value, confirmed), replaces_event_id="prior"
            )
        )

    def complete(self, task_id: str) -> Transition:
        return self.apply(TaskCompleted(**self._ids(), task_id=task_id))

    def ready(self) -> "Session":
        self.start()
        self.consent()
        return self
