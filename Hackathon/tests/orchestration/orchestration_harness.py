"""Offline harness: DeterministicInboundMock + SyntheticEHR + InMemoryAuditSink + FixedClock.

Everything is synthetic. Scripts set voice fields directly; nothing here
recognizes speech or extracts meaning from language.
"""

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from clinical_triage.adapters.voice_mock import (
    DeterministicInboundMock,
    MockCallPort,
    MockEvent,
    MockScriptError,
)
from clinical_triage.audit import InMemoryAuditSink
from clinical_triage.domain.audit import AuditRecord, DecisionRecord, OperationOutcome
from clinical_triage.domain.voice import FieldSpec, FieldValue, InboundHandlers, SessionEnded
from clinical_triage.fixtures import FIXTURE_CLOCK, FixedClock, SyntheticEHR, build_fixtures
from clinical_triage.orchestration import CallContext, CallOrchestrator, offer_field_key
from clinical_triage.orchestration.example import (
    EMERGENCY_TARGET,
    HUMAN_REVIEW_TARGET,
    example_orchestrator_config,
    example_policy_engine,
    example_scheduling_policy,
)

ACCEPT_ALL_TRANSFERS: Mapping[str, str | None] = {
    EMERGENCY_TARGET.target_id: None,
    HUMAN_REVIEW_TARGET.target_id: None,
}


@dataclass
class Harness:
    orchestrator: CallOrchestrator
    mock: DeterministicInboundMock
    ehr: SyntheticEHR
    audit: InMemoryAuditSink
    clock: FixedClock
    transfer_outcomes: Mapping[str, str | None]

    def run(self, script: tuple[MockEvent, ...], call_id: str = "call-1") -> "Result":
        port = self.mock.run(call_id, script)
        return Result(port=port, ctx=self.orchestrator.calls[call_id], harness=self)

    def stepper(self, call_id: str = "call-1") -> "Stepper":
        return Stepper(self, call_id)


@dataclass
class Result:
    port: MockCallPort
    ctx: CallContext
    harness: Harness

    @property
    def audit(self) -> AuditRecord:
        records = [
            r for r in self.harness.audit.audit_records if r.call_id == self.ctx.state.call_id
        ]
        assert len(records) == 1
        return records[0]

    @property
    def decision(self) -> DecisionRecord:
        records = [
            r for r in self.harness.audit.decision_records if r.call_id == self.ctx.state.call_id
        ]
        assert len(records) == 1
        return records[0]

    def operations(self, operation_type: str) -> list[OperationOutcome]:
        return [o.outcome for o in self.audit.operations if o.operation_type == operation_type]

    def task_ids(self) -> list[str]:
        return [t.task_id for t in self.port.tasks]


@dataclass
class Stepper:
    """Drives one mock call event by event so tests can act mid-call."""

    harness: Harness
    call_id: str
    handlers: InboundHandlers = field(init=False)
    port: MockCallPort = field(init=False)

    def __post_init__(self) -> None:
        self.handlers = self.harness.orchestrator.handlers()
        self.port = MockCallPort(
            call_id=self.call_id, transfer_outcomes=self.harness.transfer_outcomes
        )
        self.handlers.on_call_start(self.port)

    @property
    def ctx(self) -> CallContext:
        return self.harness.orchestrator.calls[self.call_id]

    def answer(self, task_id: str, values: Mapping[str, FieldValue]) -> None:
        task = self.port.active_task
        if self.port.ended is not None:
            raise MockScriptError("session already ended")
        if task is None or task.task_id != task_id:
            raise MockScriptError(f"task {task_id!r} is not active")
        keys = {item.key for item in task.checklist if isinstance(item, FieldSpec)}
        if set(values) != keys:
            raise MockScriptError(f"answer keys {sorted(values)} != task keys {sorted(keys)}")
        self.port.values.update(values)
        self.handlers.on_task_complete[task_id](self.port)

    def end(self, reason: str | None = None) -> Result:
        if reason is not None:
            self.port.ended = SessionEnded(reason=reason)  # type: ignore[arg-type]
        elif self.port.ended is None:
            self.port.ended = SessionEnded(reason="user-hangup")
        assert self.handlers.on_session_end is not None
        self.handlers.on_session_end(self.port, self.port.ended)
        return Result(port=self.port, ctx=self.ctx, harness=self.harness)


