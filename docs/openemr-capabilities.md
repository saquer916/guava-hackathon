# OpenEMR FHIR adapter: capabilities and gaps

Scope: Fleet task `guava-openemr-fhir-adapter` (Issue #4).
Code: `Hackathon/src/clinical_triage/adapters/openemr/`.

The adapter implements the provider-neutral `EHRAdapter` port against the
OpenEMR FHIR R4 API. FHIR payloads never leave the adapter: callers receive
only `clinical_triage.domain` values or a provider-neutral
`AdapterOperationUnavailable(operation_code, reason_code)`.

## Boundary

| Property | Enforcement |
| --- | --- |
| Local only | `OpenEMRConfig` rejects any base URL that is not `https` on a loopback host, or that embeds credentials, a path, or a query. |
| TLS on | `HttpxFhirTransport` requires a CA bundle file; there is no option to disable verification. |
| Least privilege | Scopes must be `openid`, `api:fhir`, or `user/<Resource>.rs`. `system/*`, `patient/*`, wildcards, v1 `.read/.write`, write permissions, `offline_access`, and `api:oemr` are rejected. |
| Read only | The transport exposes `GET` only. Appointment mutations and call/triage recording return explicit failed results with `ADAPTER_READ_ONLY_BOUNDARY`. |
| No secret leakage | Tokens are redacted from `repr`; failures carry reason codes only, never response bodies or request values. |
| No password grant | The adapter never acquires tokens. An operator supplies a short-lived token obtained through a documented OpenEMR OAuth2 flow. |

## Capability gates

`OpenEMRFhirAdapter.discover()` reads `GET /apis/{site}/fhir/metadata` once.
If discovery fails (unreachable, non-200, not a CapabilityStatement, not FHIR
4.0.x), the adapter is inactive and every operation raises with that reason.
Otherwise each operation is enabled only if the statement advertises every
interaction and search parameter it uses. Operations check this before sending
any request.

| Port operation | Requires | Status against documented OpenEMR |
| --- | --- | --- |
| `find_patient` | `Patient` `search-type` + each query factor's search param (`given`, `family`, `birthdate`, `phone`, `identifier`) | Expected available |
| `get_patient` | `Patient` `read` | Expected available |
| `verify_patient` | `Patient` `read` | Expected available |
| `get_appointments` | `Appointment` `search-type` with `patient` | Must be confirmed by live statement |
| `get_available_appointments` | `Slot` `search-type` with `start`, `status` | **Unavailable**: OpenEMR documents no `Slot`/`Schedule` resource. Even if advertised, stays unsupported (`SLOT_MAPPING_NOT_IMPLEMENTED`). |
| `get_clinical_context` | `search-type` with `patient` on `Condition`, `MedicationRequest`, `AllergyIntolerance`, `Observation` | Must be confirmed by live statement |
| `create_appointment`, `update_appointment` | — | **Disabled** (`ADAPTER_READ_ONLY_BOUNDARY`) |
| `record_call_summary`, `record_triage_result` | — | **Disabled** (`ADAPTER_READ_ONLY_BOUNDARY`) |

## Fail-closed semantics

- Patient search results are rechecked exactly on the client (FHIR `string`
  search is prefix-based); only candidates matching every supplied factor are
  returned. More than one match, a `next` link, or a `total` larger than the
  page marks every candidate `ambiguous`.
- Identity verification requires the patient to exist and at least two
  distinct known factors including `BIRTH_DATE` (configurable upward only).
- Clinical context is all-or-nothing: truncation, authorization failure, a
  malformed bundle, or any uncoded entry raises rather than returning a partial
  (and therefore falsely reassuring) context.
- Existing appointments missing start/end with timezone, a practitioner, or a
  location raise `APPOINTMENT_MAPPING_INCOMPLETE`.
- Record IDs are validated against the FHIR id grammar before building a path.

## Mapping assumptions (review requested)

- Domain `patient_id` is the opaque FHIR `Patient.id`.
- Clinical codes are rendered `system|code` from the first complete coding.
- Existing appointments map to `AppointmentSlot(kind=OPEN)` with
  `slot_id = "appointment-<id>"`; `status` is upper-cased FHIR status.
- `AdapterOperationUnavailable` lives in `clinical_triage/adapters/errors.py`
  because the frozen `EHRAdapter` port has no failure channel for reads. It is
  provider-neutral and adds no field to any domain contract. Codex should
  confirm or relocate it.

## Gaps requiring a Codex decision

1. **Appointment availability.** No documented FHIR path. Options: a separate,
   explicit OpenEMR Standard API adapter (the architecture permits this for
   documented gaps; its endpoints must be taken from OpenEMR's Swagger for the
   pinned version, not guessed), or a synthetic availability source for the
   demo.
2. **Writes.** Booking and recording would need write scopes and a verified
   create mapping; both are outside this task.
3. **Token acquisition.** Authorization-code flow requires an interactive
   login; client-credentials requires `system/*` scopes and JWKS, which this
   project does not enable.
4. **Live confirmation.** No live CapabilityStatement has been captured (the
   worker host had no Docker). Tests use hand-authored payloads shaped per
   OpenEMR documentation.
