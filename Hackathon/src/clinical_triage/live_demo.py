"""THROWAWAY callable demo agent (branch `demo/live-hack`). Not the reviewed architecture.

A minimal Guava agent with three tasks:

1. consent + four red-flag yes/no questions, then the EXAMPLE_UNREVIEWED
   `SafetyPolicyEngine`; EMERGENCY hangs up with an emergency script and
   never schedules;
2. reason for call, severity, temperature, then the policy again;
3. offer the first ranked slot from the synthetic fixtures, confirm, hang up.

Boundaries: synthetic only; no transfer; no EHR or booking write (the
"confirmation" is spoken only); no identity lookup; caller answers are never
logged. Every caller-facing string is EXAMPLE_UNREVIEWED. The reviewed path is
`clinical_triage.orchestration` (Fleet task #10), which this file does not use.

Run: `python -m clinical_triage.live_demo --chat` or `--phone` from `Hackathon/`,
with GUAVA_API_KEY (and GUAVA_AGENT_NUMBER for phone) in `Hackathon/.env`.
"""

import argparse
import logging
import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import guava

from clinical_triage.conversation.config import PolicyOutcome
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact, ClinicalState, FactSource, FactValue
from clinical_triage.domain.scheduling import AppointmentOffer
from clinical_triage.fixtures import FixedClock, SyntheticEHR, build_fixtures
from clinical_triage.safety import SafetyPolicyEngine, load_policy_bundle
from clinical_triage.scheduling import (
    SchedulingPolicy,
    SchedulingPolicyError,
    rank_appointment_options,
)

logger = logging.getLogger("clinical_triage.live_demo")

HACKATHON_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = HACKATHON_DIR / ".env"
POLICY_PATH = HACKATHON_DIR / "config" / "policies" / "example-red-flags.json"
SCHEDULING_PATH = HACKATHON_DIR / "config" / "scheduling" / "example.json"

SCREENING_TASK, DETAILS_TASK, OFFER_TASK = "screening", "details", "offer"
CONSENT_KEY, OFFER_KEY = "consent", "offer_accept"
REASON_KEY = "call.reason"
SEVERITY_KEY = "symptom.caller_rated_severity"
TEMPERATURE_KEY = "symptom.measured_temperature"
PLAUSIBLE_CELSIUS = (34.0, 43.0)

RED_FLAGS: tuple[tuple[str, str], ...] = (
    ("red_flag.chest_pain_now", "Are you having any chest pain or pressure right now?"),
    ("red_flag.trouble_breathing_now", "Are you having any trouble breathing right now?"),
    (
        "red_flag.new_confusion_or_one_sided_weakness",
        "Have you noticed any new confusion, or weakness or numbness on one side of your body?",
    ),
    ("red_flag.heavy_bleeding_now", "Is there any heavy bleeding happening right now?"),
)

# Minutes from call start; same example windows as the reviewed orchestrator config.
WINDOWS: dict[Disposition, tuple[int, int]] = {
    Disposition.URGENT_SAME_DAY: (0, 12 * 60),
    Disposition.SOON: (0, 72 * 60),
    Disposition.ROUTINE: (24 * 60, 21 * 24 * 60),
    Disposition.ADMINISTRATIVE: (24 * 60, 21 * 24 * 60),
}

