"""Audit sinks that keep protected decision evidence apart from operational telemetry.

Operational output (AuditRecord, OperationalEvent) carries identifiers, codes,
and outcomes only. DecisionRecord carries structured clinical facts and goes
to a separate protected destination. Neither stores free text or transcripts.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from clinical_triage.domain.audit import AuditRecord, DecisionRecord, OperationalEvent


@dataclass
class InMemoryAuditSink:
    audit_records: list[AuditRecord] = field(default_factory=list)
    decision_records: list[DecisionRecord] = field(default_factory=list)
    operational_events: list[OperationalEvent] = field(default_factory=list)

    def append_audit_record(self, record: AuditRecord) -> None:
        self.audit_records.append(record)

    def append_decision_record(self, record: DecisionRecord) -> None:
        self.decision_records.append(record)

    def emit_operational_event(self, event: OperationalEvent) -> None:
        self.operational_events.append(event)


class JsonlAuditSink:
    """Appends JSON lines; the protected file must live outside operational log shipping."""

    def __init__(self, *, operational_path: Path, protected_path: Path) -> None:
        if operational_path.resolve() == protected_path.resolve():
            raise ValueError("protected decision records need a separate destination")
        self._operational = operational_path
        self._protected = protected_path

    def append_audit_record(self, record: AuditRecord) -> None:
        self._write(self._operational, {"type": "audit", **record.model_dump(mode="json")})

    def append_decision_record(self, record: DecisionRecord) -> None:
        self._write(self._protected, {"type": "decision", **record.model_dump(mode="json")})

    def emit_operational_event(self, event: OperationalEvent) -> None:
        self._write(self._operational, {"type": "event", **event.model_dump(mode="json")})

    @staticmethod
    def _write(path: Path, document: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(document, sort_keys=True) + "\n")
