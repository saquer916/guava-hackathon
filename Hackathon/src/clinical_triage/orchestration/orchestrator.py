"""Provider-neutral call orchestration.

Connects the inbound voice port, the pure conversation reducer, the safety
policy, scheduling policy, EHR port, and audit sink. The reducer decides; this
module only translates voice callbacks into versioned domain events and
executes the reducer's commands. Boundaries enforced here:

- Once a session is EMERGENCY the orchestrator makes no further EHR or
  scheduling call of any kind, including end-of-call record writes.
- Booking requires an explicit caller YES to one ranked offer, asked in a task
  of its own, *and* `allow_booking_writes`; EMERGENCY and HUMAN_REVIEW
  sessions cannot reach it. Overbooking is only ever suggested to staff.
- An accepted transfer is recorded as ATTEMPTED; it is COMPLETED only when the
  voice session ends with `bot-transfer`.
- Caller question text is never stored. Fact values go only to the protected
  DecisionRecord; AuditRecord and OperationalEvent carry IDs and codes.
- No exception escapes a voice callback (provider SDK telemetry may upload
  exception text). Failures are recorded by class name and fail toward human
  review, or toward the emergency script once a session is EMERGENCY.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol, TypedDict, TypeVar

from clinical_triage.adapters.errors import AdapterOperationUnavailable
from clinical_triage.conversation import (
    PolicyEvaluator,
    PolicyOutcome,
    QuestionKind,
    Transition,
    begin_booking_commit,
    booking_completed,
    offer_slot,
    reduce,
    scheduling_failed,
)
from clinical_triage.domain.audit import (
    AuditedOperation,
    AuditRecord,
    DecisionRecord,
    OperationalEvent,
    OperationOutcome,
    RuleEvaluationTrace,
)
from clinical_triage.domain.conversation import (
    AnswerCorrected,
    AnswerRecorded,
    AppointmentConfirmed,
    AskQuestion,
    CallStarted,
    CloseCall,
    ConsentRecorded,
    DomainCommand,
    DomainEvent,
    Escalate,
    HumanReviewRequested,
    RequestHumanReview,
    SearchAppointments,
    SessionEndedEvent,
    SessionState,
    TaskCompleted,
)
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.ehr import CallSummary, PatientQuery
from clinical_triage.domain.facts import ClinicalFact, ClinicalState, FactSource
from clinical_triage.domain.policy import PolicyBundle
from clinical_triage.domain.ports import AuditSink, EHRAdapter
from clinical_triage.domain.scheduling import AppointmentOffer
from clinical_triage.domain.triage import TriageResult
from clinical_triage.domain.voice import (
    CallPort,
    EscalationRequest,
    FieldSpec,
    InboundHandlers,
    SaySpec,
    SessionEnded,
    TaskSpec,
    TransferResult,
)
from clinical_triage.orchestration.config import (
    IDENTITY_FIELD_KEYS,
    IDENTITY_TASK,
    OFFER_TASKS,
    OrchestratorConfig,
    offer_field_key,
    parse_birth_date,
)
from clinical_triage.scheduling import (
    SchedulingPolicy,
    SchedulingPolicyError,
    build_confirmation,
    rank_appointment_options,
)
from clinical_triage.triage import build_triage_result

T = TypeVar("T")


class Clock(Protocol):
    def now(self) -> datetime: ...


class PolicyEngine(PolicyEvaluator, Protocol):
    bundle: PolicyBundle

    def trace(self, clinical: ClinicalState) -> tuple[RuleEvaluationTrace, ...]: ...


class _EventIds(TypedDict):
    event_id: str
    call_id: str
    expected_state_version: int


class _EHRFailed(Exception):
    """Internal signal: an EHR call failed and was already audited."""


@dataclass
class CallContext:
    port: CallPort
    state: SessionState
    started_at: datetime
    outcome: PolicyOutcome | None = None
    patient_id: str | None = None
    identity_attempted: bool = False
    pending_search: SearchAppointments | None = None
    offer: AppointmentOffer | None = None
    offer_task_id: str | None = None
    offers_made: int = 0
    booking_failures: int = 0
    appointment_id: str | None = None
    event_count: int = 0
    fact_event_ids: dict[str, str] = field(default_factory=dict)
    considered_offer_ids: list[str] = field(default_factory=list)
    operations: list[AuditedOperation] = field(default_factory=list)
    human_decisions: list[str] = field(default_factory=list)
    error_codes: list[str] = field(default_factory=list)
    transfer_pending: bool = False
    triage: TriageResult | None = None
    finalized: bool = False

    @property
    def emergency(self) -> bool:
        return self.state.disposition is Disposition.EMERGENCY


class CallOrchestrator:
    def __init__(
        self,
        *,
        config: OrchestratorConfig,
        policy: PolicyEngine,
        scheduling_policy: SchedulingPolicy,
        ehr: EHRAdapter,
        audit: AuditSink,
        clock: Clock,
    ) -> None:
        self._config = config
        self._policy = policy
        self._scheduling = scheduling_policy
        self._ehr = ehr
        self._audit = audit
        self._clock = clock
        self.calls: dict[str, CallContext] = {}

    # --- voice port wiring -----------------------------------------------------

    def handlers(self) -> InboundHandlers:
        task_ids = [
            self._config.conversation.consent_question_id,
            IDENTITY_TASK,
            *OFFER_TASKS,
            *(q.question_id for q in self._config.questions),
        ]
        return InboundHandlers(
            on_call_start=self.on_call_start,
            on_question=self.on_question,
            on_task_complete={task_id: self._completion(task_id) for task_id in task_ids},
            on_escalate=self.on_escalate,
            on_session_end=self.on_session_end,
        )

    def on_call_start(self, port: CallPort) -> None:
        if port.id in self.calls:
            return
        state = SessionState(call_id=port.id)
        ctx = CallContext(port=port, state=state, started_at=self._clock.now())
        self.calls[port.id] = ctx
        self._emit(ctx, "CALL.STARTED", OperationOutcome.COMPLETED)
        self._guarded(ctx, lambda: self._apply_event(ctx, CallStarted(**self._event_ids(ctx))))

    def on_question(self, port: CallPort, question: str) -> str:
        # The caller's words are deliberately neither stored nor interpreted.
        ctx = self.calls.get(port.id)
        if ctx is not None:
            self._emit(ctx, "CALL.QUESTION_DEFLECTED", OperationOutcome.COMPLETED)
        return self._config.question_deflection

    def on_escalate(self, port: CallPort, request: EscalationRequest) -> TransferResult:
        return port.transfer(request.target)

    def on_session_end(self, port: CallPort, ended: SessionEnded) -> None:
        ctx = self.calls.get(port.id)
        if ctx is None or ctx.finalized:
            return
        if ctx.transfer_pending:
            completed = ended.reason == "bot-transfer"
            self._operation(
                ctx,
                "VOICE.TRANSFER_COMPLETED",
                "voice",
                OperationOutcome.COMPLETED if completed else OperationOutcome.FAILED,
                None if completed else "TRANSFER_NOT_OBSERVED",
            )
        if not ctx.state.terminal:
            reason = ended.reason.upper().replace("-", "_")
            self._guarded(
                ctx,
                lambda: self._apply_event(
                    ctx, SessionEndedEvent(**self._event_ids(ctx), reason_code=reason)
                ),
                fail_safe=False,
            )
        self._finalize(ctx)

    def submit_correction(self, call_id: str, fact: ClinicalFact) -> Transition | None:
        """Apply a caller correction relayed by an operator or a correction tool.

        Returns None when the call is unknown or has already been finalized.
        """

        ctx = self.calls.get(call_id)
        if ctx is None or ctx.finalized:
            return None
        replaces = ctx.fact_event_ids.get(fact.fact_id, "NO_PRIOR_EVENT")
        event = AnswerCorrected(**self._event_ids(ctx), fact=fact, replaces_event_id=replaces)
        result: list[Transition] = []
        self._guarded(ctx, lambda: result.append(self._apply_event(ctx, event)))
        return result[0] if result else None

    # --- task completions --------------------------------------------------------

    def _completion(self, task_id: str) -> Callable[[CallPort], None]:
        def handle(port: CallPort) -> None:
            ctx = self.calls.get(port.id)
            if ctx is None or ctx.finalized:
                return
            if task_id == self._config.conversation.consent_question_id:
                self._guarded(ctx, lambda: self._consent_completed(ctx))
            elif task_id == IDENTITY_TASK:
                self._guarded(ctx, lambda: self._identity_completed(ctx))
            elif task_id in OFFER_TASKS:
                self._guarded(ctx, lambda: self._offer_completed(ctx, task_id))
            else:
                self._guarded(ctx, lambda: self._question_completed(ctx, task_id))

        return handle

    def _consent_completed(self, ctx: CallContext) -> None:
        answer = ctx.port.get_field(self._config.consent_field.key)
        code = "CONSENT_GIVEN" if str(answer).strip().upper() == "YES" else "CONSENT_DECLINED"
        ctx.human_decisions.append(code)
        self._apply_event(ctx, ConsentRecorded(**self._event_ids(ctx), consent_code=code))

    def _question_completed(self, ctx: CallContext, question_id: str) -> None:
        question = self._config.question(question_id)
        spec = next(
            (q for q in self._config.conversation.questions if q.question_id == question_id), None
        )
        if question is None or spec is None:
            ctx.error_codes.append(f"UNKNOWN_QUESTION:{question_id}")
            return
        value = question.parse_value(ctx.port.get_field(question.field.key))
        existing = ctx.state.clinical.fact(question.fact_id)
        if value is None:
            ctx.error_codes.append(f"UNPARSEABLE_ANSWER:{question_id}")
        else:
            fact = ClinicalFact(
                fact_id=question.fact_id,
                value=value,
                source=FactSource.CALLER,
                confirmed=question.is_plausible(value),
                unit_code=question.unit_code,
            )
            ids = self._event_ids(ctx)
            event: DomainEvent
            if existing is None:
                event = AnswerRecorded(**ids, fact=fact)
            elif spec.kind is QuestionKind.CLARIFICATION:
                replaces = ctx.fact_event_ids.get(fact.fact_id, "NO_PRIOR_EVENT")
                event = AnswerCorrected(**ids, fact=fact, replaces_event_id=replaces)
            else:
                ctx.error_codes.append(f"FACT_ALREADY_RECORDED:{question_id}")
                event = TaskCompleted(**ids, task_id=question_id)
            if self._apply_event(ctx, event).accepted and not isinstance(event, TaskCompleted):
                ctx.fact_event_ids[fact.fact_id] = ids["event_id"]
        if not ctx.state.terminal:
            self._apply_event(ctx, TaskCompleted(**self._event_ids(ctx), task_id=question_id))

    def _identity_completed(self, ctx: CallContext) -> None:
        given, family, raw_birth_date = (ctx.port.get_field(k) for k in IDENTITY_FIELD_KEYS)
        patient_id = self._verify_identity(ctx, given, family, parse_birth_date(raw_birth_date))
        if patient_id is None:
            self._apply_event(
                ctx, HumanReviewRequested(**self._event_ids(ctx), reason_code="IDENTITY_UNVERIFIED")
            )
            return
        ctx.patient_id = patient_id
        pending, ctx.pending_search = ctx.pending_search, None
        if pending is not None:
            self._search(ctx, pending)

    def _offer_completed(self, ctx: CallContext, task_id: str) -> None:
        if task_id != ctx.offer_task_id or ctx.offer is None:
            ctx.error_codes.append(f"STALE_OFFER_TASK:{task_id}")
            return
        offer = ctx.offer
        ctx.offer_task_id = None
        answer = str(ctx.port.get_field(offer_field_key(task_id))).strip().upper()
        if answer != "YES":
            ctx.human_decisions.append("CALLER_DECLINED_OFFER")
            self._scheduling_failed(ctx, "CALLER_DECLINED_OFFER", retry=False)
            return
        ctx.human_decisions.append("CALLER_CONFIRMED_OFFER")
        ids = self._event_ids(ctx)
        confirm = AppointmentConfirmed(**ids, confirmation_id=f"{ids['event_id']}-confirm")
        if not self._apply_event(ctx, confirm).accepted:
            return
        commit = begin_booking_commit(ctx.state, expected_version=ctx.state.version)
        self._dispatch(ctx, commit)
        if not commit.accepted:
            return
        if not self._config.allow_booking_writes:
            self._operation(
                ctx, "EHR.CREATE_APPOINTMENT", "ehr", OperationOutcome.SKIPPED, "WRITES_DISABLED"
            )
            self._scheduling_failed(ctx, "BOOKING_REQUIRES_STAFF_APPROVAL", retry=False)
            return
        self._book(ctx, offer, confirm.event_id)

    # --- command execution -------------------------------------------------------

    def _execute(self, ctx: CallContext, command: DomainCommand) -> None:
        if isinstance(command, AskQuestion):
            self._ask(ctx, command.question_id)
        elif isinstance(command, Escalate):
            self._escalate(ctx, command)
        elif isinstance(command, SearchAppointments):
            self._search(ctx, command)
        elif isinstance(command, RequestHumanReview):
            self._handoff(ctx, command.reason_code)
        elif isinstance(command, CloseCall):
            ctx.port.hangup(self._config.scripts[command.script_id])

    def _ask(self, ctx: CallContext, question_id: str) -> None:
        if question_id == self._config.conversation.consent_question_id:
            ctx.port.set_task(
                TaskSpec(
                    task_id=question_id,
                    objective="Explain the call boundary and ask for consent to continue.",
                    checklist=(
                        SaySpec(self._config.consent_boundary_script),
                        self._config.consent_field,
                    ),
                )
            )
            return
        question = self._config.question(question_id)
        if question is None:
            self._apply_event(
                ctx, HumanReviewRequested(**self._event_ids(ctx), reason_code="NO_VOICE_QUESTION")
            )
            return
        ctx.port.set_task(
            TaskSpec(
                task_id=question_id,
                objective="Collect one structured answer. Do not give medical advice.",
                checklist=(question.field,),
            )
        )

    def _escalate(self, ctx: CallContext, command: Escalate) -> None:
        ctx.offer, ctx.offer_task_id, ctx.pending_search = None, None, None
        ctx.human_decisions.append("EMERGENCY_ESCALATION")
        for rule_id in command.trigger_rule_ids:
            self._emit(ctx, f"SAFETY.EMERGENCY_RULE:{rule_id}", OperationOutcome.COMPLETED)
        request = EscalationRequest(
            call_id=ctx.state.call_id,
            script_id=command.script_id,
            trigger_rule_ids=command.trigger_rule_ids,
            target=self._config.emergency_target,
        )
        self._transfer_or_hangup(ctx, request, self._emergency_script(command.script_id))

    def _handoff(self, ctx: CallContext, reason_code: str) -> None:
        ctx.offer, ctx.offer_task_id = None, None
        ctx.human_decisions.append(f"HUMAN_REVIEW:{reason_code}")
        request = EscalationRequest(
            call_id=ctx.state.call_id,
            script_id="HUMAN_REVIEW_HANDOFF",
            trigger_rule_ids=(reason_code,),
            target=self._config.human_review_target,
        )
        self._transfer_or_hangup(ctx, request, self._config.human_review_callback_script)

    def _transfer_or_hangup(
        self, ctx: CallContext, request: EscalationRequest, script: str
    ) -> None:
        result = self.on_escalate(ctx.port, request)
        if result.accepted:
            ctx.transfer_pending = True
            self._operation(ctx, "VOICE.TRANSFER", "voice", OperationOutcome.ATTEMPTED)
            return
        self._operation(
            ctx, "VOICE.TRANSFER", "voice", OperationOutcome.FAILED, result.failure_code
        )
        ctx.port.hangup(script)

    def _search(self, ctx: CallContext, command: SearchAppointments) -> None:
        if ctx.patient_id is None:
            if ctx.identity_attempted:
                self._scheduling_failed(ctx, "IDENTITY_UNVERIFIED", retry=False)
                return
            ctx.identity_attempted = True
            ctx.pending_search = command
            ctx.port.set_task(
                TaskSpec(
                    task_id=IDENTITY_TASK,
                    objective="Collect identity details to find the synthetic patient record.",
                    checklist=self._config.identity_fields,
                )
            )
            return
        disposition = ctx.state.disposition
        if disposition is None:
            self._scheduling_failed(ctx, "NO_DISPOSITION", retry=False)
            return
        window = self._config.windows[command.scheduling_window]
        now = self._clock.now()
        try:
            snapshot = self._ehr_call(
                ctx,
                "EHR.GET_AVAILABLE_APPOINTMENTS",
                lambda: self._ehr.get_available_appointments(
                    earliest=now + timedelta(minutes=window.earliest_offset_minutes),
                    latest=now + timedelta(minutes=window.latest_offset_minutes),
                    constraint_codes=command.constraint_codes,
                ),
            )
        except _EHRFailed:
            self._scheduling_failed(ctx, "AVAILABILITY_UNAVAILABLE", retry=False)
            return
        try:
            options = rank_appointment_options(
                snapshot=snapshot, disposition=disposition, policy=self._scheduling, now=now
            )
        except SchedulingPolicyError as exc:
            self._scheduling_failed(ctx, exc.reason_code, retry=False)
            return
        offers = options.normal_availability + options.alternative_availability
        ctx.considered_offer_ids.extend(o.offer_id for o in offers)
        if options.possible_escalation is not None:
            # Staff decide on overbooking; the system only surfaces the request.
            ctx.human_decisions.append(
                f"OVERBOOK_REVIEW_SUGGESTED:{options.possible_escalation.reason_code}"
            )
        if not offers:
            reason = (
                "OVERBOOK_REVIEW_REQUESTED" if options.possible_escalation else "NO_AVAILABILITY"
            )
            self._scheduling_failed(ctx, reason, retry=False)
            return
        if ctx.offers_made >= len(OFFER_TASKS):
            self._scheduling_failed(ctx, "OFFER_ATTEMPTS_EXHAUSTED", retry=False)
            return
        offer = offers[0]
        transition = offer_slot(
            ctx.state, slot_id=offer.slot.slot_id, expected_version=ctx.state.version
        )
        self._dispatch(ctx, transition)
        if not transition.accepted:
            return
        task_id = OFFER_TASKS[ctx.offers_made]
        ctx.offers_made += 1
        ctx.offer, ctx.offer_task_id = offer, task_id
        ctx.port.set_task(
            TaskSpec(
                task_id=task_id,
                objective=self._config.offer_prompt_template.format(
                    starts_at=offer.slot.starts_at.isoformat(), kind=offer.slot.kind.value
                ),
                checklist=(
                    FieldSpec(
                        key=offer_field_key(task_id),
                        field_type="multiple_choice",
                        choices=("YES", "NO"),
                    ),
                ),
            )
        )

    def _book(self, ctx: CallContext, offer: AppointmentOffer, confirmation_event_id: str) -> None:
        patient_id = ctx.patient_id
        if patient_id is None:
            self._scheduling_failed(ctx, "IDENTITY_UNVERIFIED", retry=False)
            return
        try:
            confirmation = build_confirmation(
                offer=offer,
                confirmation_id=f"{ctx.state.call_id}-{offer.offer_id}",
                confirmation_event_id=confirmation_event_id,
                confirmed_at=self._clock.now(),
            )
        except ValueError:
            self._booking_failed(ctx, "OFFER_EXPIRED")
            return
        try:
            result = self._ehr_call(
                ctx,
                "EHR.CREATE_APPOINTMENT",
                lambda: self._ehr.create_appointment(
                    patient_id=patient_id,
                    confirmation=confirmation,
                    idempotency_key=f"{ctx.state.call_id}:{offer.offer_id}",
                ),
                audit_success=False,
            )
        except _EHRFailed:
            self._booking_failed(ctx, "BOOKING_UNAVAILABLE")
            return
        if not result.completed:
            code = result.failure_code or "BOOKING_FAILED"
            self._operation(ctx, "EHR.CREATE_APPOINTMENT", "ehr", OperationOutcome.FAILED, code)
            self._booking_failed(ctx, code)
            return
        self._operation(ctx, "EHR.CREATE_APPOINTMENT", "ehr", OperationOutcome.COMPLETED)
        ctx.appointment_id = result.appointment_id
        ctx.offer = None
        self._dispatch(
            ctx,
            booking_completed(
                ctx.state, expected_version=ctx.state.version, config=self._config.conversation
            ),
        )

    def _booking_failed(self, ctx: CallContext, reason: str) -> None:
        # Some failures (an expired offer) never reach the EHR; keep every attempt auditable.
        ctx.error_codes.append(f"BOOKING_ATTEMPT_FAILED:{reason}")
        ctx.booking_failures += 1
        retry = ctx.booking_failures == 1 and reason in self._config.retryable_booking_failures
        self._scheduling_failed(ctx, reason, retry=retry)

    def _scheduling_failed(self, ctx: CallContext, reason: str, *, retry: bool) -> None:
        ctx.offer, ctx.offer_task_id = None, None
        self._dispatch(
            ctx,
            scheduling_failed(
                ctx.state,
                expected_version=ctx.state.version,
                reason_code=reason,
                retry=retry,
                config=self._config.conversation,
            ),
        )

    def _verify_identity(
        self, ctx: CallContext, given: object, family: object, birth_date: date | None
    ) -> str | None:
        # Name alone never identifies a caller: synthetic patients A and G share one.
        if not (isinstance(given, str) and given.strip() and isinstance(family, str)):
            ctx.error_codes.append("IDENTITY_INCOMPLETE")
            return None
        if birth_date is None:
            ctx.error_codes.append("IDENTITY_INCOMPLETE")
            return None
        query = PatientQuery(
            given_name=given.strip(), family_name=family.strip(), birth_date=birth_date
        )
        try:
            candidates = self._ehr_call(
                ctx, "EHR.FIND_PATIENT", lambda: self._ehr.find_patient(query)
            )
            if len(candidates) != 1 or candidates[0].ambiguous:
                ctx.error_codes.append("IDENTITY_NOT_UNIQUE" if candidates else "IDENTITY_NO_MATCH")
                return None
            candidate = candidates[0]
            verification = self._ehr_call(
                ctx,
                "EHR.VERIFY_PATIENT",
                lambda: self._ehr.verify_patient(
                    candidate.patient_id, candidate.match_factor_codes
                ),
            )
        except _EHRFailed:
            return None
        if not verification.verified:
            ctx.error_codes.append("IDENTITY_NOT_VERIFIED")
            return None
        return verification.patient_id

    def _ehr_call(
        self, ctx: CallContext, code: str, call: Callable[[], T], *, audit_success: bool = True
    ) -> T:
        if ctx.emergency:
            self._operation(ctx, code, "ehr", OperationOutcome.SKIPPED, "EMERGENCY_NO_EHR_CALLS")
            raise _EHRFailed
        try:
            value = call()
        except AdapterOperationUnavailable as exc:
            self._operation(ctx, code, "ehr", OperationOutcome.FAILED, exc.reason_code)
            raise _EHRFailed from None
        except Exception as exc:  # noqa: BLE001 - any adapter failure must fail closed
            self._operation(ctx, code, "ehr", OperationOutcome.FAILED, type(exc).__name__)
            raise _EHRFailed from None
        if audit_success:
            self._operation(ctx, code, "ehr", OperationOutcome.COMPLETED)
        return value

    # --- reducer plumbing ------------------------------------------------------------

    def _event_ids(self, ctx: CallContext) -> _EventIds:
        ctx.event_count += 1
        return {
            "event_id": f"{ctx.state.call_id}-e{ctx.event_count}",
            "call_id": ctx.state.call_id,
            "expected_state_version": ctx.state.version,
        }

    def _apply_event(self, ctx: CallContext, event: DomainEvent) -> Transition:
        transition = reduce(
            ctx.state, event, config=self._config.conversation, evaluate=self._policy
        )
        self._dispatch(ctx, transition)
        return transition

    def _dispatch(self, ctx: CallContext, transition: Transition) -> None:
        if not transition.accepted:
            ctx.error_codes.append(f"REJECTED:{transition.rejected_reason}")
            return
        ctx.state = transition.state
        if transition.outcome is not None:
            ctx.outcome = transition.outcome
        for command in transition.commands:
            self._execute(ctx, command)

    def _guarded(
        self, ctx: CallContext, action: Callable[[], object], *, fail_safe: bool = True
    ) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - nothing may escape into the voice SDK
            ctx.error_codes.append(f"UNHANDLED:{type(exc).__name__}")
            if fail_safe:
                self._fail_safe(ctx)

    def _fail_safe(self, ctx: CallContext) -> None:
        try:
            if ctx.emergency:
                ctx.port.hangup(self._emergency_script(None))
            elif not ctx.state.terminal:
                self._apply_event(
                    ctx,
                    HumanReviewRequested(**self._event_ids(ctx), reason_code="ORCHESTRATOR_ERROR"),
                )
        except Exception as exc:  # noqa: BLE001 - last resort; already failing
            ctx.error_codes.append(f"FAIL_SAFE_ERROR:{type(exc).__name__}")

    def _emergency_script(self, script_id: str | None) -> str:
        fallback = self._config.scripts[self._config.conversation.fallback_emergency_script_id]
        return self._config.scripts.get(script_id or "", fallback)

    # --- audit -------------------------------------------------------------------------

    def _operation(
        self,
        ctx: CallContext,
        operation_type: str,
        target: str,
        outcome: OperationOutcome,
        error_code: str | None = None,
    ) -> None:
        ctx.operations.append(
            AuditedOperation(
                operation_id=f"{ctx.state.call_id}-op{len(ctx.operations) + 1}",
                operation_type=operation_type,
                target_system=target,
                outcome=outcome,
                error_code=error_code,
            )
        )
        self._emit(ctx, operation_type, outcome, error_code)

    def _emit(
        self, ctx: CallContext, code: str, outcome: OperationOutcome, error_code: str | None = None
    ) -> None:
        self._audit.emit_operational_event(
            OperationalEvent(
                event_code=code,
                call_id=ctx.state.call_id,
                occurred_at=self._clock.now(),
                outcome=outcome,
                error_code=error_code,
            )
        )

    def _finalize(self, ctx: CallContext) -> None:
        ctx.finalized = True
        bundle = self._policy.bundle
        state = ctx.state
        trace = self._policy.trace(state.clinical) if state.clinical.facts else ()
        if ctx.outcome is not None:
            try:
                ctx.triage = build_triage_result(state, ctx.outcome, self._config.conversation)
            except ValueError:
                ctx.error_codes.append("TRIAGE_RESULT_INVALID")
        disposition = ctx.triage.disposition if ctx.triage else state.disposition
        if ctx.patient_id and ctx.triage and self._config.allow_record_writes:
            self._record(ctx, ctx.patient_id, ctx.triage)
        ended_at = max(self._clock.now(), ctx.started_at)
        self._audit.append_decision_record(
            DecisionRecord(
                call_id=state.call_id,
                synthetic_patient_id=ctx.patient_id,
                recorded_at=ended_at,
                policy_id=bundle.policy_id,
                policy_version=bundle.version,
                policy_checksum_sha256=bundle.checksum_sha256,
                facts_recorded=state.clinical.facts,
                rule_evaluations=trace,
                disposition=disposition,
            )
        )
        self._audit.append_audit_record(
            AuditRecord(
                call_id=state.call_id,
                synthetic_patient_id=ctx.patient_id,
                started_at=ctx.started_at,
                ended_at=ended_at,
                policy_id=bundle.policy_id,
                policy_version=bundle.version,
                policy_checksum_sha256=bundle.checksum_sha256,
                question_ids_asked=state.conversation.asked_question_ids,
                fact_ids_recorded=tuple(f.fact_id for f in state.clinical.facts),
                rule_evaluations=trace,
                disposition=disposition,
                appointment_option_ids_considered=tuple(dict.fromkeys(ctx.considered_offer_ids)),
                human_decision_codes=tuple(ctx.human_decisions),
                operations=tuple(ctx.operations),
                error_codes=tuple(ctx.error_codes),
            )
        )
        self._emit(ctx, "CALL.FINALIZED", OperationOutcome.COMPLETED)

    def _record(self, ctx: CallContext, patient_id: str, triage: TriageResult) -> None:
        bundle = self._policy.bundle
        summary = CallSummary(
            call_id=ctx.state.call_id,
            synthetic_patient_id=patient_id,
            disposition_code=triage.disposition.value,
            rationale_code=triage.rationale_code,
            policy_id=bundle.policy_id,
            policy_version=bundle.version,
            trigger_rule_ids=triage.trigger_rule_ids,
            symptom_fact_ids=triage.symptom_fact_ids,
        )
        writes = (
            ("EHR.RECORD_CALL_SUMMARY", lambda: self._ehr.record_call_summary(summary)),
            (
                "EHR.RECORD_TRIAGE_RESULT",
                lambda: self._ehr.record_triage_result(
                    patient_id=patient_id,
                    result=triage,
                    idempotency_key=f"{ctx.state.call_id}:triage",
                ),
            ),
        )
        for code, write in writes:
            try:
                result = self._ehr_call(ctx, code, write, audit_success=False)
            except _EHRFailed:
                continue
            outcome = OperationOutcome.COMPLETED if result.completed else OperationOutcome.FAILED
            self._operation(ctx, code, "ehr", outcome, result.failure_code)