PURPOSE = (
    "EXAMPLE_UNREVIEWED synthetic demo: a clinic's automated assistant that asks a few "
    "routing questions and offers an appointment. Never give medical advice or a diagnosis."
)
CONSENT_SCRIPT = (
    "EXAMPLE_UNREVIEWED: Hi, this is the clinic's automated assistant, a demo line. I can "
    "ask a few questions and offer an appointment, but I can't give medical advice. If this "
    "is an emergency, hang up and call your local emergency number."
)
EMERGENCY_SCRIPT = (
    "EXAMPLE_UNREVIEWED: What you've described needs emergency care right now. Please hang "
    "up and call your local emergency number immediately. Do not wait for an appointment."
)
SAFETY_CALLBACK_SCRIPT = (
    "EXAMPLE_UNREVIEWED: I wasn't able to finish the safety questions. If you have chest "
    "pain, trouble breathing, new confusion or weakness, or heavy bleeding, call your local "
    "emergency number now. Otherwise the care team will call you back."
)
DECLINED_SCRIPT = (
    "EXAMPLE_UNREVIEWED: No problem. The care team can help you directly. If this is an "
    "emergency, please call your local emergency number."
)
CALLBACK_SCRIPT = (
    "EXAMPLE_UNREVIEWED: Thanks. I'd like a member of the care team to follow up with you "
    "directly, so someone will call you back. If anything gets worse, call your local "
    "emergency number."
)
NO_SLOT_SCRIPT = (
    "EXAMPLE_UNREVIEWED: I don't see an opening that fits right now, so the scheduling team "
    "will call you back to find a time. If anything gets worse, call your local emergency "
    "number."
)
DECLINED_OFFER_SCRIPT = (
    "EXAMPLE_UNREVIEWED: No problem. The scheduling team will call you back to find another "
    "time. If anything gets worse, call your local emergency number."
)
CONFIRMED_SCRIPT = (
    "EXAMPLE_UNREVIEWED: Great, I've noted {when} for you. This is a demo line, so nothing "
    "was booked in a real system. If anything gets worse before then, call your local "
    "emergency number."
)
FAILURE_SCRIPT = (
    "EXAMPLE_UNREVIEWED: Sorry, something went wrong on my end. The care team will call you "
    "back. If this is an emergency, hang up and call your local emergency number."
)
DEFLECTION = (
    "EXAMPLE_UNREVIEWED: I'm not able to answer that, but the care team can help with it "
    "when they follow up."
)


class CallLike(Protocol):
    """The documented `guava.Call` surface this demo uses (also met by MockCall)."""

    @property
    def id(self) -> Any: ...

    def set_task(self, task_id: str, *, objective: str, checklist: list[Any]) -> None: ...

    def get_field(self, key: str) -> Any: ...

    def hangup(self, final_instructions: str = "") -> None: ...


@dataclass
class CallState:
    clinical: ClinicalState = field(default_factory=ClinicalState)
    offer: AppointmentOffer | None = None
    outcome_codes: list[str] = field(default_factory=list)


def _yes_no(key: str, question: str, *, required: bool = True, description: str = "") -> Any:
    return guava.Field(
        key=key,
        field_type="multiple_choice",
        question=question,
        description=description,
        choices=["YES", "NO"],
        required=required,
    )


def _choice(raw: Any, choices: Sequence[str]) -> str | None:
    text = str(raw).strip().upper() if raw is not None else ""
    return text if text in choices else None


def parse_celsius(raw: Any) -> float | None:
    """A plausible Celsius reading, or None (unparseable, missing, or likely Fahrenheit)."""

    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(str(raw).strip().rstrip("CcFf° ").strip())
    except ValueError:
        return None
    low, high = PLAUSIBLE_CELSIUS
    return value if math.isfinite(value) and low <= value <= high else None


def spoken_time(moment: datetime, offset_hours: float, label: str) -> str:
    local = moment.astimezone(timezone(timedelta(hours=offset_hours)))
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{local:%A}, {local:%B} {local.day} at {hour}:{local:%M} {suffix} {label}".strip()


