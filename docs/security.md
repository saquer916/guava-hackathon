# Security, privacy, and PHI gaps

This prototype holds **synthetic data only**. The controls below are what the
code and configuration enforce today; the gap list is what must change before
any real patient information could be handled. Nothing here is a compliance
certification.

## Controls in place (verified by tests or observation)

| Area | Control | Evidence |
| --- | --- | --- |
| Data | Fixtures are generated in code; family name is always `Synthetic`, phones are fictional `555-01xx`, IDs are `SYN-PAT-*`, clinical codes use `urn:synthetic:*` | `tests/fixtures/test_synthetic_fixtures.py` |
| Secrets | `.env` and `.env.*` are git-ignored; compose has no credential defaults (`${VAR:?}`); tokens are redacted from `repr` | `tests/integration/test_openemr_local.py`, `tests/adapters/test_openemr_adapter.py` |
| Telemetry vs. evidence | `AuditRecord`/`OperationalEvent` carry IDs and codes only; fact values live only in `DecisionRecord`, written to a separate protected file | `tests/orchestration` (redaction and JSONL separation tests) |
| Free text | Caller question text is never stored or interpreted; a fixed deflection is returned | `test_question_text_is_never_stored` |
| Exceptions | No exception escapes a voice callback; adapter failures are audited by reason code or exception class name, never message text (Guava SDK telemetry uploads exception reprs) | `test_unexpected_adapter_exception_is_recorded_by_class_name_only` |
| Identity | A name alone never identifies a caller; birth date is required; ambiguous or unmatched identity goes to human review | `tests/orchestration` identity tests, `identity-uncertain` scenario |
| Writes | Booking and EHR record writes are off by default (`allow_booking_writes`, `allow_record_writes`); the OpenEMR adapter is read-only by construction | `tests/orchestration`, `docs/openemr-capabilities.md` |
| EHR exposure | OpenEMR binds `127.0.0.1` only; `reset.sh` stops the stack otherwise; TLS verification cannot be disabled; certificate is pinned | Observed live 2026-09-26 (`127.0.0.1:9301->443`) |
| EHR auth | FHIR only; standard REST, portal, system scopes, and password grant are off; adapter scopes are `user/<Resource>.rs` only | `compose.yaml`, `adapters/openemr/config.py`; observed: token endpoint offers only `authorization_code`/`refresh_token` |
| Voice | Live phone binding and call transfer are refused unless explicitly approved in code; transfer destinations come only from operator config | `tests/adapters/test_guava` |
| Validation | Every domain value is a frozen pydantic model with `extra="forbid"`; policy bundles are checksummed | `tests/domain`, `tests/safety` |

## Gaps before any real PHI (blocking)

1. **Legal/compliance.** No BAA with Guava or any hosting provider; no HIPAA
   risk analysis; no retention, access, or breach-notification policy.
2. **Voice data flow.** Guava's agent hears and transcribes the caller and
   extracts field values with its own model. Where audio, transcripts, and
   field values are stored, for how long, and who can read them is not
   documented here. SDK telemetry behavior must be confirmed with Guava
   (`GUAVA_DISABLE_TELEMETRY` is undocumented).
3. **Protected decision records.** `JsonlAuditSink` writes plain JSONL to a
   local file. Real use needs encryption at rest, access control, audit of
   access, retention limits, and tamper evidence.
4. **Identity verification.** Name + birth date is a demo standard. Real use
   needs a clinic-approved verification policy, protection against
   enumeration, and handling of proxies/caregivers.
5. **Authentication to the EHR.** Tokens are operator-supplied and
   short-lived; there is no managed token lifecycle, secret store, or
   per-environment client. OpenEMR clients must be registered and enabled by an
   administrator.
6. **Logging.** Operational events are sanitized by construction, but no log
   shipping, alerting, or SIEM integration exists. Python and Guava SDK logs
   outside this code have not been reviewed.
7. **Network.** Everything assumes one developer machine. Any shared
   environment needs network segmentation, TLS with real certificates, and
   secrets management.
8. **Clinical safety.** The policy and all caller-facing wording are
   EXAMPLE_UNREVIEWED (see `docs/clinical-policy.md`).

## Operator note

The compose default port (9300) is also OpenEMR's own development-stack
default. If another OpenEMR stack is already running, set a different
`OPENEMR_HTTPS_PORT` in the ignored `.env` rather than stopping someone else's
environment, and check that any other local OpenEMR stack is bound to loopback
(`docker ps` shows `127.0.0.1:` rather than `0.0.0.0:`).
