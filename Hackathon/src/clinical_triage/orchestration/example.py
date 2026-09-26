"""EXAMPLE_UNREVIEWED orchestrator configuration for the example red-flag policy.

Every caller-facing string here is illustrative wording that no clinician,
compliance reviewer, or operator has approved. It exists so the synthetic demo
and tests exercise realistic, conversational prompts. Do not use it with real
callers. The question catalog mirrors the fact IDs in
`config/policies/example-red-flags.json`; the policy, not this file, decides
which of these questions is asked and in what order.
"""

from dataclasses import replace
from pathlib import Path

from clinical_triage.conversation import ConversationConfig, QuestionKind, QuestionSpec
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.voice import AgentSpec, FieldSpec, TransferTarget
from clinical_triage.orchestration.config import (
    IDENTITY_FIELD_KEYS,
    OrchestratorConfig,
    ParseKind,
    SchedulingWindow,
    VoiceQuestion,
)
from clinical_triage.safety import SafetyPolicyEngine, load_policy_bundle
from clinical_triage.scheduling import SchedulingPolicy

EXAMPLE_MARKER = "EXAMPLE_UNREVIEWED"
CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config"
EXAMPLE_POLICY_PATH = CONFIG_ROOT / "policies" / "example-red-flags.json"
EXAMPLE_SCHEDULING_PATH = CONFIG_ROOT / "scheduling" / "example.json"

EMERGENCY_TARGET = TransferTarget("EXAMPLE_EMERGENCY_HANDOFF", "Emergency handoff (example)")
HUMAN_REVIEW_TARGET = TransferTarget("EXAMPLE_TRIAGE_NURSE", "Triage nurse queue (example)")

WINDOW_SAME_DAY = "WINDOW_SAME_DAY"
WINDOW_SOON = "WINDOW_SOON"
WINDOW_ROUTINE = "WINDOW_ROUTINE"
WINDOW_ADMIN = "WINDOW_ADMIN"

EMERGENCY_SCRIPT_ID = "EXAMPLE_UNREVIEWED_SCRIPT_EMERGENCY_SERVICES"
FALLBACK_EMERGENCY_SCRIPT_ID = "EXAMPLE_UNREVIEWED_SCRIPT_EMERGENCY_FALLBACK"
CLOSE_SCRIPT_ID = "EXAMPLE_UNREVIEWED_SCRIPT_CLOSE_BOOKED"

_YES_NO = ("YES", "NO")


def _yes_no(question_id: str, fact_id: str, text: str) -> VoiceQuestion:
    field = FieldSpec(key=fact_id, field_type="multiple_choice", question=text, choices=_YES_NO)
    return VoiceQuestion(question_id, fact_id, field, ParseKind.YES_NO)


def example_questions() -> tuple[VoiceQuestion, ...]:
    """EXAMPLE_UNREVIEWED conversational wording for each policy fact."""

    return (
        _yes_no(
            "q.red_flag.chest_pain",
            "red_flag.chest_pain_now",
            "Before we go further, I need to check a few things. "
            "Are you having any chest pain or pressure right now?",
        ),
        _yes_no(
            "q.red_flag.breathing",
            "red_flag.trouble_breathing_now",
            "Okay. And are you having any trouble breathing right now?",
        ),
        _yes_no(
            "q.red_flag.neuro",
            "red_flag.new_confusion_or_one_sided_weakness",
            "Have you noticed any new confusion, or weakness or numbness on one side of your body?",
        ),
        _yes_no(
            "q.red_flag.bleeding",
            "red_flag.heavy_bleeding_now",
            "Is there any heavy bleeding happening right now?",
        ),
        VoiceQuestion(
            "q.call.reason",
            "call.reason",
            FieldSpec(
                key="call.reason",
                field_type="multiple_choice",
                question="Thanks for bearing with me. What can we help with today: a new "
                "symptom, a follow-up visit, a medication refill, or something administrative?",
                choices=("SYMPTOM", "FOLLOW_UP", "MEDICATION_REFILL", "ADMINISTRATIVE"),
            ),
            ParseKind.CHOICE,
        ),
        VoiceQuestion(
            "q.symptom.severity",
            "symptom.caller_rated_severity",
            FieldSpec(
                key="symptom.caller_rated_severity",
                field_type="multiple_choice",
                question="I'm sorry you're dealing with that. Would you call it mild, "
                "moderate, or severe?",
                choices=("MILD", "MODERATE", "SEVERE"),
            ),
            ParseKind.CHOICE,
        ),
        VoiceQuestion(
            "q.symptom.temperature",
            "symptom.measured_temperature",
            FieldSpec(
                key="symptom.measured_temperature",
                field_type="text",
                question="Have you been able to take your temperature? What did it read, "
                "in degrees Celsius?",
            ),
            ParseKind.NUMBER,
            unit_code="Cel",
            plausible_range=(34.0, 43.0),
        ),
        VoiceQuestion(
            "q.symptom.temperature.confirm",
            "symptom.measured_temperature",
            FieldSpec(
                key="symptom.measured_temperature.confirm",
                field_type="text",
                question="Just so I have it right: what was that reading in degrees Celsius?",
            ),
            ParseKind.NUMBER,
            unit_code="Cel",
            plausible_range=(34.0, 43.0),
        ),
    )


