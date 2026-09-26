"""Narrow voice-provider contract grounded in the Guava inbound lifecycle."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NoReturn, Protocol, TypeAlias

FieldValue: TypeAlias = str | int | float | bool | None
FieldType: TypeAlias = Literal[
    "text",
    "date",
    "datetime",
    "integer",
    "multiple_choice",
    "calendar_slot",
    "digit_sequence",
]


@dataclass(frozen=True)
class AgentSpec:
    name: str | None
    organization: str | None
    purpose: str


@dataclass(frozen=True)
class FieldSpec:
    key: str
    field_type: FieldType = "text"
    description: str = ""
    question: str = ""
    required: bool = True
    choices: tuple[str, ...] = ()
    searchable: bool = False
    sensitive: bool = False


@dataclass(frozen=True)
class SaySpec:
    text: str


ChecklistItem: TypeAlias = FieldSpec | SaySpec | str


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    objective: str
    checklist: tuple[ChecklistItem, ...] = ()
    completion_criteria: str = ""


@dataclass(frozen=True)
class SessionEnded:
    reason: Literal["user-hangup", "bot-hangup", "bot-failure", "bot-transfer"]


@dataclass(frozen=True)
class TransferTarget:
    target_id: str
    display_name: str


@dataclass(frozen=True)
class TransferResult:
    transfer_id: str
    accepted: bool
    failure_code: str | None = None

    def __post_init__(self) -> None:
        has_failure = self.failure_code is not None and bool(self.failure_code.strip())
        if self.accepted == has_failure:
            raise ValueError("accepted transfer and failure_code must be opposites")


@dataclass(frozen=True)
class EscalationRequest:
    call_id: str
    script_id: str
    trigger_rule_ids: tuple[str, ...]
    target: TransferTarget


class CallPort(Protocol):
    @property
    def id(self) -> str: ...

    def set_task(self, task: TaskSpec) -> None: ...

    def get_field(self, key: str) -> FieldValue: ...

    def transfer(self, target: TransferTarget) -> TransferResult: ...

    def hangup(self, final_instructions: str = "") -> None: ...


@dataclass(frozen=True)
class InboundHandlers:
    on_call_start: Callable[[CallPort], None]
    on_question: Callable[[CallPort, str], str] | None
    on_task_complete: Mapping[str, Callable[[CallPort], None]]
    on_escalate: Callable[[CallPort, EscalationRequest], TransferResult]
    on_session_end: Callable[[CallPort, SessionEnded], None] | None


class InboundVoiceAdapter(Protocol):
    def bind(self, spec: AgentSpec, handlers: InboundHandlers) -> None: ...

    def listen_phone(self, phone_number: str) -> NoReturn: ...
