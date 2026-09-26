"""One focused live Guava call: synthetic identity to stroke-emergency routing."""

import logging
import os
from datetime import date
from pathlib import Path

import guava
from guava import logging_utils
from guava.events import BotSessionEnded

from clinical_triage.adapters.openemr_demo import OpenEMRDemoAdapter, OpenEMRDemoError
from clinical_triage.demo.audit import new_outcome, persist_emergency_outcome
from clinical_triage.demo.emergency import evaluate_stroke_red_flag

logger = logging.getLogger("guava.stroke_demo")
CURRENT_DIR = Path(__file__).resolve().parent
AUDIT_PATH = Path(os.getenv("DEMO_AUDIT_PATH", CURRENT_DIR / "audit" / "stroke-emergency.jsonl"))
PATIENT_ID_BY_CALL: dict[str, str] = {}

agent = guava.Agent(
    name="Synthetic Emergency Routing Demo",
    organization="Hackathon Synthetic Clinic",
    purpose="Verify one synthetic caller and route a deterministic emergency red flag.",
)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"missing required configuration: {name}")
    return value


def _adapter() -> OpenEMRDemoAdapter:
    return OpenEMRDemoAdapter(
        fhir_base_url=_required_env("OPENEMR_FHIR_BASE_URL"),
        bearer_token=os.getenv("OPENEMR_BEARER_TOKEN") or None,
        verify_tls=os.getenv("OPENEMR_VERIFY_TLS", "true").lower() not in {"0", "false", "no"},
    )


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@agent.on_call_start
def on_call_start(call: guava.Call) -> None:
    logger.info("synthetic emergency demo call started")
    try:
        _required_env("DEMO_PATIENT_ID")
        _required_env("OPENEMR_FHIR_BASE_URL")
    except RuntimeError:
        call.hangup("This demonstration is not configured. Please end the call.")
        return

    call.set_task(
        "identity",
        objective=(
            "Verify the synthetic patient before discussing symptoms. Ask briefly for their "
            "date of birth and the phone number used for the appointment. Do not disclose any "
            "record details until both match."
        ),
        checklist=[
            guava.Field(
                key="patient_birth_date",
                field_type="date",
                description="Ask for the patient's date of birth.",
                required=True,
            ),
            guava.Field(
                key="patient_phone",
                field_type="digit_sequence",
                description="Ask for the phone number on the synthetic patient record.",
                required=True,
            ),
        ],
    )


@agent.on_task_complete("identity")
def on_identity_complete(call: guava.Call) -> None:
    patient_id = _required_env("DEMO_PATIENT_ID")
    adapter = _adapter()
    try:
        verification = adapter.verify_patient(
            patient_id=patient_id,
            birth_date=_as_date(call.get_field("patient_birth_date")),
            phone=str(call.get_field("patient_phone") or ""),
        )
        if not verification.verified:
            logger.info("synthetic identity verification failed")
            call.hangup("I could not verify those details. Please contact the clinic directly.")
            return
        PATIENT_ID_BY_CALL[call.id] = patient_id
        try:
            context = adapter.fetch_context(patient_id=patient_id)
            logger.info(
                "synthetic context fetched: conditions=%d medications=%d observations=%d",
                len(context.condition_codes),
                len(context.medication_codes),
                len(context.observation_codes),
            )
        except OpenEMRDemoError:
            logger.info("synthetic context fetch failed; continuing only for emergency screening")
    except (ValueError, OpenEMRDemoError):
        logger.info("synthetic identity lookup failed")
        call.hangup("I could not verify those details. Please contact the clinic directly.")
        return
    finally:
        adapter.close()

    call.set_task(
        "symptoms",
        objective=(
            "Ask concise adaptive follow-ups about the caller's vague symptoms. First ask when "
            "the symptoms began. Then ask whether one arm, especially the right arm, feels weak. "
            "Then ask whether anyone has noticed speech sounding unusual. "
            "Accept short yes/no answers."
        ),
        checklist=[
            guava.Field(
                key="symptom_onset",
                field_type="text",
                description="Ask when the unusual feeling began; capture a short answer.",
                required=True,
            ),
            guava.Field(
                key="right_arm_weakness",
                field_type="multiple_choice",
                choices=("yes", "no", "unclear"),
                description="Ask whether the right arm feels weak. Record yes, no, or unclear.",
                required=True,
            ),
            guava.Field(
                key="speech_abnormality",
                field_type="multiple_choice",
                choices=("yes", "no", "unclear"),
                description=(
                    "Ask whether the caller or someone with them notices unusual or "
                    "slurred speech. "
                    "Record yes, no, or unclear."
                ),
                required=True,
            ),
        ],
    )


@agent.on_task_complete("symptoms")
def on_symptoms_complete(call: guava.Call) -> None:
    result = evaluate_stroke_red_flag(
        right_arm_weakness=call.get_field("right_arm_weakness"),
        speech_abnormality=call.get_field("speech_abnormality"),
    )
    patient_id = PATIENT_ID_BY_CALL.get(call.id, "unknown-synthetic-patient")
    if result.disposition.value == "EMERGENCY":
        outcome = new_outcome(call_id=call.id, patient_id=patient_id)
        persist_emergency_outcome(outcome, audit_path=AUDIT_PATH)
        logger.info(
            "EMERGENCY disposition=%s trigger=%s schedulingAllowed=false patient_id=%s",
            outcome.disposition,
            outcome.trigger,
            patient_id,
        )
        call.hangup(
            "Tell the caller this may be a medical emergency. Tell them to call 911 now, "
            "or have someone call for them. Tell them not to drive themselves. Do not diagnose "
            "or continue normal scheduling."
        )
        return

    logger.info("screen incomplete; routing to human review")
    call.hangup(
        "Tell the caller a clinician must review this call. Do not offer an appointment or "
        "say that they are safe."
    )


@agent.on_session_end
def on_session_end(call: guava.Call, event: BotSessionEnded) -> None:
    del event
    PATIENT_ID_BY_CALL.pop(call.id, None)
    logger.info("synthetic emergency demo call ended")


if __name__ == "__main__":
    logging_utils.configure_logging()
    agent.listen_phone(_required_env("GUAVA_AGENT_NUMBER"))