class DemoLogic:
    """Handler logic, free of Guava network objects so it runs against MockCall."""

    def __init__(
        self,
        *,
        policy: Callable[[ClinicalState], PolicyOutcome],
        scheduling_policy: SchedulingPolicy,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        utc_offset_hours: float = -4.0,
        time_label: str = "Eastern",
    ) -> None:
        self._policy = policy
        self._scheduling = scheduling_policy
        self._now = now
        self._offset = utc_offset_hours
        self._label = time_label
        self.calls: dict[str, CallState] = {}

    # --- Guava callbacks ------------------------------------------------------------

    def on_call_start(self, call: CallLike) -> None:
        self._guard(call, self._start)

    def on_screening_complete(self, call: CallLike) -> None:
        self._guard(call, self._screening_complete)

    def on_details_complete(self, call: CallLike) -> None:
        self._guard(call, self._details_complete)

    def on_offer_complete(self, call: CallLike) -> None:
        self._guard(call, self._offer_complete)

    def on_question(self, call: CallLike, question: str) -> str:
        # The caller's words are deliberately neither logged nor interpreted.
        return DEFLECTION

    def on_session_end(self, call: CallLike, event: Any) -> None:
        state = self.calls.pop(str(call.id), None)
        codes = ",".join(state.outcome_codes) if state else "-"
        logger.info("session ended; outcome codes: %s", codes)

    # --- steps ------------------------------------------------------------------------

    def _start(self, call: CallLike) -> None:
        self.calls[str(call.id)] = CallState()
        call.set_task(
            SCREENING_TASK,
            objective=(
                "Explain the call boundary, ask for consent to continue, then ask all four "
                "safety questions one at a time in a warm, conversational way. If the caller "
                "declines to continue, stop and complete the task. Never give medical advice."
            ),
            checklist=[
                guava.Say(CONSENT_SCRIPT),  # type: ignore[no-untyped-call]
                _yes_no(CONSENT_KEY, "Is it okay if we continue?"),
                *(
                    _yes_no(
                        key,
                        question,
                        required=False,
                        description="Ask only if the caller agreed to continue.",
                    )
                    for key, question in RED_FLAGS
                ),
            ],
        )

    def _screening_complete(self, call: CallLike) -> None:
        state = self._state(call)
        answers = {key: _choice(call.get_field(key), ("YES", "NO")) for key, _ in RED_FLAGS}
        facts = [self._fact(key, value == "YES") for key, value in answers.items() if value]
        state.clinical = ClinicalState(facts=tuple(facts))
        outcome = self._policy(state.clinical)
        # Emergency wins even if consent was declined or answers are incomplete.
        if self._escalated(call, state, outcome):
            return
        if _choice(call.get_field(CONSENT_KEY), ("YES", "NO")) != "YES":
            self._finish(call, state, "CONSENT_DECLINED", DECLINED_SCRIPT)
            return
        if any(value is None for value in answers.values()):
            self._finish(call, state, "RED_FLAGS_INCOMPLETE", SAFETY_CALLBACK_SCRIPT)
            return
        call.set_task(
            DETAILS_TASK,
            objective=(
                "Find out why the caller is calling, conversationally. Only ask follow-ups "
                "that apply. Never give medical advice or a diagnosis."
            ),
            checklist=[
                guava.Field(
                    key=REASON_KEY,
                    field_type="multiple_choice",
                    question="Thanks. What can we help with today: a new symptom, a "
                    "follow-up visit, a medication refill, or something administrative?",
                    choices=["SYMPTOM", "FOLLOW_UP", "MEDICATION_REFILL", "ADMINISTRATIVE"],
                    required=True,
                ),
                guava.Field(
                    key=SEVERITY_KEY,
                    field_type="multiple_choice",
                    question="I'm sorry you're dealing with that. Would you call it mild, "
                    "moderate, or severe?",
                    description="Ask only if the reason is a new symptom.",
                    choices=["MILD", "MODERATE", "SEVERE"],
                    required=False,
                ),
                guava.Field(
                    key=TEMPERATURE_KEY,
                    field_type="text",
                    question="Have you taken your temperature? What did it read, in "
                    "degrees Celsius?",
                    description=(
                        "Ask only if the reason is a new symptom and severity is mild or "
                        "moderate. Record only the number in Celsius; leave empty if they "
                        "have not measured it."
                    ),
                    required=False,
                ),
            ],
        )

    def _details_complete(self, call: CallLike) -> None:
        state = self._state(call)
        facts = list(state.clinical.facts)
        reason = _choice(
            call.get_field(REASON_KEY),
            ("SYMPTOM", "FOLLOW_UP", "MEDICATION_REFILL", "ADMINISTRATIVE"),
        )
        severity = _choice(call.get_field(SEVERITY_KEY), ("MILD", "MODERATE", "SEVERE"))
        temperature = parse_celsius(call.get_field(TEMPERATURE_KEY))
        if reason:
            facts.append(self._fact(REASON_KEY, reason))
        if severity:
            facts.append(self._fact(SEVERITY_KEY, severity))
        if temperature is not None:
            facts.append(self._fact(TEMPERATURE_KEY, temperature, unit="Cel"))
        state.clinical = ClinicalState(facts=tuple(facts))
        outcome = self._policy(state.clinical)
        if self._escalated(call, state, outcome):
            return
        disposition = outcome.evaluation.disposition
        if disposition not in WINDOWS:
            reason_code = outcome.evaluation.fail_closed_reason or "HUMAN_REVIEW"
            self._finish(call, state, f"HUMAN_REVIEW:{reason_code}", CALLBACK_SCRIPT)
            return
        assert disposition is not None
        state.outcome_codes.append(f"DISPOSITION:{disposition.value}")
        offer = self._first_offer(disposition)
        if offer is None:
            self._finish(call, state, "NO_SLOT", NO_SLOT_SCRIPT)
            return
        state.offer = offer
        when = spoken_time(offer.slot.starts_at, self._offset, self._label)
        call.set_task(
            OFFER_TASK,
            objective=f"Offer one appointment, {when}, and ask whether it works.",
            checklist=[
                guava.Say(f"EXAMPLE_UNREVIEWED: I have an opening {when}."),  # type: ignore[no-untyped-call]
                _yes_no(OFFER_KEY, "Does that time work for you?"),
            ],
        )

    def _offer_complete(self, call: CallLike) -> None:
        state = self._state(call)
        if state.offer is None:
            self._finish(call, state, "NO_ACTIVE_OFFER", CALLBACK_SCRIPT)
            return
        if _choice(call.get_field(OFFER_KEY), ("YES", "NO")) != "YES":
            self._finish(call, state, "OFFER_DECLINED", DECLINED_OFFER_SCRIPT)
            return
        when = spoken_time(state.offer.slot.starts_at, self._offset, self._label)
        self._finish(call, state, "OFFER_CONFIRMED_SPOKEN_ONLY", CONFIRMED_SCRIPT.format(when=when))

    # --- helpers ----------------------------------------------------------------------

    def _first_offer(self, disposition: Disposition) -> AppointmentOffer | None:
        # Re-anchor the synthetic slot offsets at call time so offers are near-future.
        anchor = self._now().replace(minute=0, second=0, microsecond=0)
        clock = FixedClock(anchor)
        fixtures = build_fixtures().model_copy(update={"clock": anchor})
        ehr = SyntheticEHR(fixtures=fixtures, clock=clock)
        earliest, latest = WINDOWS[disposition]
        snapshot = ehr.get_available_appointments(
            earliest=anchor + timedelta(minutes=earliest),
            latest=anchor + timedelta(minutes=latest),
            constraint_codes=(),
        )
        try:
            options = rank_appointment_options(
                snapshot=snapshot, disposition=disposition, policy=self._scheduling, now=anchor
            )
        except SchedulingPolicyError:
            return None
        offers = options.normal_availability + options.alternative_availability
        return offers[0] if offers else None

    def _escalated(self, call: CallLike, state: CallState, outcome: PolicyOutcome) -> bool:
        if outcome.evaluation.disposition is not Disposition.EMERGENCY:
            return False
        rules = ",".join(outcome.evaluation.matched_rule_ids)
        logger.warning("EMERGENCY rule(s) fired: %s; scheduling stopped", rules)
        state.offer = None
        self._finish(call, state, f"EMERGENCY:{rules}", EMERGENCY_SCRIPT)
        return True

    def _finish(self, call: CallLike, state: CallState, code: str, script: str) -> None:
        state.outcome_codes.append(code)
        logger.info("call outcome: %s", code)
        call.hangup(script)

    def _state(self, call: CallLike) -> CallState:
        return self.calls.setdefault(str(call.id), CallState())

    @staticmethod
    def _fact(fact_id: str, value: FactValue, unit: str | None = None) -> ClinicalFact:
        return ClinicalFact(
            fact_id=fact_id, value=value, source=FactSource.CALLER, confirmed=True, unit_code=unit
        )

    def _guard(self, call: CallLike, step: Callable[[CallLike], None]) -> None:
        try:
            step(call)
        except Exception as exc:  # noqa: BLE001 - never let caller data reach SDK telemetry
            logger.error("handler failed: %s", type(exc).__name__)
            try:
                call.hangup(FAILURE_SCRIPT)
            except Exception as hangup_exc:  # noqa: BLE001
                logger.error("fail-safe hangup failed: %s", type(hangup_exc).__name__)


