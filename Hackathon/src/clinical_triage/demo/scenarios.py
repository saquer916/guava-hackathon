"""Deterministic synthetic demo scenarios. Every caller, answer, and slot is invented.

Caller lines are display-only illustrations of what a synthetic caller might
say; the structured values next to them are what the voice layer would hand
to the orchestrator. The policy and all agent wording are EXAMPLE_UNREVIEWED.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from clinical_triage.audit import InMemoryAuditSink
from clinical_triage.demo.driver import (
    AdvanceClock,
    DriveResult,
    RelayCorrection,
    Say,
    ScenarioDriver,
    Step,
)
from clinical_triage.domain.facts import ClinicalFact, FactSource
from clinical_triage.domain.voice import FieldValue
from clinical_triage.fixtures import FIXTURE_CLOCK, FixedClock, SyntheticEHR, build_fixtures
from clinical_triage.orchestration import CallContext, CallOrchestrator, offer_field_key
from clinical_triage.orchestration.example import (
    EMERGENCY_TARGET,
    HUMAN_REVIEW_TARGET,
    example_orchestrator_config,
    example_policy_engine,
    example_scheduling_policy,
)

ACCEPT_TRANSFERS: Mapping[str, str | None] = {
    EMERGENCY_TARGET.target_id: None,
    HUMAN_REVIEW_TARGET.target_id: None,
}
EHR_BACKEND = "SyntheticEHR (offline synthetic fixtures; not OpenEMR)"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    summary: str
    synthetic_patient_id: str | None
    steps: tuple[Step, ...]
    booked_slot_ids: Mapping[str, str] = field(default_factory=dict)
    slots_taken_after_snapshot: frozenset[str] = frozenset()
    unavailable_operations: frozenset[str] = frozenset()
    transfer_outcomes: Mapping[str, str | None] = field(default_factory=lambda: ACCEPT_TRANSFERS)
    allow_booking_writes: bool = True
    allow_record_writes: bool = True


@dataclass
class ScenarioRun:
    scenario: Scenario
    drive: DriveResult
    ctx: CallContext
    ehr: SyntheticEHR
    audit: InMemoryAuditSink
    clock: FixedClock
    ehr_backend: str = EHR_BACKEND


def run_scenario(scenario: Scenario, *, audit: InMemoryAuditSink | None = None) -> ScenarioRun:
    clock = FixedClock(FIXTURE_CLOCK)
    ehr = SyntheticEHR(
        fixtures=build_fixtures(),
        clock=clock,
        unavailable_operations=scenario.unavailable_operations,
        slots_taken_after_snapshot=scenario.slots_taken_after_snapshot,
        booked_slot_ids=dict(scenario.booked_slot_ids),
    )
    sink = audit or InMemoryAuditSink()
    orchestrator = CallOrchestrator(
        config=example_orchestrator_config(
            allow_booking_writes=scenario.allow_booking_writes,
            allow_record_writes=scenario.allow_record_writes,
        ),
        policy=example_policy_engine(),
        scheduling_policy=example_scheduling_policy(),
        ehr=ehr,
        audit=sink,
        clock=clock,
    )
    call_id = f"demo-{scenario.scenario_id}"
    drive = ScenarioDriver(orchestrator, clock, scenario.transfer_outcomes).run(
        call_id, scenario.steps
    )
    return ScenarioRun(scenario, drive, orchestrator.calls[call_id], ehr, sink, clock)


# --- step helpers -----------------------------------------------------------------


def say(task_id: str, key: str, value: FieldValue, line: str = "") -> Say:
    return Say(task_id, {key: value}, line)


CONSENT = say("q.consent", "consent.continue", "YES", "Sure, that's fine.")


def screening(
    *, chest: str = "NO", breathing: str = "NO", neuro: str = "NO", bleeding: str = "NO"
) -> tuple[Say, ...]:
    steps = (
        say("q.red_flag.chest_pain", "red_flag.chest_pain_now", chest, _yn(chest)),
        say("q.red_flag.breathing", "red_flag.trouble_breathing_now", breathing, _yn(breathing)),
        say(
            "q.red_flag.neuro",
            "red_flag.new_confusion_or_one_sided_weakness",
            neuro,
            _yn(neuro),
        ),
        say("q.red_flag.bleeding", "red_flag.heavy_bleeding_now", bleeding, _yn(bleeding)),
    )
    stop = next((i for i, s in enumerate(steps) if "YES" in s.values.values()), len(steps) - 1)
    return steps[: stop + 1]


def reason(value: str, line: str) -> Say:
    return say("q.call.reason", "call.reason", value, line)


def severity(value: str, line: str) -> Say:
    return say("q.symptom.severity", "symptom.caller_rated_severity", value, line)


def identity(given: str, family: str, birth_date: str) -> Say:
    return Say(
        "identity",
        {
            "identity.given_name": given,
            "identity.family_name": family,
            "identity.birth_date": birth_date,
        },
        f"It's {given} {family}, born {birth_date}.",
    )


def accept(task_id: str = "offer", value: str = "YES", line: str = "Yes, that works.") -> Say:
    return say(task_id, offer_field_key(task_id), value, line)


def _yn(value: str) -> str:
    return "Yes, actually." if value == "YES" else "No."


CHEST_PAIN_NOW = ClinicalFact(
    fact_id="red_flag.chest_pain_now", value=True, source=FactSource.CALLER, confirmed=True
)

# --- scenarios ----------------------------------------------------------------------

ROUTINE = Scenario(
    scenario_id="routine",
    title="1. Routine request",
    summary="Follow-up visit; no symptom questions are asked; routine slot booked.",
    synthetic_patient_id="SYN-PAT-A",
    steps=(
        CONSENT,
        *screening(),
        reason("FOLLOW_UP", "I just need my regular follow-up visit."),
        identity("Avery", "Synthetic", "1980-01-02"),
        accept(),
    ),
)

ADAPTIVE_CLARIFICATION = Scenario(
    scenario_id="adaptive-clarification",
    title="2. Adaptive clarification",
    summary="Mild symptom adds a temperature question; an implausible reading is "
    "clarified once and the corrected value decides the route.",
    synthetic_patient_id="SYN-PAT-B",
    steps=(
        CONSENT,
        *screening(),
        reason("SYMPTOM", "I've had a sore throat and I feel run down."),
        severity("MILD", "Pretty mild, honestly."),
        say(
            "q.symptom.temperature",
            "symptom.measured_temperature",
            "103",
            "It said one-oh-three.",
        ),
        say(
            "q.symptom.temperature.confirm",
            "symptom.measured_temperature.confirm",
            "38.4",
            "Oh, in Celsius it was about thirty-eight point four.",
        ),
        identity("Blake", "Synthetic", "1975-03-04"),
        accept(),
    ),
)

URGENT_SAME_DAY = Scenario(
    scenario_id="urgent-same-day",
    title="3. Urgent same-day",
    summary="Severe symptom routes to URGENT_SAME_DAY and books the same-day slot.",
    synthetic_patient_id="SYN-PAT-C",
    steps=(
        CONSENT,
        *screening(),
        reason("SYMPTOM", "I've had bad stomach pain since yesterday."),
        severity("SEVERE", "It's really bad, the worst I've had."),
        identity("Casey", "Synthetic", "1990-05-06"),
        accept(),
    ),
)

EMERGENCY_INTERRUPTION = Scenario(
    scenario_id="emergency-interruption",
    title="4. Emergency interruption mid-offer",
    summary="Ordinary scheduling reaches an offer; a relayed red-flag correction fires an "
    "emergency rule, withdraws the offer, and escalates. No booking, no further EHR call.",
    synthetic_patient_id="SYN-PAT-D",
    steps=(
        CONSENT,
        *screening(),
        reason("SYMPTOM", "I've had a cough for a few days."),
        severity("MODERATE", "Moderate, I guess."),
        say(
            "q.symptom.temperature",
            "symptom.measured_temperature",
            "38.0",
            "Thirty-eight this morning.",
        ),
        identity("Drew", "Synthetic", "1968-07-08"),
        RelayCorrection(
            CHEST_PAIN_NOW, "Wait, actually, I'm starting to get chest pain right now."
        ),
    ),
)

EMERGENCY_AT_SCREENING = Scenario(
    scenario_id="emergency-at-screening",
    title="4b. Emergency during screening",
    summary="A red flag during screening escalates before any EHR call.",
    synthetic_patient_id=None,
    steps=(CONSENT, *screening(breathing="YES")),
)

HUMAN_REVIEW_FALLBACK = Scenario(
    scenario_id="human-review-fallback",
    title="5. Human-review fallback",
    summary="A critical fact cannot be collected; it is not asked twice and the call is "
    "handed to the triage nurse queue.",
    synthetic_patient_id="SYN-PAT-E",
    steps=(
        CONSENT,
        *screening(),
        reason("SYMPTOM", "I've been feeling feverish."),
        severity("MODERATE", "Moderate."),
        say(
            "q.symptom.temperature",
            "symptom.measured_temperature",
            "no thermometer",
            "I don't have a thermometer.",
        ),
    ),
)

SCHEDULING_FAILURE = Scenario(
    scenario_id="scheduling-failure",
    title="6. Scheduling failure / stale availability",
    summary="The first confirmation arrives after the offer expired; one retry re-offers, "
    "but the slot was taken after the snapshot; the booking goes to staff.",
    synthetic_patient_id="SYN-PAT-F",
    slots_taken_after_snapshot=frozenset({"SLOT-SYN-SAME-DAY-1"}),
    steps=(
        CONSENT,
        *screening(),
        reason("SYMPTOM", "My ear has been hurting a lot."),
        severity("SEVERE", "Severe."),
        identity("Finley", "Synthetic", "1995-11-12"),
        AdvanceClock(seconds=400),
        accept(line="Sorry, I got distracted. Yes."),
        accept("offer_retry", line="Yes, please book it."),
    ),
)

SCHEDULE_SQUEEZE = Scenario(
    scenario_id="schedule-squeeze",
    title="7. Schedule squeeze",
    summary="Urgent need, no normal same-day slot: an alternative provider is offered and "
    "overbook review is surfaced to staff. Nothing is force-booked.",
    synthetic_patient_id="SYN-PAT-C",
    booked_slot_ids={"SLOT-SYN-SAME-DAY-1": "SYN-PAT-X", "SLOT-SYN-CANCEL-1": "SYN-PAT-X"},
    steps=(
        CONSENT,
        *screening(),
        reason("SYMPTOM", "I've had bad stomach pain since yesterday."),
        severity("SEVERE", "Severe."),
        identity("Casey", "Synthetic", "1990-05-06"),
        accept(line="A different doctor is fine. Yes."),
    ),
)

IDENTITY_UNCERTAIN = Scenario(
    scenario_id="identity-uncertain",
    title="8. Uncertain identity",
    summary="Same name as two synthetic patients (A and G) with a birth date matching "
    "neither: no record is chosen and the call goes to human review.",
    synthetic_patient_id=None,
    steps=(
        CONSENT,
        *screening(),
        reason("FOLLOW_UP", "I need to schedule my follow-up."),
        identity("Avery", "Synthetic", "1980-12-13"),
    ),
)

SCENARIOS: tuple[Scenario, ...] = (
    ROUTINE,
    ADAPTIVE_CLARIFICATION,
    URGENT_SAME_DAY,
    EMERGENCY_INTERRUPTION,
    EMERGENCY_AT_SCREENING,
    HUMAN_REVIEW_FALLBACK,
    SCHEDULING_FAILURE,
    SCHEDULE_SQUEEZE,
    IDENTITY_UNCERTAIN,
)


def scenario(scenario_id: str) -> Scenario:
    for candidate in SCENARIOS:
        if candidate.scenario_id == scenario_id:
            return candidate
    raise KeyError(scenario_id)
