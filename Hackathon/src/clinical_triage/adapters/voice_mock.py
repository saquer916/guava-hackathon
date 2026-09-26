"""Deterministic inbound-call mock for the provider-neutral voice port.

The mock replays an explicit script. It does not recognize speech, extract
fields from language, time turns, or generate replies: a scripted `field`
event sets a value directly, and a `complete` event fires the task handler
only if the active task's required fields were all supplied. It imports no
provider SDK and never places or transfers a real call.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, NoReturn

from clinical_triage.domain.voice import (
    AgentSpec,
    FieldSpec,
    FieldValue,
    InboundHandlers,
    SessionEnded,
    TaskSpec,
    TransferResult,
    TransferTarget,
)

MockEventKind = Literal["start", "field", "complete", "question", "hangup"]


class MockScriptError(ValueError):
    """The script is inconsistent with the call's state (a test bug, not a call event)."""


@dataclass(frozen=True)
class MockEvent:
    kind: MockEventKind
    key: str = ""
    value: FieldValue = None
    text: str = ""

    @classmethod
    def start(cls) -> "MockEvent":
        return cls("start")

    @classmethod
    def field(cls, key: str, value: FieldValue) -> "MockEvent":
        return cls("field", key=key, value=value)

    @classmethod
    def complete(cls, task_id: str) -> "MockEvent":
        return cls("complete", key=task_id)

    @classmethod
    def question(cls, text: str) -> "MockEvent":
        return cls("question", text=text)

    @classmethod
    def hangup(cls) -> "MockEvent":
        return cls("hangup")


@dataclass
class MockCallPort:
    call_id: str
    transfer_outcomes: Mapping[str, str | None]
    tasks: list[TaskSpec] = field(default_factory=list)
    values: dict[str, FieldValue] = field(default_factory=dict)
    transfers: list[TransferTarget] = field(default_factory=list)
    hangups: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    ended: SessionEnded | None = None

    @property
    def id(self) -> str:
        return self.call_id

    @property
    def active_task(self) -> TaskSpec | None:
        return self.tasks[-1] if self.tasks else None

    def set_task(self, task: TaskSpec) -> None:
        self._require_live()
        self.tasks.append(task)

    def get_field(self, key: str) -> FieldValue:
        return self.values.get(key)

    def transfer(self, target: TransferTarget) -> TransferResult:
        self._require_live()
        self.transfers.append(target)
        transfer_id = f"{self.call_id}:{target.target_id}"
        failure = self.transfer_outcomes.get(target.target_id, "TRANSFER_TARGET_NOT_CONFIGURED")
        if failure is None:
            self.ended = SessionEnded(reason="bot-transfer")
            return TransferResult(transfer_id, accepted=True)
        return TransferResult(transfer_id, accepted=False, failure_code=failure)

    def hangup(self, final_instructions: str = "") -> None:
        self._require_live()
        self.hangups.append(final_instructions)
        self.ended = SessionEnded(reason="bot-hangup")

    def _require_live(self) -> None:
        if self.ended is not None:
            raise MockScriptError("command issued after the session ended")


class DeterministicInboundMock:
    def __init__(self, *, transfer_outcomes: Mapping[str, str | None] | None = None) -> None:
        self._transfer_outcomes = dict(transfer_outcomes or {})
        self._handlers: InboundHandlers | None = None
        self.spec: AgentSpec | None = None

    def bind(self, spec: AgentSpec, handlers: InboundHandlers) -> None:
        self.spec = spec
        self._handlers = handlers

    def listen_phone(self, phone_number: str) -> NoReturn:
        raise RuntimeError("the deterministic mock never binds a phone number")

    def run(self, call_id: str, script: tuple[MockEvent, ...]) -> MockCallPort:
        if self._handlers is None:
            raise MockScriptError("bind() must be called before run()")
        handlers = self._handlers
        port = MockCallPort(call_id=call_id, transfer_outcomes=self._transfer_outcomes)
        for event in script:
            if port.ended is not None:
                break
            if event.kind == "start":
                handlers.on_call_start(port)
            elif event.kind == "field":
                self._set_field(port, event.key, event.value)
            elif event.kind == "complete":
                self._complete(port, handlers, event.key)
            elif event.kind == "question":
                if handlers.on_question is None:
                    raise MockScriptError("no question handler is bound")
                port.answers.append(handlers.on_question(port, event.text))
            else:
                port.ended = SessionEnded(reason="user-hangup")
        if port.ended is None:
            port.ended = SessionEnded(reason="user-hangup")
        if handlers.on_session_end is not None:
            handlers.on_session_end(port, port.ended)
        return port

    @staticmethod
    def _set_field(port: MockCallPort, key: str, value: FieldValue) -> None:
        task = port.active_task
        keys = (
            {item.key for item in task.checklist if isinstance(item, FieldSpec)} if task else set()
        )
        if key not in keys:
            raise MockScriptError(f"field {key!r} is not in the active task")
        port.values[key] = value

    @staticmethod
    def _complete(port: MockCallPort, handlers: InboundHandlers, task_id: str) -> None:
        task = port.active_task
        if task is None or task.task_id != task_id:
            raise MockScriptError(f"task {task_id!r} is not active")
        missing = [
            item.key
            for item in task.checklist
            if isinstance(item, FieldSpec) and item.required and item.key not in port.values
        ]
        if missing:
            raise MockScriptError(f"required fields not supplied: {missing}")
        handler = handlers.on_task_complete.get(task_id)
        if handler is None:
            raise MockScriptError(f"no completion handler for task {task_id!r}")
        handler(port)
