import importlib.util
import json
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from clinical_triage.adapters.errors import AdapterOperationUnavailable
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.ehr import PatientQuery
from clinical_triage.domain.scheduling import AppointmentConfirmation
from clinical_triage.fixtures import (
    FIXTURE_CLOCK,
    FixedClock,
    SyntheticEHR,
    SyntheticPatient,
    build_fixtures,
    load_fixture_json,
    render_fixture_json,
)
from clinical_triage.scheduling import (
    SchedulingPolicy,
    build_confirmation,
    rank_appointment_options,
)

HACKATHON = Path(__file__).parents[2]
COMMITTED = HACKATHON / "fixtures" / "synthetic" / "fixtures.json"
POLICY = SchedulingPolicy.model_validate_json(
    (HACKATHON / "config" / "scheduling" / "example.json").read_text(encoding="utf-8")
)


def _load_loader() -> ModuleType:
    sys.path.insert(0, str(HACKATHON / "infra" / "openemr"))
    spec = importlib.util.spec_from_file_location(
        "openemr_load_fixtures", HACKATHON / "infra" / "openemr" / "load_fixtures.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ehr(
    unavailable_operations: frozenset[str] = frozenset(),
    slots_taken_after_snapshot: frozenset[str] = frozenset(),
) -> SyntheticEHR:
    return SyntheticEHR(
        fixtures=build_fixtures(),
        clock=FixedClock(FIXTURE_CLOCK),
        unavailable_operations=unavailable_operations,
        slots_taken_after_snapshot=slots_taken_after_snapshot,
    )


# --- determinism and PHI guards ----------------------------------------------


def test_committed_fixture_file_matches_generator_exactly() -> None:
    committed = COMMITTED.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render_fixture_json()
    assert render_fixture_json() == render_fixture_json(build_fixtures())


def test_committed_fixture_round_trips() -> None:
    assert load_fixture_json(COMMITTED.read_text(encoding="utf-8")) == build_fixtures()


def test_patients_a_through_g_cover_each_scenario() -> None:
    fixtures = build_fixtures()
    assert [p.synthetic_id for p in fixtures.patients] == [f"SYN-PAT-{c}" for c in "ABCDEFG"]
    assert {p.scenario_code for p in fixtures.patients} == {
        "ROUTINE_REQUEST",
        "ADAPTIVE_CLARIFICATION",
        "URGENT_SAME_DAY",
        "EMERGENCY_INTERRUPTION",
        "HUMAN_REVIEW_FALLBACK",
        "SCHEDULING_FAILURE",
        "IDENTITY_AMBIGUITY",
    }


def test_fixture_values_are_visibly_synthetic() -> None:
    raw = COMMITTED.read_text(encoding="utf-8")
    for patient in build_fixtures().patients:
        assert patient.family_name == "Synthetic"
        assert re.fullmatch(r"555-01\d\d", patient.phone)
    assert "@" not in raw, "fixtures must not contain email addresses"
    assert not re.search(r"\b\d{3}-\d{2}-\d{4}\b", raw), "fixtures must not contain SSN-like values"
    codes = re.findall(r'"(urn:[^"]+)"', raw)
    assert codes and all(code.startswith("urn:synthetic:") for code in codes)


@pytest.mark.parametrize(
    "override",
    [
        {"family_name": "Smith"},
        {"phone": "212-555-0101"},
        {"synthetic_id": "PAT-1"},
        {"condition_codes": ("http://snomed.info/sct|38341003",)},
    ],
)
def test_fixture_model_rejects_non_synthetic_values(override: dict[str, object]) -> None:
    base = build_fixtures().patients[0].model_dump()
    base.update(override)
    with pytest.raises(ValueError):
        SyntheticPatient.model_validate(base)


def test_slots_are_future_relative_to_fixture_clock_and_timezone_aware() -> None:
    for template in build_fixtures().slots:
        slot = template.at(FIXTURE_CLOCK)
        assert slot.starts_at > FIXTURE_CLOCK and slot.starts_at.tzinfo is not None


# --- synthetic EHR behavior --------------------------------------------------


def test_identity_ambiguity_between_patients_a_and_g() -> None:
    by_name = ehr().find_patient(PatientQuery(given_name="avery", family_name="SYNTHETIC"))
    assert [c.patient_id for c in by_name] == ["SYN-PAT-A", "SYN-PAT-G"]
    assert all(c.ambiguous for c in by_name)
    exact = ehr().find_patient(
        PatientQuery(given_name="Avery", family_name="Synthetic", birth_date=date(1981, 12, 13))
    )
    assert [(c.patient_id, c.ambiguous) for c in exact] == [("SYN-PAT-G", False)]


def test_verification_requires_birth_date_and_two_factors() -> None:
    target = ehr()
    assert target.verify_patient("SYN-PAT-A", ("BIRTH_DATE", "FAMILY_NAME")).verified
    assert not target.verify_patient("SYN-PAT-A", ("GIVEN_NAME", "FAMILY_NAME")).verified
    assert not target.verify_patient("SYN-PAT-Z", ("BIRTH_DATE", "FAMILY_NAME")).verified


