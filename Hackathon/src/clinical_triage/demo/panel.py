"""Developer-only rendering of a simulated call: transcript plus a diagnostic panel.

The diagnostic panel exposes policy, rule, and EHR internals. It is for
developers running synthetic scenarios and must never be shown to a caller or
built into a patient-facing interface.
"""

from collections import Counter
from typing import Any

from clinical_triage.demo.scenarios import ScenarioRun
from clinical_triage.domain.audit import OperationOutcome

BANNER = (
    "SYNTHETIC DEMO - scripted caller turns, no speech recognition, EXAMPLE_UNREVIEWED "
    "policy and wording. Developer panel: never patient-facing."
)


def summarize(run: ScenarioRun) -> dict[str, Any]:
    """Structured developer summary derived from the audit and decision records."""

    ctx = run.ctx
    audit = next(r for r in run.audit.audit_records if r.call_id == ctx.state.call_id)
    triage = ctx.triage
    ops = [
        f"{o.operation_type}:{o.outcome.value}" + (f"({o.error_code})" if o.error_code else "")
        for o in audit.operations
    ]
    ehr_writes = [
        o.operation_type
        for o in audit.operations
        if o.target_system == "ehr"
        and o.outcome is OperationOutcome.COMPLETED
        and o.operation_type.startswith(("EHR.CREATE", "EHR.RECORD", "EHR.UPDATE"))
    ]
    red_flag_facts = [f for f in audit.fact_ids_recorded if f.startswith("red_flag.")]
    return {
        "scenario": run.scenario.scenario_id,
        "ehr_backend": run.ehr_backend,
        "patient_matched": ctx.patient_id is not None,
        "synthetic_patient_id": ctx.patient_id,
        "questions_asked": list(audit.question_ids_asked),
        "facts_recorded": len(audit.fact_ids_recorded),
        "red_flags_screened": f"{len(red_flag_facts)}/4",
        "outstanding_policy_facts": list(ctx.state.clinical.important_missing_fact_ids),
        "deciding_rules": list(triage.trigger_rule_ids) if triage else [],
        "rules_true_in_trace": [t.rule_id for t in audit.rule_evaluations if t.triggered],
        "disposition": audit.disposition.value if audit.disposition else None,
        "requires_human_review": triage.requires_human_review if triage else True,
        "rationale": triage.rationale_code if triage else None,
        "confidence": None,
        "final_phase": ctx.state.phase.value,
        "appointment_id": ctx.appointment_id,
        "offers_considered": len(audit.appointment_option_ids_considered),
        "human_decisions": list(audit.human_decision_codes),
        "operations": ops,
        "ehr_calls": dict(Counter(run.ehr.calls)),
        "ehr_writes_completed": ehr_writes,
        "errors": list(audit.error_codes),
    }


def render(run: ScenarioRun) -> str:
    summary = summarize(run)
    lines = [
        "=" * 78,
        f"{run.scenario.title}  [{run.scenario.scenario_id}]",
        run.scenario.summary,
        "-" * 78,
    ]
    for turn in run.drive.transcript:
        lines.append(f"{turn.speaker:>7}: {turn.text}")
    lines += ["-" * 78, "Developer panel (synthetic, not patient-facing)"]
    panel = (
        ("EHR backend", summary["ehr_backend"]),
        (
            "Patient matched",
            f"yes ({summary['synthetic_patient_id']})" if summary["patient_matched"] else "no",
        ),
        (
            "Facts recorded",
            f"{summary['facts_recorded']} (red flags screened {summary['red_flags_screened']})",
        ),
        ("Outstanding policy facts", ", ".join(summary["outstanding_policy_facts"]) or "none"),
        ("Deciding rules", ", ".join(summary["deciding_rules"]) or "none (fail-closed)"),
        ("Rules true in trace", ", ".join(summary["rules_true_in_trace"]) or "none"),
        ("Disposition", f"{summary['disposition']} (confidence: none; rule-based)"),
        ("Requires human review", str(summary["requires_human_review"])),
        ("Appointment", summary["appointment_id"] or "not booked"),
        ("Human decisions", ", ".join(summary["human_decisions"]) or "none"),
        ("EHR writes completed", ", ".join(summary["ehr_writes_completed"]) or "none"),
        ("Operations", "; ".join(summary["operations"]) or "none"),
        ("Errors", ", ".join(summary["errors"]) or "none"),
    )
    width = max(len(label) for label, _ in panel)
    lines += [f"  {label:<{width}} : {value}" for label, value in panel]
    return "\n".join(lines)
