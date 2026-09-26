from datetime import date
from pathlib import Path

import httpx

from clinical_triage.adapters.openemr_demo import OpenEMRDemoAdapter
from clinical_triage.demo.audit import load_last_outcome, new_outcome, persist_emergency_outcome
from clinical_triage.demo.emergency import evaluate_stroke_red_flag
from clinical_triage.domain.disposition import Disposition


def test_focal_neurologic_deficit_is_deterministic_and_stops_scheduling() -> None:
    result = evaluate_stroke_red_flag(right_arm_weakness="yes", speech_abnormality="yes")
    assert result.disposition is Disposition.EMERGENCY
    assert result.trigger_rule_ids == ("focal_neurologic_deficit",)
    assert result.recommended_scheduling_window is None


def test_incomplete_screen_fails_to_human_review() -> None:
    result = evaluate_stroke_red_flag(right_arm_weakness="yes", speech_abnormality="unclear")
    assert result.disposition is Disposition.HUMAN_REVIEW
    assert result.requires_human_review is True


def test_structured_audit_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "stroke-emergency.jsonl"
    outcome = new_outcome(call_id="call-1", patient_id="synthetic-patient-1")
    persist_emergency_outcome(outcome, audit_path=path)
    loaded = load_last_outcome(path)
    assert loaded is not None
    assert loaded.scheduling_allowed is False
    assert loaded.trigger == "focal_neurologic_deficit"


def test_openemr_adapter_verifies_two_identity_factors_and_fetches_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Patient/patient-1"):
            return httpx.Response(
                200,
                json={
                    "resourceType": "Patient",
                    "birthDate": "1980-01-02",
                    "telecom": [{"system": "phone", "value": "+1 240 212 6155"}],
                },
            )
        if "Condition" in request.url.path:
            return httpx.Response(
                200,
                json={"entry": [{"resource": {"code": {"coding": [{"code": "I10"}]}}}]},
            )
        if "Observation" in request.url.path:
            return httpx.Response(
                200,
                json={"entry": [{"resource": {"code": {"coding": [{"code": "8867-4"}]}}}]},
            )
        return httpx.Response(200, json={"entry": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenEMRDemoAdapter(fhir_base_url="https://openemr.test/fhir", client=client)
    verification = adapter.verify_patient(
        patient_id="patient-1", birth_date=date(1980, 1, 2), phone="2402126155"
    )
    context = adapter.fetch_context(patient_id="patient-1")
    adapter.close()
    assert verification.verified is True
    assert verification.verified_factor_codes == ("BIRTH_DATE", "PHONE")
    assert context.condition_codes == ("I10",)
    assert context.observation_codes == ("8867-4",)
