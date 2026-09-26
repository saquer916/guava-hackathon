"""Opt-in live evidence: the real OpenEMR adapter against the local synthetic OpenEMR.

Skipped by default verification. Requires the loopback-only stack from
`infra/openemr` and a CA bundle holding its self-signed certificate:

    OPENEMR_LIVE_BASE_URL=https://localhost:9301 \
    OPENEMR_LIVE_CA_BUNDLE=infra/openemr/data/server.pem \
    uv run --frozen pytest tests/e2e/test_openemr_live.py -q

The CapabilityStatement is unauthenticated, so discovery needs no token. The
orchestrated-call test additionally needs OPENEMR_LIVE_ACCESS_TOKEN (a
user-context read-only token for synthetic data) and is skipped without it.
"""

import os
from pathlib import Path

import pytest

from clinical_triage.adapters.openemr import (
    HttpxFhirTransport,
    OpenEMRConfig,
    OpenEMRFhirAdapter,
    StaticAccessToken,
)

BASE_URL = os.environ.get("OPENEMR_LIVE_BASE_URL", "")
CA_BUNDLE = os.environ.get("OPENEMR_LIVE_CA_BUNDLE", "")
TOKEN = os.environ.get("OPENEMR_LIVE_ACCESS_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not (BASE_URL and CA_BUNDLE),
    reason="opt-in: set OPENEMR_LIVE_BASE_URL and OPENEMR_LIVE_CA_BUNDLE",
)


def live_adapter() -> OpenEMRFhirAdapter:  # pragma: no cover - opt-in only
    transport = HttpxFhirTransport(
        base_url=BASE_URL,
        ca_bundle=Path(CA_BUNDLE),
        # Metadata is fetched without a token; other reads need a real one.
        tokens=StaticAccessToken(TOKEN or "metadata-only"),
    )
    return OpenEMRFhirAdapter.discover(config=OpenEMRConfig(base_url=BASE_URL), transport=transport)


def test_live_discovery_gates_operations_on_the_capability_statement() -> None:  # pragma: no cover
    report = live_adapter().capabilities()
    supported = {o.operation_code: o.supported for o in report.operations}
    assert report.active
    assert supported["FIND_PATIENT"] and supported["VERIFY_PATIENT"]
    # OpenEMR advertises no FHIR Slot/Schedule and a read-only Appointment.
    assert not supported["GET_AVAILABLE_APPOINTMENTS"]
    assert not supported["CREATE_APPOINTMENT"]
    assert not supported["UPDATE_APPOINTMENT"]


@pytest.mark.skipif(not TOKEN, reason="opt-in: also set OPENEMR_LIVE_ACCESS_TOKEN")
def test_live_orchestrated_call_fails_closed_without_fhir_availability() -> (
    None
):  # pragma: no cover
    from clinical_triage.audit import InMemoryAuditSink
    from clinical_triage.demo import ScenarioDriver, scenario
    from clinical_triage.domain.disposition import Disposition
    from clinical_triage.fixtures import FIXTURE_CLOCK, FixedClock
    from clinical_triage.orchestration import CallOrchestrator
    from clinical_triage.orchestration.example import (
        example_orchestrator_config,
        example_policy_engine,
        example_scheduling_policy,
    )

    clock = FixedClock(FIXTURE_CLOCK)
    sink = InMemoryAuditSink()
    orchestrator = CallOrchestrator(
        config=example_orchestrator_config(allow_booking_writes=True),
        policy=example_policy_engine(),
        scheduling_policy=example_scheduling_policy(),
        ehr=live_adapter(),
        audit=sink,
        clock=clock,
    )
    routine = scenario("routine")
    ScenarioDriver(orchestrator, clock, routine.transfer_outcomes).run(
        "live-routine", routine.steps[:-1]
    )
    (record,) = sink.audit_records
    ops = {o.operation_type: o for o in record.operations}
    assert record.synthetic_patient_id is not None
    assert ops["EHR.GET_AVAILABLE_APPOINTMENTS"].error_code is not None
    assert "EHR.CREATE_APPOINTMENT" not in ops
    assert record.disposition is Disposition.ROUTINE
    assert "HUMAN_REVIEW:AVAILABILITY_UNAVAILABLE" in record.human_decision_codes
