"""Local structured audit for the focused synthetic demo."""

import json
from datetime import UTC, datetime
from pathlib import Path

from clinical_triage.demo.models import DemoEmergencyOutcome


def persist_emergency_outcome(outcome: DemoEmergencyOutcome, *, audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as stream:
        stream.write(outcome.model_dump_json() + "\n")


def new_outcome(*, call_id: str, patient_id: str) -> DemoEmergencyOutcome:
    return DemoEmergencyOutcome(
        synthetic_patient_id=patient_id,
        call_id=call_id,
        occurred_at=datetime.now(UTC),
    )


def load_last_outcome(audit_path: Path) -> DemoEmergencyOutcome | None:
    if not audit_path.exists():
        return None
    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line]
    return DemoEmergencyOutcome.model_validate(json.loads(lines[-1])) if lines else None