def example_conversation_config() -> ConversationConfig:
    questions = example_questions()
    return ConversationConfig(
        questions=tuple(
            QuestionSpec(
                q.question_id,
                q.fact_id,
                QuestionKind.CLARIFICATION
                if q.question_id.endswith(".confirm")
                else QuestionKind.PRIMARY,
            )
            for q in questions
        ),
        consent_question_id="q.consent",
        accepted_consent_codes=frozenset({"CONSENT_GIVEN"}),
        scheduling_windows={
            Disposition.URGENT_SAME_DAY: WINDOW_SAME_DAY,
            Disposition.SOON: WINDOW_SOON,
            Disposition.ROUTINE: WINDOW_ROUTINE,
            Disposition.ADMINISTRATIVE: WINDOW_ADMIN,
        },
        fallback_emergency_script_id=FALLBACK_EMERGENCY_SCRIPT_ID,
        close_script_id=CLOSE_SCRIPT_ID,
    )


def example_orchestrator_config(
    *, allow_booking_writes: bool = False, allow_record_writes: bool = False
) -> OrchestratorConfig:
    """Build the EXAMPLE_UNREVIEWED config. Writes stay disabled unless asked for."""

    config = OrchestratorConfig(
        agent=AgentSpec(
            name=None,
            organization="Synthetic Family Medicine (example)",
            purpose=f"{EXAMPLE_MARKER}: collect routing facts and help schedule; never diagnose.",
        ),
        conversation=example_conversation_config(),
        questions=example_questions(),
        consent_field=FieldSpec(
            key="consent.continue",
            field_type="multiple_choice",
            question="Is it okay if we continue?",
            choices=_YES_NO,
        ),
        consent_boundary_script=(
            "EXAMPLE_UNREVIEWED: I'm the clinic's automated assistant. I can ask a few "
            "questions, route your call, and help book a visit, but I can't give medical "
            "advice or a diagnosis. If this is an emergency, hang up and call your local "
            "emergency number."
        ),
        identity_fields=(
            FieldSpec(
                key=IDENTITY_FIELD_KEYS[0],
                question="Can I get your first name?",
                sensitive=True,
            ),
            FieldSpec(
                key=IDENTITY_FIELD_KEYS[1],
                question="And your last name?",
                sensitive=True,
            ),
            FieldSpec(
                key=IDENTITY_FIELD_KEYS[2],
                field_type="date",
                question="And your date of birth?",
                sensitive=True,
            ),
        ),
        windows={
            WINDOW_SAME_DAY: SchedulingWindow(0, 12 * 60),
            WINDOW_SOON: SchedulingWindow(0, 72 * 60),
            WINDOW_ROUTINE: SchedulingWindow(24 * 60, 21 * 24 * 60),
            WINDOW_ADMIN: SchedulingWindow(24 * 60, 21 * 24 * 60),
        },
        emergency_target=EMERGENCY_TARGET,
        human_review_target=HUMAN_REVIEW_TARGET,
        scripts={
            EMERGENCY_SCRIPT_ID: (
                "EXAMPLE_UNREVIEWED: What you've described needs emergency care right now. "
                "Please hang up and call your local emergency number immediately."
            ),
            FALLBACK_EMERGENCY_SCRIPT_ID: (
                "EXAMPLE_UNREVIEWED: Please hang up and call your local emergency number "
                "right away."
            ),
            CLOSE_SCRIPT_ID: (
                "EXAMPLE_UNREVIEWED: You're all set. The clinic will send the visit details. "
                "If anything gets worse before then, call back or seek emergency care."
            ),
        },
        question_deflection=(
            "EXAMPLE_UNREVIEWED: I'm not able to answer that, but I'll make sure the care "
            "team knows you asked."
        ),
        human_review_callback_script=(
            "EXAMPLE_UNREVIEWED: I couldn't connect you just now. A member of the care team "
            "will call you back. If anything gets worse, call your local emergency number."
        ),
        offer_prompt_template=(
            "EXAMPLE_UNREVIEWED: Offer the {kind} appointment starting {starts_at} and ask "
            "the caller to answer yes or no."
        ),
    )
    return replace(
        config, allow_booking_writes=allow_booking_writes, allow_record_writes=allow_record_writes
    )


def example_policy_engine(path: Path = EXAMPLE_POLICY_PATH) -> SafetyPolicyEngine:
    return SafetyPolicyEngine(load_policy_bundle(path, allow_example_unreviewed=True))


def example_scheduling_policy(path: Path = EXAMPLE_SCHEDULING_PATH) -> SchedulingPolicy:
    return SchedulingPolicy.model_validate_json(path.read_text(encoding="utf-8"))
