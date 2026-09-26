"""Small, explicit models for the one-call hackathon demonstration."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from clinical_triage.domain._model import DomainModel


class DemoEmergencyOutcome(DomainModel):
    disposition: Literal["EMERGENCY"] = "EMERGENCY"
    trigger: Literal["focal_neurologic_deficit"] = "focal_neurologic_deficit"
    scheduling_allowed: Literal[False] = False
    synthetic_patient_id: str = Field(min_length=1)
    key_symptom_fact_ids: tuple[str, ...] = ("right_arm_weakness", "speech_abnormality")
    call_id: str = Field(min_length=1)
    occurred_at: datetime
