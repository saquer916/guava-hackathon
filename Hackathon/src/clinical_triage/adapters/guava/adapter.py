"""Narrow Guava implementation of the provider-neutral inbound voice port.

Live behavior is off by default. Binding a phone number requires
`live_calls_approved=True`; transferring a call requires
`live_transfer_approved=True` and a destination resolved from an
operator-supplied directory by target ID. Callers never supply numbers.

Guava's documented `call.transfer(destination, instructions)` returns nothing,
so an accepted TransferResult means "transfer submitted"; completion is only
observable later as a session end with reason `bot-transfer`.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol

import guava

from clinical_triage.adapters.guava.translation import to_guava_checklist, to_session_ended
from clinical_triage.domain.voice import (
    AgentSpec,
    FieldValue,
    InboundHandlers,
    TaskSpec,
    TransferResult,
    TransferTarget,
)

_DESTINATION = re.compile(r"^(\+[1-9]\d{7,14}|sip:[^\s@]+@[^\s@]+)$")


class LiveVoiceNotApproved(RuntimeError):
    """A live Guava operation was requested without explicit approval."""


class GuavaAgentLike(Protocol):
    """The documented decorator surface of `guava.Agent` that this adapter uses."""

    def on_call_start(self, fn: Callable[[Any], None], /) -> Callable[[Any], None]: ...

    def on_question(self, fn: Callable[[Any, str], str], /) -> Callable[[Any, str], str]: ...

    def on_task_complete(
        self, task_name: str, /
    ) -> Callable[[Callable[[Any], None]], Callable[[Any], None]]: ...

    def on_session_end(self, fn: Callable[[Any, Any], None], /) -> Callable[[Any, Any], None]: ...

    def listen_phone(self, agent_number: str) -> None: ...


AgentFactory = Callable[[AgentSpec], GuavaAgentLike]


def live_agent_factory(spec: AgentSpec) -> GuavaAgentLike:
    """Constructs a real guava.Agent; this authenticates and contacts Guava."""

    agent: GuavaAgentLike = guava.Agent(
        name=spec.name, organization=spec.organization, purpose=spec.purpose
    )
    return agent


@dataclass(frozen=True)
class TransferDirectory:
    """Maps approved target IDs to destinations loaded from ignored local config."""

    destinations: Mapping[str, str]

    def __post_init__(self) -> None:
        for target_id, destination in self.destinations.items():
            if not target_id or not _DESTINATION.fullmatch(destination):
                raise ValueError("transfer destinations must be E.164 numbers or SIP URIs")

    def resolve(self, target_id: str) -> str | None:
        return self.destinations.get(target_id)

    def __repr__(self) -> str:
        return f"TransferDirectory(targets={sorted(self.destinations)})"


class GuavaCallPort:
    def __init__(
        self, call: guava.Call, *, directory: TransferDirectory, live_transfer_approved: bool
    ) -> None:
        self._call = call
        self._directory = directory
        self._live_transfer_approved = live_transfer_approved

    @property
    def id(self) -> str:
        return str(self._call.id)

    def set_task(self, task: TaskSpec) -> None:
        self._call.set_task(
            task.task_id,
            objective=task.objective,
            checklist=to_guava_checklist(task),
            completion_criteria=task.completion_criteria,
        )

    def get_field(self, key: str) -> FieldValue:
        value = self._call.get_field(key)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def transfer(self, target: TransferTarget) -> TransferResult:
        transfer_id = f"{self.id}:{target.target_id}"
        if not self._live_transfer_approved:
            return TransferResult(
                transfer_id, accepted=False, failure_code="LIVE_TRANSFER_NOT_APPROVED"
            )
        destination = self._directory.resolve(target.target_id)
        if destination is None:
            return TransferResult(
                transfer_id, accepted=False, failure_code="TRANSFER_TARGET_NOT_CONFIGURED"
            )
        self._call.transfer(destination)
        return TransferResult(transfer_id, accepted=True)

    def hangup(self, final_instructions: str = "") -> None:
        self._call.hangup(final_instructions)


class GuavaInboundAdapter:
    def __init__(
        self,
        *,
        directory: TransferDirectory,
        agent_factory: AgentFactory = live_agent_factory,
        live_calls_approved: bool = False,
        live_transfer_approved: bool = False,
    ) -> None:
        self._directory = directory
        self._agent_factory = agent_factory
        self._live_calls_approved = live_calls_approved
        self._live_transfer_approved = live_transfer_approved
        self._agent: GuavaAgentLike | None = None
        self._ports: dict[str, GuavaCallPort] = {}

    def port_for(self, call: guava.Call) -> GuavaCallPort:
        key = str(call.id)
        if key not in self._ports:
            self._ports[key] = GuavaCallPort(
                call, directory=self._directory, live_transfer_approved=self._live_transfer_approved
            )
        return self._ports[key]

    def bind(self, spec: AgentSpec, handlers: InboundHandlers) -> None:
        agent = self._agent_factory(spec)
        agent.on_call_start(lambda call: handlers.on_call_start(self.port_for(call)))
        on_question = handlers.on_question
        if on_question is not None:
            agent.on_question(lambda call, question: on_question(self.port_for(call), question))
        for task_id, handler in handlers.on_task_complete.items():
            agent.on_task_complete(task_id)(self._task_handler(handler))
        on_session_end = handlers.on_session_end
        if on_session_end is not None:

            def session_end(call: guava.Call, event: Any) -> None:
                on_session_end(self.port_for(call), to_session_ended(event.termination_reason))
                self._ports.pop(str(call.id), None)

            agent.on_session_end(session_end)
        self._agent = agent

    def _task_handler(self, handler: Callable[[GuavaCallPort], None]) -> Callable[[Any], None]:
        return lambda call: handler(self.port_for(call))

    def listen_phone(self, phone_number: str) -> NoReturn:
        if not self._live_calls_approved:
            raise LiveVoiceNotApproved("binding a Guava phone number requires explicit approval")
        if self._agent is None:
            raise RuntimeError("bind() must be called before listen_phone()")
        self._agent.listen_phone(phone_number)
        raise RuntimeError("Guava listen_phone returned unexpectedly")
