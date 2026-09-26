"""Build the structured TriageResult from session state and a policy outcome.

The result is a routing record, not a diagnosis. Confidence is always None:
no model score participates in routing.
"""

from clinical_triage.conversation.config import (
    ORDINARY_DISPOSITIONS,
    ConversationConfig,
    PolicyOutcome,
    QuestionKind,
)
from clinical_triage.domain.conversation import SessionState
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.triage import TriageResult

NO_RULE_EVIDENCE = "EMERGENCY_WITHOUT_RULE_EVIDENCE"


def build_triage_result(
    state: SessionState, outcome: PolicyOutcome, config: ConversationConfig
) -> TriageResult:
    evaluation = outcome.evaluation
    disposition = state.disposition or Disposition.HUMAN_REVIEW
    unanswered = tuple(
        question.question_id if question else f"FACT:{fact_id}"
        for fact_id in evaluation.next_required_fact_ids
        for question in (config.question_for(fact_id, QuestionKind.PRIMARY),)
    )
    if unanswered and disposition is not Disposition.EMERGENCY:
        disposition = Disposition.HUMAN_REVIEW

    recorded = {fact.fact_id for fact in state.clinical.facts}
    triggers = evaluation.matched_rule_ids
    red_flags: tuple[str, ...] = ()
    if disposition is Disposition.EMERGENCY:
        triggers = triggers or (NO_RULE_EVIDENCE,)
        red_flags = triggers

    if state.disposition is None and disposition is Disposition.HUMAN_REVIEW:
        rationale = "SESSION_INCOMPLETE"
    elif evaluation.fail_closed_reason and disposition is Disposition.HUMAN_REVIEW:
        rationale = f"FAIL_CLOSED_{evaluation.fail_closed_reason}"
    else:
        rationale = f"POLICY_ROUTED_{disposition.value}"

    return TriageResult(
        disposition=disposition,
        confidence=None,
        trigger_rule_ids=triggers,
        symptom_fact_ids=tuple(f for f in evaluation.considered_fact_ids if f in recorded),
        red_flag_ids=red_flags,
        unanswered_critical_question_ids=unanswered,
        recommended_scheduling_window=(
            config.scheduling_windows[disposition] if disposition in ORDINARY_DISPOSITIONS else None
        ),
        requires_human_review=disposition not in ORDINARY_DISPOSITIONS or bool(unanswered),
        rationale_code=rationale,
        policy_id=evaluation.policy_id,
        policy_version=evaluation.policy_version,
        policy_checksum_sha256=evaluation.policy_checksum_sha256,
    )
