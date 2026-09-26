"""Deterministic emergency decision for the focused demo path."""

from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.triage import TriageResult


def _yes(value: object) -> bool:
    return str(value or "").strip().lower() in {"yes", "y", "true", "present"}


def evaluate_stroke_red_flag(
    *,
    right_arm_weakness: object,
    speech_abnormality: object,
) -> TriageResult:
    """Return an emergency only when both demo red-flag facts are affirmative."""

    weakness = _yes(right_arm_weakness)
    speech = _yes(speech_abnormality)
    if weakness and speech:
        return TriageResult(
            disposition=Disposition.EMERGENCY,
            confidence=None,
            trigger_rule_ids=("focal_neurologic_deficit",),
            symptom_fact_ids=("right_arm_weakness", "speech_abnormality"),
            red_flag_ids=("focal_neurologic_deficit",),
            requires_human_review=True,
            rationale_code="DEMO_FOCAL_NEUROLOGIC_DEFICIT",
            policy_id="synthetic-stroke-demo",
            policy_version="0.1.0-example",
            policy_checksum_sha256="0" * 64,
        )
    return TriageResult(
        disposition=Disposition.HUMAN_REVIEW,
        confidence=None,
        symptom_fact_ids=tuple(
            fact_id
            for fact_id, present in (
                ("right_arm_weakness", weakness),
                ("speech_abnormality", speech),
            )
            if present
        ),
        unanswered_critical_question_ids=tuple(
            fact_id
            for fact_id, present in (
                ("right_arm_weakness", weakness),
                ("speech_abnormality", speech),
            )
            if not present
        ),
        requires_human_review=True,
        rationale_code="DEMO_INCOMPLETE_RED_FLAG_SCREEN",
        policy_id="synthetic-stroke-demo",
        policy_version="0.1.0-example",
        policy_checksum_sha256="0" * 64,
    )