def build(
    *,
    allow_booking_writes: bool = False,
    allow_record_writes: bool = False,
    transfer_outcomes: Mapping[str, str | None] = ACCEPT_ALL_TRANSFERS,
    unavailable_operations: frozenset[str] = frozenset(),
    slots_taken_after_snapshot: frozenset[str] = frozenset(),
    booked_slot_ids: Mapping[str, str] | None = None,
    ehr: SyntheticEHR | None = None,
) -> Harness:
    clock = FixedClock(FIXTURE_CLOCK)
    ehr = ehr or SyntheticEHR(
        fixtures=build_fixtures(),
        clock=clock,
        unavailable_operations=unavailable_operations,
        slots_taken_after_snapshot=slots_taken_after_snapshot,
        booked_slot_ids=dict(booked_slot_ids or {}),
    )
    audit = InMemoryAuditSink()
    config = example_orchestrator_config(
        allow_booking_writes=allow_booking_writes, allow_record_writes=allow_record_writes
    )
    orchestrator = CallOrchestrator(
        config=config,
        policy=example_policy_engine(),
        scheduling_policy=example_scheduling_policy(),
        ehr=ehr,
        audit=audit,
        clock=clock,
    )
    mock = DeterministicInboundMock(transfer_outcomes=transfer_outcomes)
    mock.bind(config.agent, orchestrator.handlers())
    return Harness(orchestrator, mock, ehr, audit, clock, transfer_outcomes)


# --- script builders ------------------------------------------------------------


def answer(task_id: str, key: str, value: FieldValue) -> tuple[MockEvent, ...]:
    return (MockEvent.field(key, value), MockEvent.complete(task_id))


def consent(value: str = "YES") -> tuple[MockEvent, ...]:
    return (MockEvent.start(), *answer("q.consent", "consent.continue", value))


def red_flags(
    chest: str = "NO", breathing: str = "NO", neuro: str = "NO", bleeding: str = "NO"
) -> tuple[MockEvent, ...]:
    events: list[MockEvent] = []
    for task_id, key, value, stop in (
        ("q.red_flag.chest_pain", "red_flag.chest_pain_now", chest, chest == "YES"),
        ("q.red_flag.breathing", "red_flag.trouble_breathing_now", breathing, breathing == "YES"),
        (
            "q.red_flag.neuro",
            "red_flag.new_confusion_or_one_sided_weakness",
            neuro,
            neuro == "YES",
        ),
        ("q.red_flag.bleeding", "red_flag.heavy_bleeding_now", bleeding, bleeding == "YES"),
    ):
        events.extend(answer(task_id, key, value))
        if stop:
            break
    return tuple(events)


def reason(value: str) -> tuple[MockEvent, ...]:
    return answer("q.call.reason", "call.reason", value)


def severity(value: str) -> tuple[MockEvent, ...]:
    return answer("q.symptom.severity", "symptom.caller_rated_severity", value)


def temperature(value: str) -> tuple[MockEvent, ...]:
    return answer("q.symptom.temperature", "symptom.measured_temperature", value)


def temperature_confirm(value: str) -> tuple[MockEvent, ...]:
    return answer("q.symptom.temperature.confirm", "symptom.measured_temperature.confirm", value)


def identity(given: str, family: str, birth_date: str) -> tuple[MockEvent, ...]:
    return (
        MockEvent.field("identity.given_name", given),
        MockEvent.field("identity.family_name", family),
        MockEvent.field("identity.birth_date", birth_date),
        MockEvent.complete("identity"),
    )


def offer(value: str = "YES", task_id: str = "offer") -> tuple[MockEvent, ...]:
    return answer(task_id, offer_field_key(task_id), value)


PATIENT_A = identity("Avery", "Synthetic", "1980-01-02")
PATIENT_B = identity("Blake", "Synthetic", "1975-03-04")
PATIENT_C = identity("Casey", "Synthetic", "1990-05-06")
PATIENT_F = identity("Finley", "Synthetic", "1995-11-12")


def leaves(document: Any) -> Iterator[tuple[str, Any]]:
    """Yield (key, leaf) pairs from a JSON-compatible document."""

    if isinstance(document, dict):
        for key, value in document.items():
            if isinstance(value, (dict, list)):
                yield from leaves(value)
            else:
                yield key, value
    elif isinstance(document, list):
        for item in document:
            yield from leaves(item)


def telemetry_json(audit: InMemoryAuditSink) -> list[Any]:
    """The operational (non-protected) streams, serialized exactly as a sink would."""

    return [json.loads(r.model_dump_json()) for r in audit.audit_records] + [
        json.loads(e.model_dump_json()) for e in audit.operational_events
    ]
