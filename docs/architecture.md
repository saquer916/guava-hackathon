# Architecture

## Authority and clinical boundary

Codex is the architectural and final review gate. Workers implement bounded
Fleet tasks and report claims; deterministic tests, CI, and identified runtime
observations provide evidence. Humans retain approval over merges and every
live clinical, voice, EHR, transfer, or deployment operation.

This prototype gathers history and routes calls. It does not diagnose,
prescribe, certify safety, replace emergency evaluation, or let scheduling
capacity downgrade a safety disposition. All fixtures are synthetic.

## System shape

```text
Guava voice transport (or deterministic mock)
                |
          VoiceAdapter
                |
         CallOrchestrator
          /      |       \
 Conversation  Triage   Audit
    State      Engine    Record
                 |
          SafetyPolicyEngine
                 |
         SchedulingEngine
                 |
             EHRAdapter
                 |
       OpenEMR FHIR R4 (local)
```

Provider SDKs stop at adapters. Domain models, conversation state, explicit
safety rules, scheduling policy, and orchestration do not import Guava or FHIR
libraries. Guava receives high-level tools rather than arbitrary FHIR access.

## Core contracts

- `VoiceAdapter` translates calls and task events without owning clinical
  logic. The mock replays explicit events; it never pretends to perform speech
  recognition or LLM extraction.
- `EHRAdapter` exposes patient matching, identity verification, clinical
  context, appointment queries/mutations, and call/triage recording. Every
  operation reports attempted/completed status for audit.
- `ConversationState` tracks known facts, unknown critical facts, prior
  questions, clarifications, and prohibited repetition separately from
  clinical state.
- `SafetyPolicyEngine` evaluates versioned deterministic rules before ordinary
  question or scheduling decisions. Rules name their trigger evidence and are
  explicitly marked as example policy pending clinician review.
- `TriageEngine` returns a configured disposition, triggers, symptoms, red
  flags, missing critical questions, scheduling window, human-review flag, and
  rationale. Confidence is informational, never clinical validation.
- `SchedulingEngine` ranks open, same-day, cancellation, short-visit,
  alternative-provider, next-available, and permitted telehealth options. It
  may request overbook review but never performs an autonomous overbook.
- `AuditRecord` uses stable synthetic identifiers and records decisions and
  effects without retaining unnecessary raw conversation.

## Initial dispositions

The configuration vocabulary is `EMERGENCY`, `URGENT_SAME_DAY`, `SOON`,
`ROUTINE`, `ADMINISTRATIVE`, and `HUMAN_REVIEW`. Emergency is terminal for the
ordinary scheduling path. Unknown identity, policy ambiguity, missing critical
facts, and adapter failure fail toward human review.

## OpenEMR boundary

OpenEMR runs locally in Docker with authentication and loopback-only ports.
The adapter discovers the FHIR CapabilityStatement rather than assuming every
desired operation exists. FHIR R4 is preferred; documented gaps may use a
separate, explicit OpenEMR-standard-API implementation. Synthetic fixture
seeding is deterministic and repeatable.

## Delivery decisions

- Python is retained because the repository and Guava SDK are Python-native.
- `uv` provides locked dependencies and Python 3.11+ portability.
- The first demo is a CLI simulator; a web dashboard is unnecessary.
- JSON/JSONL are used for deterministic fixtures, tool payloads, and audit
  output. No database is introduced outside OpenEMR.
- Default verification is offline. Live Guava and OpenEMR tests are opt-in and
  separately identified.