def build_logic() -> DemoLogic:
    return DemoLogic(
        policy=SafetyPolicyEngine(load_policy_bundle(POLICY_PATH, allow_example_unreviewed=True)),
        scheduling_policy=SchedulingPolicy.model_validate_json(
            SCHEDULING_PATH.read_text(encoding="utf-8")
        ),
        utc_offset_hours=float(os.environ.get("DEMO_UTC_OFFSET_HOURS", "-4")),
        time_label=os.environ.get("DEMO_TIME_LABEL", "Eastern"),
    )


def load_env_file(path: Path) -> list[str]:
    """Load KEY=VALUE lines into os.environ without overriding; returns key names only."""

    loaded: list[str] = []
    if not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def missing_settings(mode: str) -> list[str]:
    required = ["GUAVA_API_KEY"] + (["GUAVA_AGENT_NUMBER"] if mode == "phone" else [])
    return [name for name in required if not os.environ.get(name, "").strip()]


def build_agent(logic: DemoLogic) -> Any:
    """Constructs a real guava.Agent. This authenticates to Guava; never call it in tests."""

    agent = guava.Agent(
        name=None, organization="Synthetic Family Medicine (demo)", purpose=PURPOSE
    )
    agent.on_call_start(logic.on_call_start)
    agent.on_question(logic.on_question)
    agent.on_task_complete(SCREENING_TASK)(logic.on_screening_complete)
    agent.on_task_complete(DETAILS_TASK)(logic.on_details_complete)
    agent.on_task_complete(OFFER_TASK)(logic.on_offer_complete)
    agent.on_session_end(logic.on_session_end)
    return agent


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m clinical_triage.live_demo",
        description="THROWAWAY synthetic Guava demo agent (EXAMPLE_UNREVIEWED). No transfers.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--chat", action="store_true", help="text chat in this terminal")
    mode.add_argument("--phone", action="store_true", help="answer calls on GUAVA_AGENT_NUMBER")
    parser.add_argument("--env-file", type=Path, default=ENV_PATH)
    args = parser.parse_args(argv)
    selected = "phone" if args.phone else "chat"

    load_env_file(args.env_file)
    missing = missing_settings(selected)
    if missing:
        parser.error(f"missing {', '.join(missing)} (set in {args.env_file}; values never shown)")

    guava.logging_utils.configure_logging()
    agent = build_agent(build_logic())
    if args.phone:
        logger.info("listening for calls on the configured number (not shown)")
        agent.listen_phone(os.environ["GUAVA_AGENT_NUMBER"])
    else:
        agent.chat()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
