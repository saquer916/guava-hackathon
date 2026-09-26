"""Deterministic, auditable evaluation of a versioned PolicyBundle.

This engine routes calls; it does not diagnose and certifies nothing as safe.
Semantics:

- Predicates are three-valued. A fact that is absent, undefined by the bundle,
  or does not match its definition's type/unit is UNKNOWN, never false.
- A rule matches only if every `all_of` predicate is true, at least one
  `any_of` predicate is true (when present), and every `required_fact_ids` fact
  is known. It is ruled out only when a known predicate makes it false.
- Any matched EMERGENCY rule yields EMERGENCY immediately, regardless of other
  facts. An EMERGENCY rule that is not yet ruled out blocks every ordinary
  disposition and names the facts needed to resolve it.
- Lower `priority` values take precedence. An unresolved rule that outranks the
  best match blocks it; tied matches that disagree fail closed; no match fails
  closed. There is no default disposition.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from clinical_triage.conversation.config import PolicyOutcome
from clinical_triage.domain.audit import RuleEvaluationTrace
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact, ClinicalState, FactValue
from clinical_triage.domain.policy import (
    FactDataType,
    FactDefinition,
    FactPredicate,
    PolicyBundle,
    PolicyEvaluation,
    PolicyReviewStatus,
    PredicateOperator,
    RuleSpec,
)


class PolicyLoadError(ValueError):
    """The bundle is malformed, tampered with, or not permitted in this mode."""


class Truth(Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


def canonical_checksum(document: Mapping[str, Any]) -> str:
    body = {key: value for key, value in document.items() if key != "checksum_sha256"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode()).hexdigest()


def load_policy_bundle(path: Path, *, allow_example_unreviewed: bool) -> PolicyBundle:
    document = json.loads(path.read_text(encoding="utf-8"))
    if canonical_checksum(document) != document.get("checksum_sha256"):
        raise PolicyLoadError("POLICY_CHECKSUM_MISMATCH")
    bundle = PolicyBundle.model_validate(document)
    if (
        bundle.review_status is PolicyReviewStatus.EXAMPLE_UNREVIEWED
        and not allow_example_unreviewed
    ):
        raise PolicyLoadError("POLICY_NOT_CLINICIAN_REVIEWED")
    return bundle


@dataclass(frozen=True)
class RuleResult:
    rule: RuleSpec
    truth: Truth
    missing_fact_ids: tuple[str, ...]
    evidence_fact_ids: tuple[str, ...]


class SafetyPolicyEngine:
    def __init__(self, bundle: PolicyBundle) -> None:
        if bundle.review_status is PolicyReviewStatus.EXAMPLE_UNREVIEWED and (
            "EXAMPLE_UNREVIEWED" not in bundle.policy_id
        ):
            raise PolicyLoadError("EXAMPLE_POLICY_ID_MUST_BE_MARKED")
        for rule in bundle.rules:
            if rule.disposition is Disposition.EMERGENCY and not rule.approved_script_id:
                raise PolicyLoadError("EMERGENCY_RULE_REQUIRES_SCRIPT")
        self.bundle = bundle
        self._definitions = {d.fact_id: d for d in bundle.fact_definitions}
        self._definition_order = {d.fact_id: i for i, d in enumerate(bundle.fact_definitions)}
        self._rules = tuple(sorted(bundle.rules, key=lambda r: (r.priority, r.rule_id)))

    @property
    def review_status(self) -> PolicyReviewStatus:
        return self.bundle.review_status

    def __call__(self, clinical: ClinicalState) -> PolicyOutcome:
        evaluation, results = self._evaluate(clinical)
        script = None
        if evaluation.disposition is Disposition.EMERGENCY:
            script = next(
                r.rule.approved_script_id
                for r in results
                if r.truth is Truth.TRUE and r.rule.disposition is Disposition.EMERGENCY
            )
        return PolicyOutcome(evaluation=evaluation, escalation_script_id=script)

    def evaluate(self, clinical: ClinicalState) -> PolicyEvaluation:
        return self._evaluate(clinical)[0]

    def trace(self, clinical: ClinicalState) -> tuple[RuleEvaluationTrace, ...]:
        _, results = self._evaluate(clinical)
        return tuple(
            RuleEvaluationTrace(
                rule_id=r.rule.rule_id,
                evaluated=True,
                triggered=r.truth is Truth.TRUE,
                evidence_fact_ids=r.evidence_fact_ids,
            )
            for r in results
        )

    # --- internals -------------------------------------------------------

    def _evaluate(self, clinical: ClinicalState) -> tuple[PolicyEvaluation, tuple[RuleResult, ...]]:
        known, invalid = self._known_facts(clinical)
        results = tuple(self._rule_result(rule, known) for rule in self._rules)
        base: dict[str, Any] = {
            "policy_id": self.bundle.policy_id,
            "policy_version": self.bundle.version,
            "policy_checksum_sha256": self.bundle.checksum_sha256,
            "considered_fact_ids": tuple(sorted(known, key=self._fact_order)),
        }

        emergency = [r for r in results if r.rule.disposition is Disposition.EMERGENCY]
        matched_emergency = [r for r in emergency if r.truth is Truth.TRUE]
        if matched_emergency:
            unresolved = [r for r in emergency if r.truth is Truth.UNKNOWN]
            return (
                PolicyEvaluation(
                    **base,
                    matched_rule_ids=tuple(r.rule.rule_id for r in matched_emergency),
                    unresolved_rule_ids=tuple(r.rule.rule_id for r in unresolved),
                    disposition=Disposition.EMERGENCY,
                ),
                results,
            )

        unresolved_emergency = [r for r in emergency if r.truth is Truth.UNKNOWN]
        if unresolved_emergency:
            return self._fail_closed(base, results, unresolved_emergency, "EMERGENCY_NOT_RULED_OUT")

        if invalid:
            return self._fail_closed(base, results, [], "INVALID_FACT_VALUE")

        ordinary = [r for r in results if r.rule.disposition is not Disposition.EMERGENCY]
        matched = [r for r in ordinary if r.truth is Truth.TRUE]
        if not matched:
            unresolved = [r for r in ordinary if r.truth is Truth.UNKNOWN]
            reason = "RULES_UNRESOLVED" if unresolved else "NO_RULE_MATCHED"
            return self._fail_closed(base, results, unresolved, reason)

        best = matched[0].rule.priority
        blocking = [r for r in ordinary if r.truth is Truth.UNKNOWN and r.rule.priority <= best]
        if blocking:
            return self._fail_closed(base, results, blocking, "HIGHER_PRECEDENCE_RULE_UNRESOLVED")
        top = [r for r in matched if r.rule.priority == best]
        if len({r.rule.disposition for r in top}) > 1:
            return self._fail_closed(base, results, [], "CONFLICTING_RULES")
        return (
            PolicyEvaluation(
                **base,
                matched_rule_ids=tuple(r.rule.rule_id for r in top),
                suppressed_rule_ids=tuple(
                    r.rule.rule_id for r in matched if r.rule.priority != best
                ),
                disposition=top[0].rule.disposition,
            ),
            results,
        )

    def _fail_closed(
        self,
        base: Mapping[str, Any],
        results: tuple[RuleResult, ...],
        unresolved: list[RuleResult],
        reason: str,
    ) -> tuple[PolicyEvaluation, tuple[RuleResult, ...]]:
        needed: list[str] = []
        for result in unresolved:
            for fact_id in result.missing_fact_ids:
                if fact_id not in needed:
                    needed.append(fact_id)
        return (
            PolicyEvaluation(
                **base,
                matched_rule_ids=(),
                unresolved_rule_ids=tuple(r.rule.rule_id for r in unresolved),
                next_required_fact_ids=tuple(needed),
                fail_closed_reason=reason,
            ),
            results,
        )

    def _fact_order(self, fact_id: str) -> tuple[int, str]:
        return (self._definition_order.get(fact_id, len(self._definition_order)), fact_id)

    def _known_facts(self, clinical: ClinicalState) -> tuple[dict[str, ClinicalFact], list[str]]:
        known: dict[str, ClinicalFact] = {}
        invalid: list[str] = []
        for fact in clinical.facts:
            definition = self._definitions.get(fact.fact_id)
            if definition is None:
                continue
            if _fact_matches_definition(fact, definition):
                known[fact.fact_id] = fact
            else:
                invalid.append(fact.fact_id)
        return known, invalid

    def _rule_result(self, rule: RuleSpec, known: Mapping[str, ClinicalFact]) -> RuleResult:
        all_truths = [_predicate(p, known) for p in rule.all_of]
        any_truths = [_predicate(p, known) for p in rule.any_of]
        all_part = _conjunction(all_truths)
        any_part = _disjunction(any_truths) if rule.any_of else Truth.TRUE
        truth = _conjunction([all_part, any_part])
        missing_required = [f for f in rule.required_fact_ids if f not in known]
        if truth is Truth.TRUE and missing_required:
            truth = Truth.UNKNOWN
        referenced = [p.fact_id for p in rule.all_of + rule.any_of] + list(rule.required_fact_ids)
        missing: list[str] = []
        for fact_id in referenced:
            if fact_id not in known and fact_id not in missing:
                missing.append(fact_id)
        evidence = tuple(dict.fromkeys(f for f in referenced if f in known))
        return RuleResult(
            rule=rule,
            truth=truth,
            missing_fact_ids=tuple(missing) if truth is Truth.UNKNOWN else (),
            evidence_fact_ids=evidence,
        )


def _conjunction(truths: list[Truth]) -> Truth:
    if any(t is Truth.FALSE for t in truths):
        return Truth.FALSE
    if all(t is Truth.TRUE for t in truths):
        return Truth.TRUE
    return Truth.UNKNOWN


def _disjunction(truths: list[Truth]) -> Truth:
    if any(t is Truth.TRUE for t in truths):
        return Truth.TRUE
    if all(t is Truth.FALSE for t in truths):
        return Truth.FALSE
    return Truth.UNKNOWN


def _predicate(predicate: FactPredicate, known: Mapping[str, ClinicalFact]) -> Truth:
    fact = known.get(predicate.fact_id)
    if fact is None:
        return Truth.UNKNOWN
    if predicate.operator is PredicateOperator.PRESENT:
        return Truth.TRUE
    if predicate.unit_code is not None and fact.unit_code != predicate.unit_code:
        return Truth.UNKNOWN
    value = fact.value
    expected = predicate.value
    if predicate.operator is PredicateOperator.EQUALS:
        return _truth(_same(value, expected))
    if predicate.operator is PredicateOperator.IN:
        assert isinstance(expected, tuple)
        return _truth(any(_same(value, option) for option in expected))
    comparable = _ordered(value, expected)
    if comparable is None:
        return Truth.UNKNOWN
    left, right = comparable
    if predicate.operator is PredicateOperator.GREATER_THAN_OR_EQUAL:
        return _truth(left >= right)
    return _truth(left <= right)


def _truth(value: bool) -> Truth:
    return Truth.TRUE if value else Truth.FALSE


def _same(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    return left == right


def _ordered(left: FactValue, right: object) -> tuple[Any, Any] | None:
    numeric = (int, float)
    if isinstance(left, numeric) and not isinstance(left, bool):
        if isinstance(right, numeric) and not isinstance(right, bool):
            return left, right
        return None
    if isinstance(left, datetime) and isinstance(right, datetime):
        return left, right
    if isinstance(left, date) and not isinstance(left, datetime):
        if isinstance(right, date) and not isinstance(right, datetime):
            return left, right
    return None


def _fact_matches_definition(fact: ClinicalFact, definition: FactDefinition) -> bool:
    value = fact.value
    data_type = definition.data_type
    if definition.allowed_unit_codes and fact.unit_code not in definition.allowed_unit_codes:
        return False
    if not definition.allowed_unit_codes and fact.unit_code is not None:
        return False
    if data_type in {FactDataType.TEXT, FactDataType.CODE}:
        return isinstance(value, str) and bool(value)
    if data_type is FactDataType.BOOLEAN:
        return isinstance(value, bool)
    if data_type is FactDataType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type is FactDataType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if data_type is FactDataType.DATE:
        return isinstance(value, date) and not isinstance(value, datetime)
    return isinstance(value, datetime) and value.tzinfo is not None
