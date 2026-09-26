"""SDK translation tests. Uses guava.testing.MockCall (queues commands, no network).

No test constructs guava.Agent or guava.Client: both authenticate and call Guava.
"""

from collections.abc import Callable
from typing import Any

import pytest
from guava.commands import SetTaskCommand, TransferCommand
from guava.testing import MockCall
from guava.types import SerializableField

from clinical_triage.adapters.guava import (
    GuavaCallPort,
    GuavaInboundAdapter,
    LiveVoiceNotApproved,
    TransferDirectory,
    UnsupportedVoiceSpec,
    live_agent_factory,
    to_guava_checklist,
    to_session_ended,
)
from clinical_triage.domain.voice import (
    AgentSpec,
    CallPort,
    FieldSpec,
    InboundHandlers,
    SaySpec,
    SessionEnded,
    TaskSpec,
    TransferTarget,
)

DIRECTORY = TransferDirectory({"clinical-triage-nurse": "+15550100999"})
NURSE = TransferTarget(target_id="clinical-triage-nurse", display_name="Triage nurse")
TASK = TaskSpec(
    task_id="collect.call.reason",
    objective="Collect the structured reason for the call.",
    checklist=(
        SaySpec("This line is a synthetic prototype."),
        FieldSpec(
            key="call.reason",
            field_type="multiple_choice",
            choices=("SYMPTOM", "FOLLOW_UP"),
            required=False,
            sensitive=True,
        ),
        "Do not give medical advice.",
    ),
)


def port(call: MockCall, *, approved: bool = False) -> GuavaCallPort:
    return GuavaCallPort(call, directory=DIRECTORY, live_transfer_approved=approved)


# --- translation ------------------------------------------------------------------


def test_set_task_uses_documented_task_field_and_say() -> None:
    call = MockCall(session_id="mock-1")
    port(call).set_task(TASK)
    (command,) = call._command_queue
    assert isinstance(command, SetTaskCommand)
    assert command.task_id == "collect.call.reason"
    kinds = [getattr(item, "item_type", None) for item in command.action_items]
    assert kinds == ["say", "field", "todo"]
    field = command.action_items[1]
    assert isinstance(field, SerializableField)
    assert field.key == "call.reason" and field.choices == ["SYMPTOM", "FOLLOW_UP"]
    assert field.sensitive is True and field.required is False


@pytest.mark.parametrize(
    "spec",
    [
        FieldSpec(key="slot", field_type="calendar_slot", searchable=True),
        FieldSpec(key="reason", field_type="text", choices=("A",)),
    ],
)
def test_undocumented_or_unsupported_field_options_are_refused(spec: FieldSpec) -> None:
    with pytest.raises(UnsupportedVoiceSpec):
        to_guava_checklist(TaskSpec(task_id="t", objective="o", checklist=(spec,)))


def test_duplicate_field_keys_are_refused() -> None:
    duplicate = (FieldSpec(key="a"), FieldSpec(key="a"))
    with pytest.raises(UnsupportedVoiceSpec):
        to_guava_checklist(TaskSpec(task_id="t", objective="o", checklist=duplicate))


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("user-hangup", "user-hangup"),
        ("bot-hangup", "bot-hangup"),
        ("bot-transfer", "bot-transfer"),
        ("bot-failure", "bot-failure"),
        ("voicemail", "bot-failure"),
        ("something-new", "bot-failure"),
    ],
)
def test_termination_reasons_map_conservatively(reason: str, expected: str) -> None:
    assert to_session_ended(reason) == SessionEnded(reason=expected)  # type: ignore[arg-type]


def test_get_field_returns_only_scalar_values() -> None:
    call = MockCall(session_id="mock-1")
    call.set_field("n", 3)
    call.set_field("when", object())
    assert port(call).get_field("n") == 3
    assert isinstance(port(call).get_field("when"), str)
    assert port(call).get_field("missing") is None


def test_hangup_uses_documented_hangup() -> None:
    call = MockCall(session_id="mock-1")
    port(call).hangup("EXAMPLE_UNREVIEWED_SCRIPT_CLOSE")
    assert len(call._command_queue) == 1


# --- transfer / escalation boundary --------------------------------------------------


def test_transfer_is_refused_without_explicit_approval_and_sends_nothing() -> None:
    call = MockCall(session_id="mock-1")
    result = port(call).transfer(NURSE)
    assert not result.accepted and result.failure_code == "LIVE_TRANSFER_NOT_APPROVED"
    assert call._command_queue == []


def test_transfer_to_unconfigured_target_is_refused() -> None:
    call = MockCall(session_id="mock-1")
    result = port(call, approved=True).transfer(TransferTarget("unknown", "Unknown"))
    assert result.failure_code == "TRANSFER_TARGET_NOT_CONFIGURED"
    assert call._command_queue == []


