"""Deterministic simulated-call driver for the developer demo and end-to-end tests.

It drives the SDK-free voice mock port (`MockCallPort`) through the
orchestrator's provider-neutral handlers one step at a time, so a scenario can
act mid-call (a relayed correction, a clock advance). Caller turns are scripted:
each `Say` step carries the structured field values the voice layer would
have extracted, plus an optional display-only line. The driver never
interprets that line, and neither does the orchestrator.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from clinical_triage.adapters.voice_mock import MockCallPort
from clinical_triage.domain.facts import ClinicalFact
from clinical_triage.domain.voice import FieldSpec, FieldValue, SaySpec, SessionEnded, TaskSpec
from clinical_triage.fixtures import FixedClock
from clinical_triage.orchestration import CallOrchestrator


class ScenarioError(ValueError):
    """The script disagrees with what the call is doing (a scenario bug)."""


@dataclass(frozen=True)
class Say:
    """The caller answers the active task."""

    task_id: str
    values: Mapping[str, FieldValue]
    line: str = ""


@dataclass(frozen=True)
class AskQuestion:
    """The caller asks something; the text is passed to the handler and never stored."""

    text: str


@dataclass(frozen=True)
class RelayCorrection:
    """An operator or agent tool relays a corrected answer via `submit_correction`."""

    fact: ClinicalFact
    line: str = ""


@dataclass(frozen=True)
class AdvanceClock:
    seconds: int


@dataclass(frozen=True)
class Hangup:
    """The caller hangs up."""


Step = Say | AskQuestion | RelayCorrection | AdvanceClock | Hangup


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str


@dataclass
class DriveResult:
    port: MockCallPort
    transcript: list[Turn] = field(default_factory=list)


def task_prompt(task: TaskSpec) -> str:
    parts = [item.text for item in task.checklist if isinstance(item, SaySpec)]
    parts += [item.question for item in task.checklist if isinstance(item, FieldSpec)]
    return " ".join(p for p in parts if p) or task.objective


class ScenarioDriver:
    def __init__(
        self,
        orchestrator: CallOrchestrator,
        clock: FixedClock,
        transfer_outcomes: Mapping[str, str | None],
    ) -> None:
        self._orchestrator = orchestrator
        self._clock = clock
        self._transfer_outcomes = transfer_outcomes

    def run(self, call_id: str, steps: tuple[Step, ...]) -> DriveResult:
        handlers = self._orchestrator.handlers()
        port = MockCallPort(call_id=call_id, transfer_outcomes=self._transfer_outcomes)
        result = DriveResult(port=port)
        seen = _Seen()
        handlers.on_call_start(port)
        seen.collect(port, result.transcript)
        for index, step in enumerate(steps):
            if port.ended is not None:
                raise ScenarioError(f"step {index} ({type(step).__name__}) after the call ended")
            if isinstance(step, Say):
                task = port.active_task
                if task is None or task.task_id != step.task_id:
                    active = task.task_id if task else None
                    raise ScenarioError(
                        f"step {index}: {step.task_id!r} is not active ({active!r})"
                    )
                keys = {i.key for i in task.checklist if isinstance(i, FieldSpec)}
                if set(step.values) != keys:
                    raise ScenarioError(f"step {index}: answer keys must be exactly {sorted(keys)}")
                result.transcript.append(Turn("Caller", step.line or _values_line(step.values)))
                port.values.update(step.values)
                handlers.on_task_complete[step.task_id](port)
            elif isinstance(step, AskQuestion):
                result.transcript.append(Turn("Caller", "(asks an off-script question)"))
                if handlers.on_question is not None:
                    port.answers.append(handlers.on_question(port, step.text))
            elif isinstance(step, RelayCorrection):
                result.transcript.append(Turn("Caller", step.line or "(corrects an answer)"))
                result.transcript.append(
                    Turn("Tool", f"submit_correction({step.fact.fact_id} = {step.fact.value!r})")
                )
                self._orchestrator.submit_correction(call_id, step.fact)
            elif isinstance(step, AdvanceClock):
                self._clock.advance(seconds=step.seconds)
                result.transcript.append(Turn("Clock", f"+{step.seconds}s"))
            else:
                port.ended = SessionEnded(reason="user-hangup")
                result.transcript.append(Turn("Caller", "(hangs up)"))
            seen.collect(port, result.transcript)
        if port.ended is None:
            raise ScenarioError("the script ended while the call was still active")
        if handlers.on_session_end is not None:
            handlers.on_session_end(port, port.ended)
        return result


@dataclass
class _Seen:
    tasks: int = 0
    answers: int = 0
    transfers: int = 0
    hangups: int = 0

    def collect(self, port: MockCallPort, transcript: list[Turn]) -> None:
        for answer in port.answers[self.answers :]:
            transcript.append(Turn("Agent", answer))
        for task in port.tasks[self.tasks :]:
            transcript.append(Turn("Agent", task_prompt(task)))
        for target in port.transfers[self.transfers :]:
            transcript.append(Turn("System", f"transfer requested -> {target.display_name}"))
        for text in port.hangups[self.hangups :]:
            transcript.append(Turn("Agent", text))
            transcript.append(Turn("System", "agent ended the call"))
        self.tasks, self.answers = len(port.tasks), len(port.answers)
        self.transfers, self.hangups = len(port.transfers), len(port.hangups)


def _values_line(values: Mapping[str, FieldValue]) -> str:
    return ", ".join(f"{k}={v}" for k, v in values.items())
