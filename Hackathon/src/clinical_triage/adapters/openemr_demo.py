"""Small read-only OpenEMR FHIR adapter for one synthetic patient."""

import re
from datetime import date
from typing import Any

import httpx

from clinical_triage.domain.ehr import ClinicalContext, IdentityVerification


class OpenEMRDemoError(RuntimeError):
    """OpenEMR could not provide the evidence required by the demo."""


def normalize_phone(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))[-10:]


class OpenEMRDemoAdapter:
    def __init__(
        self,
        *,
        fhir_base_url: str,
        bearer_token: str | None = None,
        verify_tls: bool = True,
        timeout_seconds: float = 8.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.fhir_base_url = fhir_base_url.rstrip("/")
        self.bearer_token = bearer_token
        self._client = client or httpx.Client(verify=verify_tls, timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def verify_patient(
        self, *, patient_id: str, birth_date: date, phone: str
    ) -> IdentityVerification:
        resource = self._get(f"Patient/{patient_id}")
        birth_matches = resource.get("birthDate") == birth_date.isoformat()
        phone_values = [
            telecom.get("value", "")
            for telecom in resource.get("telecom", [])
            if telecom.get("system") == "phone"
        ]
        phone_matches = bool(normalize_phone(phone)) and any(
            normalize_phone(value) == normalize_phone(phone) for value in phone_values
        )
        factors = tuple(
            code
            for code, matches in (("BIRTH_DATE", birth_matches), ("PHONE", phone_matches))
            if matches
        )
        verified = birth_matches and phone_matches
        return IdentityVerification(
            patient_id=patient_id,
            verified=verified,
            verified_factor_codes=factors,
            requires_human_review=not verified,
        )

    def fetch_context(self, *, patient_id: str) -> ClinicalContext:
        conditions = self._get(f"Condition?patient={patient_id}&_count=20")
        medications = self._get(f"MedicationRequest?patient={patient_id}&_count=20")
        observations = self._get(f"Observation?patient={patient_id}&_count=20")
        return ClinicalContext(
            patient_id=patient_id,
            condition_codes=tuple(_resource_codes(conditions)),
            medication_codes=tuple(_resource_codes(medications)),
            observation_codes=tuple(_resource_codes(observations)),
        )

    def _get(self, path: str) -> dict[str, Any]:
        headers = {"Accept": "application/fhir+json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        try:
            response = self._client.get(f"{self.fhir_base_url}/{path}", headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenEMRDemoError(f"OPENEMR_READ_FAILED:{path}") from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise OpenEMRDemoError(f"OPENEMR_INVALID_RESPONSE:{path}")
        return payload


def _resource_codes(bundle: dict[str, Any]) -> list[str]:
    entries = bundle.get("entry", [])
    codes: list[str] = []
    for entry in entries:
        resource = entry.get("resource", {})
        coding = resource.get("code", {}).get("coding", [])
        codes.extend(
            str(item["code"]) for item in coding if isinstance(item, dict) and item.get("code")
        )
    return codes
