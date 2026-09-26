# ADR 0002: Explicit state and deterministic policy before provider actions

Status: accepted for the synthetic prototype; clinical content unapproved

## Context

An open-ended voice prompt cannot safely own clinical routing, emergency
escalation, appointment mutation, or audit provenance. Callback retries and
answer corrections can otherwise repeat effects or leave decisions stale.

## Decision

Separate clinical facts from conversation history. A future pure reducer will
apply versioned events to immutable session state and emit typed commands. Every
new or corrected fact forces policy reevaluation. Emergency is a terminal path
for ordinary scheduling. Unknown state, invalid policy, conflicting rules,
missing critical facts, stale versions, and provider errors fail toward human
review or an approved escalation path.

Policy bundles contain machine-evaluable predicates, stable rule IDs, version,
checksum, effective date, and review status. The repository may contain clearly
marked example rules for tests, but no policy is approved for real patients
without an identified clinical reviewer. Generated model confidence is not a
policy input and is never clinical validation.

Appointment commands require explicit confirmation and idempotency. A success
message requires a provider receipt/appointment ID. Availability is a raw,
timestamped snapshot. Scheduling policy turns it into expiring offers, and a
mutation requires an explicit confirmation tied to the offer, snapshot, slot,
and confirmation event. Stale offers fail closed. Scheduling availability
cannot downgrade a safety disposition.

Protected decision records may contain structured clinical facts and rule
evidence. Sanitized Fleet telemetry contains stable identifiers, outcomes, and
error codes only. The EHR boundary receives a minimal coded call summary rather
than the protected decision record or an operational log record.

## Consequences

- Deterministic scenario tests can prove decisions without a live LLM.
- Exact escalation wording comes from reviewed script IDs, not generated text.
- State persistence and concurrency control remain required before any real
  patient use; in-memory state is acceptable only for synthetic demonstrations.
- Protected decision audit and sanitized operational telemetry remain separate.
