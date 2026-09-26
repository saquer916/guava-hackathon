# Guava integration checkpoint

Scope: Fleet task `guava-voice-adapter` (Issue #9).
Code: `Hackathon/src/clinical_triage/adapters/guava/` (SDK adapter) and
`Hackathon/src/clinical_triage/adapters/voice_mock.py` (deterministic mock).

**Status: not connected to Guava.** No call has been placed, received, or
transferred by this code. `Hackathon/main.py` and `Hackathon/guava.toml` are
unchanged scaffold files; they remain the live-voice boundary and require
explicit Codex and human approval before any change. A live entry point that
binds `CallOrchestrator` to `GuavaInboundAdapter` has **not** been written.

## Documented Guava surface used

Every item below appears in `Hackathon/guava-docs.md` (SDK `guava-sdk==0.45.0`):

| Port operation | Guava API |
| --- | --- |
| bind call start | `@agent.on_call_start` |
| bind caller question | `@agent.on_question` (returns a string) |
| bind task completion | `@agent.on_task_complete("<task_id>")` |
| bind session end | `@agent.on_session_end` with `BotSessionEnded.termination_reason` |
| `CallPort.set_task` | `call.set_task(task_id, objective=, checklist=, completion_criteria=)` with `guava.Field` / `guava.Say` / strings |
| `CallPort.get_field` | `call.get_field(key)` |
| `CallPort.transfer` | `call.transfer(destination, instructions=None)` (soft transfer) |
| `CallPort.hangup` | `call.hangup(final_instructions)` |
| `listen_phone` | `agent.listen_phone(number)` |

Field options passed through: `key`, `description`, `question`, `field_type`,
`required`, `choices`, `sensitive`. `searchable` is refused because it needs an
`on_search_query` handler, which the provider-neutral port does not expose.
Termination reasons outside the four in the voice port (e.g. `voicemail`) are
mapped to `bot-failure`.

Not used: `on_action_request`, `on_search_query`, `reach_person`, outbound
calling, `immediate_transfer`, `read_script`, `send_instruction`, variables,
RAG helpers, `chat`, `call_local`, WebRTC.

## Approval gates in code

- `GuavaInboundAdapter.listen_phone` raises `LiveVoiceNotApproved` unless the
  adapter was constructed with `live_calls_approved=True`.
- `GuavaCallPort.transfer` returns `accepted=False` with
  `LIVE_TRANSFER_NOT_APPROVED` unless `live_transfer_approved=True`, and with
  `TRANSFER_TARGET_NOT_CONFIGURED` unless the target ID resolves in a
  `TransferDirectory`. Destinations must be E.164 or SIP URIs, come only from
  operator configuration (never from the caller or the model), and are not
  shown in `repr`.
- The default agent factory constructs a real `guava.Agent`, which constructs a
  `guava.Client` that authenticates and makes an HTTP request to Guava.
  Adapter construction does not call the factory; only `bind()` does. Tests
  inject a recording fake and never construct `guava.Agent`.

## Transfer semantics

Guava documents `call.transfer()` as returning nothing. An accepted
`TransferResult` therefore means **transfer submitted**, not completed.
Completion is only observable when `on_session_end` reports `bot-transfer`.
The orchestrator must not record an escalation as completed on the
`TransferResult` alone.

## Deterministic mock

`DeterministicInboundMock` implements the same inbound port and replays an
explicit script (`start`, `field`, `complete`, `question`, `hangup`). It never
recognizes speech, extracts fields from language, times turns, or generates
replies. A `field` event must name a field in the active task; `complete`
fires the task handler only when every required field was supplied; commands
after session end are rejected. Transfer outcomes are configured per target ID.

## Risks found while integrating

- **SDK telemetry.** `guava.Call` and `guava.Agent` methods are wrapped by SDK
  telemetry that records method names and the `repr` of any exception raised
  inside them, and uploads them once a `guava.Client` exists. Adapter code must
  never raise exceptions containing caller data through SDK calls. The SDK
  source reads `GUAVA_DISABLE_TELEMETRY`, but that variable is **not
  documented**; do not rely on it without confirmation from Guava.
- **Field values are model-extracted.** Guava's agent extracts field values
  from speech with its own LLM. Those values are caller-reported and
  unverified; the orchestrator must translate them into `ClinicalFact`s with
  `source=CALLER`, and only the deterministic policy may act on them.
- **Question callback.** `on_question` receives free text. The integration must
  return fixed, non-clinical deflections; it must not answer clinical
  questions or route text into a model.

## How the orchestrator binds (verified offline)

`CallOrchestrator.handlers()` returns provider-neutral `InboundHandlers`. The
same object is bound by `DeterministicInboundMock.bind(...)` in tests and would
be bound by `GuavaInboundAdapter.bind(spec, handlers)` live; no orchestration
code changes between the two. Task IDs registered with `on_task_complete`
are the consent question, each voice question in the config, `identity`,
`offer`, and `offer_retry` (see `orchestration/config.py`).

Guava never receives tools or FHIR access. The server-side orchestrator sets
one task at a time (`set_task`) and acts on completed fields. The high-level
operations the product brief names map onto orchestrator internals and the
provider-neutral EHR port as follows:

| Brief's tool | Where it happens | Exposed to Guava? |
| --- | --- | --- |
| `lookup_patient` / `verify_patient` | `identity` task completion → `EHRAdapter.find_patient` then `verify_patient` | No |
| `get_patient_context` | `EHRAdapter.get_clinical_context` (implemented in adapters, not yet used in the call flow) | No |
| `get_upcoming_appointments` | `EHRAdapter.get_appointments` (implemented, not yet used in the call flow) | No |
| `evaluate_triage_state` | every answer → reducer → `SafetyPolicyEngine` | No |
| `find_appointment_options` | `SearchAppointments` command → `get_available_appointments` → `rank_appointment_options` | No |
| `request_human_review` | `RequestHumanReview` command → transfer to the human-review target, else callback script | No |
| `record_call_summary` | end of call, only if `allow_record_writes` and never for EMERGENCY | No |
| `escalate_emergency` | `Escalate` command → transfer to the emergency target, else emergency script | No |
| (corrections) | `CallOrchestrator.submit_correction(call_id, fact)`: operator/agent tool; Guava has no documented caller-initiated correction event | Not mapped yet |

## What is mocked today

| Real component | Stand-in | Notes |
| --- | --- | --- |
| Guava speech, turn-taking, field extraction | Scripted field values (`DeterministicInboundMock`, `clinical_triage.demo` driver) | No speech recognition or language understanding anywhere |
| Guava `Call` object | `MockCallPort` / `guava.testing.MockCall` (adapter tests) | `guava.Agent`/`guava.Client` are never constructed in tests |
| Transfer destinations | Per-target mock outcomes | Live requires a reviewed `TransferDirectory` |
| EHR | `SyntheticEHR` | Live OpenEMR supports identity reads only; no availability or booking |

## Credentials and configuration for a future live run

Do not commit any of these. Use the ignored `Hackathon/.env` or the operator's
environment, and never print values.

| Item | Where it comes from |
| --- | --- |
| Guava API key | `GUAVA_API_KEY` (read by `guava.Client` in `guava-sdk==0.45.0`) |
| Agent phone number | `guava.toml` `phone_number`; the SDK's examples read `GUAVA_AGENT_NUMBER` |
| Transfer directory | Operator-supplied E.164/SIP destinations per target ID (`EXAMPLE_EMERGENCY_HANDOFF`, `EXAMPLE_TRIAGE_NURSE` in the example config) |
| Approval flags | `live_calls_approved`, `live_transfer_approved` on `GuavaInboundAdapter` (default False); `allow_booking_writes`, `allow_record_writes` on `OrchestratorConfig` (default False) |

No webhook or HTTP endpoint is defined by this repository. The documented
SDK model is an outbound-connecting agent process (`listen_phone`); any
endpoint beyond `guava-docs.md` must come from Guava documentation, not
assumption.

## Checkpoint before any live use (requires Codex + human approval)

1. Confirm the Guava project, number, and credentials in `guava.toml` belong to
   this prototype and that only synthetic test callers will dial it.
2. Decide on telemetry handling with Guava.
3. Supply a reviewed transfer directory (clinical staff line) via ignored
   local configuration, or keep transfers off; with transfers off every
   escalation ends with the configured script (the emergency script tells the
   caller to call emergency services).
4. Replace the scaffold in `main.py` with orchestrator wiring in a separate,
   reviewed PR; keep `live_calls_approved` and `live_transfer_approved` off by
   default; load secrets from the ignored `.env`.
5. Test in the SDK's text chat mode first (`agent.chat()` per the scaffold's
   comments) before binding a phone number.
6. Run the deterministic scenarios first; then a single supervised synthetic
   call with a human on the transfer line.
7. Known live risks: Guava's model extracts field values (caller-reported,
   unverified); choice fields must return one of the configured codes or the
   answer is unparseable and routes to human review; `on_question` must stay a
   fixed deflection.
