# Clinical routing policy: EXAMPLE_UNREVIEWED

> **Status: EXAMPLE_UNREVIEWED. Not for use with real patients.** No clinician
> has reviewed this content. It exists only to exercise deterministic routing
> in a synthetic prototype. It is not comprehensive and is not medical advice.
> The system routes calls; it does not diagnose, prescribe, or determine that
> anyone is safe.

Scope: Fleet task `guava-red-flag-policy` (Issue #7).
Bundle: `Hackathon/config/policies/example-red-flags.json`
(`policy_id` `EXAMPLE_UNREVIEWED-family-medicine-routing`, version `0.1.0-example`).
Engine: `Hackathon/src/clinical_triage/safety/engine.py`.

## Guarantees enforced in code

- **Marked.** The loader refuses an `EXAMPLE_UNREVIEWED` bundle unless the caller
  passes `allow_example_unreviewed=True`. The engine refuses an example bundle
  whose `policy_id` does not contain `EXAMPLE_UNREVIEWED`, so the marker is
  present in every `PolicyEvaluation`, `TriageResult`, and audit record.
- **Tamper-evident.** The loader recomputes a canonical SHA-256 over the bundle
  (excluding the checksum field) and refuses a mismatch.
- **Emergency first.** Any matched `EMERGENCY` rule returns `EMERGENCY`
  immediately, regardless of reason for call or any other (even invalid)
  fact. Every emergency rule must name an escalation script ID.
- **Emergency not ruled out blocks everything else.** Until every emergency rule
  is known false, no ordinary disposition is produced; the evaluation names the
  facts still needed (red-flag screening comes first).
- **Missing and ambiguous evidence fails closed.** Predicates are three-valued;
  absent, undefined, wrongly typed, or wrongly unitized facts are *unknown*,
  never false. Unknown rules of higher precedence block lower ones; tied rules
  that disagree yield `CONFLICTING_RULES`; nothing matching yields
  `NO_RULE_MATCHED`; invalid values yield `INVALID_FACT_VALUE`. Each of these
  is a `fail_closed_reason` with no disposition, which the conversation layer
  routes to human review. There is no default disposition.
- **Auditable.** `SafetyPolicyEngine.trace()` returns one
  `RuleEvaluationTrace` per rule (triggered flag and the fact IDs used as
  evidence). Evaluation is order-independent and repeatable.
- **Interrupts scheduling.** The conversation reducer escalates on an
  `EMERGENCY` evaluation from any phase, clearing any offered slot; the
  scheduling policy separately refuses `EMERGENCY` and `HUMAN_REVIEW`.
- **No model input.** Only structured facts are evaluated. No LLM output or
  confidence score is a policy input.

## Precedence

Lower `priority` numbers take precedence. Rules are evaluated in
`(priority, rule_id)` order.

## Facts (caller-reported observations, not diagnoses)

| Fact ID | Type |
| --- | --- |
| `red_flag.chest_pain_now` | BOOLEAN |
| `red_flag.trouble_breathing_now` | BOOLEAN |
| `red_flag.new_confusion_or_one_sided_weakness` | BOOLEAN |
| `red_flag.heavy_bleeding_now` | BOOLEAN |
| `call.reason` | CODE (`SYMPTOM`, `FOLLOW_UP`, `ADMINISTRATIVE`, `MEDICATION_REFILL`) |
| `symptom.caller_rated_severity` | CODE (`MILD`, `MODERATE`, `SEVERE`) |
| `symptom.measured_temperature` | NUMBER, unit `Cel` only |

## Example rules

| Rule | Priority | Disposition | Condition |
| --- | --- | --- | --- |
| EX-EMERG-001 | 0 | EMERGENCY | chest pain now = true |
| EX-EMERG-002 | 0 | EMERGENCY | trouble breathing now = true |
| EX-EMERG-003 | 0 | EMERGENCY | new confusion or one-sided weakness = true |
| EX-EMERG-004 | 0 | EMERGENCY | heavy bleeding now = true |
| EX-URGENT-001 | 10 | URGENT_SAME_DAY | reason = SYMPTOM and caller-rated severity = SEVERE |
| EX-URGENT-002 | 11 | URGENT_SAME_DAY | reason = SYMPTOM and temperature >= 39.5 Cel |
| EX-SOON-001 | 20 | SOON | reason = SYMPTOM and severity = MODERATE |
| EX-ROUTINE-001 | 30 | ROUTINE | reason = SYMPTOM and severity = MILD |
| EX-ROUTINE-002 | 30 | ROUTINE | reason = FOLLOW_UP |
| EX-ADMIN-001 | 40 | ADMINISTRATIVE | reason in {ADMINISTRATIVE, MEDICATION_REFILL} |

All emergency rules use script `EXAMPLE_UNREVIEWED_SCRIPT_EMERGENCY_SERVICES`,
whose wording has not been written or reviewed.

## Known consequences of the example design

- Every caller is screened for all four red flags, including administrative
  callers, because a volunteered red flag must escalate regardless of reason.
- A `SYMPTOM` caller rating severity `MILD` or `MODERATE` is also asked for a
  measured temperature, because EX-URGENT-002 outranks the ordinary rules; a
  caller who cannot supply a Celsius value is routed to human review.
- Unit conversion is not performed by the engine; the voice layer must supply
  normalized values or the evaluation fails closed.

## Clinical review TODOs (blocking any real use)

1. A named clinician must author or approve the fact set, thresholds, rule
   precedence, and dispositions, and set `review_status: CLINICIAN_REVIEWED`
   with `approved_by`.
2. Emergency script wording (including when to direct callers to emergency
   services) must be written and approved.
3. Coverage is deliberately minimal; a reviewed protocol would need many more
   red flags, age/pregnancy considerations, and follow-up logic.
4. Define how caller uncertainty ("I don't know") is represented and routed.
5. Validate against clinician-authored synthetic cases, including near misses.