def test_clinical_context_comes_from_fixture() -> None:
    context = ehr().get_clinical_context("SYN-PAT-B")
    assert context.allergy_codes == ("urn:synthetic:allergy|SYN-ALG-001",)
    with pytest.raises(AdapterOperationUnavailable):
        ehr().get_clinical_context("SYN-PAT-Z")


def test_injected_unavailability_fails_closed() -> None:
    target = ehr(unavailable_operations=frozenset({"GET_AVAILABLE_APPOINTMENTS"}))
    assert not {op.operation_code: op.supported for op in target.capabilities().operations}[
        "GET_AVAILABLE_APPOINTMENTS"
    ]
    with pytest.raises(AdapterOperationUnavailable):
        target.get_available_appointments(
            earliest=FIXTURE_CLOCK, latest=FIXTURE_CLOCK + timedelta(days=1), constraint_codes=()
        )


def _confirmed_offer(target: SyntheticEHR, slot_id: str) -> AppointmentConfirmation:
    snapshot = target.get_available_appointments(
        earliest=FIXTURE_CLOCK, latest=FIXTURE_CLOCK + timedelta(days=30), constraint_codes=()
    )
    options = rank_appointment_options(
        snapshot=snapshot, disposition=Disposition.ROUTINE, policy=POLICY, now=target.clock.now()
    )
    offer = next(
        o
        for o in options.normal_availability + options.alternative_availability
        if o.slot.slot_id == slot_id
    )
    return build_confirmation(
        offer=offer,
        confirmation_id="confirm-1",
        confirmation_event_id="event-1",
        confirmed_at=target.clock.now(),
    )


def test_availability_snapshot_is_deterministic() -> None:
    window = {"earliest": FIXTURE_CLOCK, "latest": FIXTURE_CLOCK + timedelta(days=1)}
    first = ehr().get_available_appointments(**window, constraint_codes=())
    second = ehr().get_available_appointments(**window, constraint_codes=())
    assert first == second
    assert [s.slot_id for s in first.slots] == [
        "SLOT-SYN-SAME-DAY-1",
        "SLOT-SYN-CANCEL-1",
        "SLOT-SYN-ALT-1",
        "SLOT-SYN-TELE-1",
    ]


def test_booking_is_idempotent_and_removes_slot() -> None:
    target = ehr()
    confirmation = _confirmed_offer(target, "SLOT-SYN-OPEN-1")
    first = target.create_appointment(
        patient_id="SYN-PAT-A", confirmation=confirmation, idempotency_key="key-1"
    )
    replay = target.create_appointment(
        patient_id="SYN-PAT-A", confirmation=confirmation, idempotency_key="key-1"
    )
    assert first.completed and first == replay
    assert target.calls.count("CREATE_APPOINTMENT") == 1
    again = target.create_appointment(
        patient_id="SYN-PAT-A", confirmation=confirmation, idempotency_key="key-2"
    )
    assert again.failure_code == "SLOT_NO_LONGER_AVAILABLE"


def test_stale_slot_and_expired_offer_fail_closed() -> None:
    stale = ehr(slots_taken_after_snapshot=frozenset({"SLOT-SYN-OPEN-1"}))
    result = stale.create_appointment(
        patient_id="SYN-PAT-F",
        confirmation=_confirmed_offer(stale, "SLOT-SYN-OPEN-1"),
        idempotency_key="k",
    )
    assert not result.completed and result.failure_code == "SLOT_NO_LONGER_AVAILABLE"

    late = ehr()
    confirmation = _confirmed_offer(late, "SLOT-SYN-OPEN-1")
    late.clock.advance(seconds=3600)
    expired = late.create_appointment(
        patient_id="SYN-PAT-A", confirmation=confirmation, idempotency_key="k"
    )
    assert expired.failure_code == "OFFER_EXPIRED"


def test_fixed_clock_requires_timezone() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 1, 1))
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    clock.advance(seconds=5)
    assert clock.now() == datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)


# --- OpenEMR loader (render and guards only; no network) ---------------------


def test_openemr_render_is_deterministic_patient_only() -> None:
    loader = _load_loader()
    rendered = loader.render_patients()
    assert rendered == loader.render_patients()
    assert [r["resourceType"] for r in rendered] == ["Patient"] * 7
    assert json.loads(json.dumps(rendered))[0]["identifier"][0]["value"] == "SYN-PAT-A"


@pytest.mark.parametrize(
    "argv",
    [
        ["apply", "--pin-sha256", "0" * 64],
        ["apply", "--pin-sha256", "0" * 64, "--apply"],
        [
            "--base-url",
            "https://ehr.example.org",
            "apply",
            "--pin-sha256",
            "0" * 64,
            "--apply",
            "--i-approve-local-synthetic-write",
        ],
    ],
)
def test_openemr_write_requires_approval_and_loopback(argv: list[str]) -> None:
    assert _load_loader().main(argv) == 3


def test_openemr_write_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENEMR_ACCESS_TOKEN", raising=False)
    argv = ["apply", "--pin-sha256", "0" * 64, "--apply", "--i-approve-local-synthetic-write"]
    assert _load_loader().main(argv) == 3