def test_approved_transfer_submits_documented_soft_transfer() -> None:
    call = MockCall(session_id="mock-1")
    result = port(call, approved=True).transfer(NURSE)
    assert result.accepted and result.transfer_id == "mock-1:clinical-triage-nurse"
    (command,) = call._command_queue
    assert isinstance(command, TransferCommand)
    assert command.to_number == "+15550100999" and command.soft_transfer is True


@pytest.mark.parametrize("destination", ["5550100", "tel:+15550100", "+1 555 0100", ""])
def test_directory_rejects_malformed_destinations(destination: str) -> None:
    with pytest.raises(ValueError):
        TransferDirectory({"target": destination})


def test_directory_repr_hides_destinations() -> None:
    assert "+1555" not in repr(DIRECTORY)


# --- inbound binding ------------------------------------------------------------------


class RecordingAgent:
    """Implements the documented guava.Agent decorator surface without the network."""

    def __init__(self) -> None:
        self.call_start: Callable[[Any], None] | None = None
        self.question: Callable[[Any, str], str] | None = None
        self.completions: dict[str, Callable[[Any], None]] = {}
        self.session_end: Callable[[Any, Any], None] | None = None
        self.listened: list[str] = []

    def on_call_start(self, fn: Callable[[Any], None], /) -> Callable[[Any], None]:
        self.call_start = fn
        return fn

    def on_question(self, fn: Callable[[Any, str], str], /) -> Callable[[Any, str], str]:
        self.question = fn
        return fn

    def on_task_complete(
        self, task_name: str, /
    ) -> Callable[[Callable[[Any], None]], Callable[[Any], None]]:
        def register(fn: Callable[[Any], None]) -> Callable[[Any], None]:
            self.completions[task_name] = fn
            return fn

        return register

    def on_session_end(self, fn: Callable[[Any, Any], None], /) -> Callable[[Any, Any], None]:
        self.session_end = fn
        return fn

    def listen_phone(self, agent_number: str) -> None:
        self.listened.append(agent_number)


class Event:
    def __init__(self, termination_reason: str) -> None:
        self.termination_reason = termination_reason


def bound(
    approved: bool = False,
) -> tuple[GuavaInboundAdapter, RecordingAgent, list[tuple[str, Any]]]:
    agent = RecordingAgent()
    seen: list[tuple[str, Any]] = []
    adapter = GuavaInboundAdapter(
        directory=DIRECTORY, agent_factory=lambda spec: agent, live_calls_approved=approved
    )

    def record(name: str) -> Callable[..., None]:
        return lambda call_port, *rest: seen.append((name, (call_port, *rest)))

    handlers = InboundHandlers(
        on_call_start=record("start"),
        on_question=lambda call_port, question: "FIXED_DEFLECTION",
        on_task_complete={"collect.call.reason": record("complete")},
        on_escalate=lambda call_port, request: call_port.transfer(request.target),
        on_session_end=record("end"),
    )
    adapter.bind(
        AgentSpec(name=None, organization="Synthetic Clinic", purpose="synthetic"), handlers
    )
    return adapter, agent, seen


def test_bind_registers_documented_callbacks_with_one_port_per_call() -> None:
    _, agent, seen = bound()
    call = MockCall(session_id="mock-7")
    assert agent.call_start and agent.session_end and agent.question
    agent.call_start(call)
    agent.completions["collect.call.reason"](call)
    assert agent.question(call, "anything") == "FIXED_DEFLECTION"
    agent.session_end(call, Event("bot-transfer"))
    assert [name for name, _ in seen] == ["start", "complete", "end"]
    ports: list[CallPort] = [args[0] for _, args in seen]
    assert ports[0] is ports[1] is ports[2]
    assert ports[0].id == "mock-7"
    assert seen[2][1][1] == SessionEnded(reason="bot-transfer")


def test_listen_phone_requires_explicit_approval() -> None:
    adapter, agent, _ = bound(approved=False)
    with pytest.raises(LiveVoiceNotApproved):
        adapter.listen_phone("+15550100000")
    assert agent.listened == []


def test_approved_listen_phone_delegates_to_documented_entrypoint() -> None:
    adapter, agent, _ = bound(approved=True)
    with pytest.raises(RuntimeError, match="returned unexpectedly"):
        adapter.listen_phone("+15550100000")
    assert agent.listened == ["+15550100000"]


def test_default_factory_is_live_but_adapter_construction_does_not_call_it() -> None:
    adapter = GuavaInboundAdapter(directory=DIRECTORY)
    assert adapter._agent_factory is live_agent_factory
    assert adapter._agent is None
