"""Deterministic synthetic patients A-G, providers, and availability.

Every value here is invented. Names follow the "<Given> Synthetic" pattern,
phone numbers use the fictional 555-01xx range, and clinical codes use the
non-clinical `urn:synthetic:*` systems so nothing can be mistaken for real
data or real clinical coding. `render_fixture_json()` is the only generator;
`Hackathon/fixtures/synthetic/fixtures.json` must equal its output.
"""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.scheduling import AppointmentSlot, AvailabilityKind

FIXTURE_VERSION = "1"
FIXTURE_CLOCK = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
PHONE_PREFIX = "555-01"


class SyntheticPatient(DomainModel):
    synthetic_id: str = Field(pattern=r"^SYN-PAT-[A-G]$")
    given_name: str = Field(min_length=1)
    family_name: str = Field(pattern=r"^Synthetic$")
    birth_date: date
    phone: str = Field(pattern=r"^555-01\d\d$")
    scenario_code: str = Field(min_length=1)
    condition_codes: tuple[str, ...] = ()
    medication_codes: tuple[str, ...] = ()
    allergy_codes: tuple[str, ...] = ()
    observation_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def codes_are_synthetic(self) -> "SyntheticPatient":
        for code in (
            self.condition_codes
            + self.medication_codes
            + self.allergy_codes
            + self.observation_codes
        ):
            if not code.startswith("urn:synthetic:"):
                raise ValueError("fixture clinical codes must use urn:synthetic systems")
        return self


class SyntheticSlotTemplate(DomainModel):
    slot_id: str = Field(pattern=r"^SLOT-SYN-[A-Z0-9-]+$")
    provider_id: str = Field(pattern=r"^PROV-SYN-\d$")
    location_id: str = Field(pattern=r"^LOC-SYN-[A-Z]+$")
    offset_minutes: int = Field(ge=1)
    duration_minutes: int = Field(ge=5, le=120)
    kind: AvailabilityKind

    def at(self, clock: datetime) -> AppointmentSlot:
        starts_at = clock + timedelta(minutes=self.offset_minutes)
        return AppointmentSlot(
            slot_id=self.slot_id,
            provider_id=self.provider_id,
            location_id=self.location_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=self.duration_minutes),
            kind=self.kind,
        )


class SyntheticFixtures(DomainModel):
    fixture_version: str
    clock: datetime
    patients: tuple[SyntheticPatient, ...]
    slots: tuple[SyntheticSlotTemplate, ...]

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> "SyntheticFixtures":
        for values, label in (
            ([p.synthetic_id for p in self.patients], "patient"),
            ([p.phone for p in self.patients], "phone"),
            ([s.slot_id for s in self.slots], "slot"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate synthetic {label} identifier")
        return self

    def patient(self, synthetic_id: str) -> SyntheticPatient:
        return next(p for p in self.patients if p.synthetic_id == synthetic_id)


def _code(kind: str, value: str) -> str:
    return f"urn:synthetic:{kind}|{value}"


def build_fixtures() -> SyntheticFixtures:
    patients = (
        SyntheticPatient(
            synthetic_id="SYN-PAT-A",
            given_name="Avery",
            family_name="Synthetic",
            birth_date=date(1980, 1, 2),
            phone="555-0101",
            scenario_code="ROUTINE_REQUEST",
            condition_codes=(_code("condition", "SYN-COND-001"),),
            medication_codes=(_code("medication", "SYN-MED-001"),),
        ),
        SyntheticPatient(
            synthetic_id="SYN-PAT-B",
            given_name="Blake",
            family_name="Synthetic",
            birth_date=date(1975, 3, 4),
            phone="555-0102",
            scenario_code="ADAPTIVE_CLARIFICATION",
            allergy_codes=(_code("allergy", "SYN-ALG-001"),),
        ),
        SyntheticPatient(
            synthetic_id="SYN-PAT-C",
            given_name="Casey",
            family_name="Synthetic",
            birth_date=date(1990, 5, 6),
            phone="555-0103",
            scenario_code="URGENT_SAME_DAY",
        ),
        SyntheticPatient(
            synthetic_id="SYN-PAT-D",
            given_name="Drew",
            family_name="Synthetic",
            birth_date=date(1968, 7, 8),
            phone="555-0104",
            scenario_code="EMERGENCY_INTERRUPTION",
            condition_codes=(_code("condition", "SYN-COND-002"),),
            observation_codes=(_code("observation", "SYN-OBS-001"),),
        ),
        SyntheticPatient(
            synthetic_id="SYN-PAT-E",
            given_name="Emery",
            family_name="Synthetic",
            birth_date=date(1985, 9, 10),
            phone="555-0105",
            scenario_code="HUMAN_REVIEW_FALLBACK",
        ),
        SyntheticPatient(
            synthetic_id="SYN-PAT-F",
            given_name="Finley",
            family_name="Synthetic",
            birth_date=date(1995, 11, 12),
            phone="555-0106",
            scenario_code="SCHEDULING_FAILURE",
        ),
        SyntheticPatient(
            synthetic_id="SYN-PAT-G",
            given_name="Avery",
            family_name="Synthetic",
            birth_date=date(1981, 12, 13),
            phone="555-0107",
            scenario_code="IDENTITY_AMBIGUITY",
        ),
    )
    slots = (
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-SAME-DAY-1",
            provider_id="PROV-SYN-1",
            location_id="LOC-SYN-MAIN",
            offset_minutes=120,
            duration_minutes=20,
            kind=AvailabilityKind.SAME_DAY,
        ),
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-CANCEL-1",
            provider_id="PROV-SYN-1",
            location_id="LOC-SYN-MAIN",
            offset_minutes=240,
            duration_minutes=20,
            kind=AvailabilityKind.CANCELLATION,
        ),
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-ALT-1",
            provider_id="PROV-SYN-2",
            location_id="LOC-SYN-EAST",
            offset_minutes=300,
            duration_minutes=20,
            kind=AvailabilityKind.ALTERNATIVE_PROVIDER,
        ),
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-TELE-1",
            provider_id="PROV-SYN-2",
            location_id="LOC-SYN-VIRTUAL",
            offset_minutes=360,
            duration_minutes=15,
            kind=AvailabilityKind.TELEHEALTH,
        ),
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-OPEN-1",
            provider_id="PROV-SYN-1",
            location_id="LOC-SYN-MAIN",
            offset_minutes=1500,
            duration_minutes=30,
            kind=AvailabilityKind.OPEN,
        ),
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-OPEN-2",
            provider_id="PROV-SYN-1",
            location_id="LOC-SYN-MAIN",
            offset_minutes=4320,
            duration_minutes=30,
            kind=AvailabilityKind.OPEN,
        ),
        SyntheticSlotTemplate(
            slot_id="SLOT-SYN-NEXT-1",
            provider_id="PROV-SYN-1",
            location_id="LOC-SYN-MAIN",
            offset_minutes=20160,
            duration_minutes=30,
            kind=AvailabilityKind.NEXT_AVAILABLE,
        ),
    )
    return SyntheticFixtures(
        fixture_version=FIXTURE_VERSION, clock=FIXTURE_CLOCK, patients=patients, slots=slots
    )


def render_fixture_json(fixtures: SyntheticFixtures | None = None) -> str:
    document: dict[str, Any] = (fixtures or build_fixtures()).model_dump(mode="json")
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def load_fixture_json(text: str) -> SyntheticFixtures:
    return SyntheticFixtures.model_validate_json(text)
