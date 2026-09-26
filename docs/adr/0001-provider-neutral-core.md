# ADR 0001: Provider-neutral clinical core

Status: accepted for the prototype

## Context

The product begins with Guava Voice AI and OpenEMR but must permit other voice
and EHR providers. Clinical reasoning and scheduling safety cannot inherit
provider callback or FHIR payload semantics.

## Decision

Domain models and ports live in `clinical_triage.domain` and import neither
Guava nor HTTP/FHIR clients. Guava and OpenEMR translate only at adapter
boundaries. The call orchestrator consumes provider-neutral events and emits
typed commands. Guava never constructs arbitrary FHIR queries.

The initial voice port mirrors only the documented inbound lifecycle already
needed by the scaffold: call start, question, task completion, session end,
task assignment, field retrieval, and hangup. Additional SDK callbacks are
added only with a concrete use case and contract test.

## Consequences

- Provider replacement does not redesign triage or safety policy.
- Adapters carry mapping and capability-discovery complexity.
- The Guava mock does not pretend to implement speech recognition, LLM field
  extraction, audio, timing, or WebSocket behavior.
- OpenEMR operations remain unavailable until its live CapabilityStatement and
  authentication path prove support.
