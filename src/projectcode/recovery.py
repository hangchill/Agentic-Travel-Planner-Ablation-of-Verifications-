"""Single owner of technical retries, output corrections and semantic repairs."""
from copy import deepcopy
from dataclasses import dataclass, asdict
from decimal import Decimal
from itertools import islice
import json
import math
import ssl
import time
from typing import Literal
from urllib.error import HTTPError, URLError
from pydantic import ValidationError
from .schemas import Constraint, Itinerary, Check

_MISSING = object()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


class TransientError(Exception):
    pass


class PermanentError(Exception):
    pass


class NoMatchingOptions(Exception):
    pass


class InvalidToolArguments(Exception):
    """Tool input checks failed; errors is a structured list without secrets."""
    def __init__(self, errors):
        super().__init__('Invalid tool arguments')
        self.errors = deepcopy(errors)


class HardConstraintConflict(Exception):
    """Only a trusted detector may report a proven contradiction."""
    def __init__(self, constraint_ids, evidence, *, proven=False):
        super().__init__('Hard constraint conflict')
        self.constraint_ids = list(constraint_ids)
        self.evidence, self.proven = evidence, proven


class _Stop(Exception):
    def __init__(self, reason, execution_error=False):
        self.reason, self.execution_error = reason, execution_error
        super().__init__(reason)


TERMINATION_REASONS = {
    'all_checks_pass': 'All expected checks pass.',
    'tool_success': 'Tool completed; its output is not automatically a verified plan.',
    'option_found': 'An option passed all original hard-constraint checks.',
    'no_matching_options': 'No verified option was found within the search allowance; impossibility is not proven.',
    'missing_information': 'Available sandbox queries cannot resolve the remaining unknown checks.',
    'hard_constraint_conflict': 'A trusted detector supplied evidence of conflicting hard constraints; none were relaxed.',
    'possible_hard_conflict': 'A conflict was reported without a proof; no impossibility claim is made.',
    'invalid_tool_arguments': 'Tool arguments need correction, but no correction callback was supplied.',
    'argument_correction_limit': 'Tool-argument corrections were exhausted.',
    'invalid_output': 'Structured-output correction attempts were exhausted.',
    'invalid_initial_plan': 'The initial itinerary does not match the shared schema.',
    'invalid_constraints': 'Original constraints do not match the shared contract or have duplicate IDs.',
    'unsupported_claims': 'Unsupported claims remain; offending plans are rejected and claims labelled UNVERIFIED.',
    'unchanged_plan': 'The same substantive plan was proposed consecutively.',
    'repeated_plan': 'A previously seen substantive plan reappeared in a cycle.',
    'repair_limit': 'Semantic repair allowance was exhausted; this is not proof of impossibility.',
    'technical_retry_limit': 'Temporary operation failures persisted beyond the retry allowance.',
    'permanent_error': 'A permanent API/configuration error stopped the request without retry.',
    'overall_call_limit': 'The shared operation-attempt limit was reached.',
    'overall_model_call_limit': 'The shared model-attempt limit was reached.',
    'overall_time_limit': 'The overall deadline was reached or cannot accommodate the next retry delay.',
    'execution_error': 'An unexpected integration or execution error stopped the request.',
}


def classify_api_error(exc):
    """Classify stdlib/SDK-style exceptions without SDK imports or logging bodies."""
    if isinstance(exc, PermanentError):
        return 'permanent'
    status = getattr(exc, 'status_code', None)
    if status is None and isinstance(exc, HTTPError):
        status = exc.code
    if status is None:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if isinstance(status, int) and 400 <= status <= 599:
        return 'transient' if status in {408, 409, 425, 429, 500, 502, 503, 504} else 'permanent'
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        return 'permanent'
    if isinstance(exc, (TransientError, TimeoutError, ConnectionError, URLError)):
        return 'transient'
    return 'other'


@dataclass(frozen=True)
class Policy:
    strategy: Literal['whole_plan', 'targeted', 'protected_targeted'] = 'protected_targeted'
    repair_limit: int = 3
    technical_retries: int = 3
    correction_limit: int = 3
    argument_correction_limit: int = 3
    factual_revision_limit: int = 3
    evidence_query_limit: int = 2
    alternative_search_limit: int = 2
    max_operations: int = 100
    max_model_calls: int = 40
    max_run_seconds: float = 180
    timeout_seconds: float = 30
    backoff_mode: Literal['fixed', 'exponential'] = 'fixed'
    backoff_seconds: float = 0.5
    max_backoff_seconds: float = 4

    def __post_init__(self):
        if self.strategy not in ('whole_plan', 'targeted', 'protected_targeted'):
            raise ValueError('Unknown strategy')
        if self.backoff_mode not in ('fixed', 'exponential'):
            raise ValueError('Unknown backoff mode')
        for key in ('repair_limit', 'technical_retries', 'correction_limit',
                    'argument_correction_limit', 'factual_revision_limit', 'evidence_query_limit',
                    'alternative_search_limit', 'max_operations', 'max_model_calls'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError(key + ' must be a nonnegative integer')
        for key in ('max_run_seconds', 'timeout_seconds', 'backoff_seconds', 'max_backoff_seconds'):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(key + ' must be finite')
        if not 0 < self.timeout_seconds <= 300 or self.max_run_seconds <= 0:
            raise ValueError('Timeouts must be positive; operation timeout must be <= 300')
        if not 0 <= self.backoff_seconds <= self.max_backoff_seconds <= 60:
            raise ValueError('Invalid backoff bounds')


def complete_report(report, constraints):
    """Missing expected checks are unknown; duplicate/extra IDs are integration errors."""
    checks = [Check.model_validate(c).model_dump() for c in report]
    ids = [c['constraint_id'] for c in checks]
    expected = [c['constraint_id'] for c in constraints]
    if len(set(ids)) != len(ids) or set(ids) - set(expected):
        raise ValueError('Verifier returned duplicate or unexpected check IDs')
    by_id = {c['constraint_id']: c for c in checks}
    return [by_id.get(i, Check(constraint_id=i, status='UNVERIFIABLE',
            failure_kind='missing_information', evidence='Required check missing').model_dump()) for i in expected]


def statuses(report):
    return {c['constraint_id']: c['status'] for c in report}


def transitions(before, after):
    b, a = statuses(before), statuses(after)
    return {
        'fixed': [i for i in b if b[i] == 'FAIL' and a[i] == 'PASS'],
        'remaining': [i for i in a if a[i] == 'FAIL'],
        'new_violations': [i for i in b if b[i] == 'PASS' and a[i] == 'FAIL'],
        'to_unverifiable': [i for i in b if b[i] != 'UNVERIFIABLE' and a[i] == 'UNVERIFIABLE'],
    }


def rank(report, constraints):
    s = statuses(report)
    return tuple(sum(s[c['constraint_id']] != 'PASS' for c in constraints if c['hardness'] == h)
                 for h in ('hard', 'soft'))


def in_scope(before, after, allowed):
    """Only existing activities listed in allowed may change; IDs/order stay fixed."""
    b, a = deepcopy(before), deepcopy(after)
    for plan in (b, a):
        for day in plan['days']:
            day['activities'] = [({'activity_id': x['activity_id']} if x['activity_id'] in allowed else x)
                                 for x in day['activities']]
    return b == a


def plan_fingerprint(plan):
    """Detect substantive cycles despite summary, slot ID or display-name changes.

    Keeps order, location, timing, category and prices. Unknown locations retain
    their names/text. Inject another function if your verifier uses other semantics.
    """
    obj = deepcopy(plan)
    obj.pop('summary', None)
    for day in obj['days']:
        for activity in day['activities']:
            activity.pop('activity_id', None)
            if activity.get('location_id') is not None:
                activity.pop('name', None)
                activity.pop('location', None)
            if activity.get('price_usd') is not None:
                activity['price_usd'] = str(Decimal(str(activity['price_usd'])).normalize())
    if obj.get('total_cost_usd') is not None:
        obj['total_cost_usd'] = str(Decimal(str(obj['total_cost_usd'])).normalize())
    return canonical(obj)


def _constraints(raw, *, allow_empty=False):
    constraints = [Constraint.model_validate(c).model_dump(mode='json') for c in deepcopy(raw)]
    if (not constraints and not allow_empty) or len({c['constraint_id'] for c in constraints}) != len(constraints):
        raise ValueError('Require unique constraint IDs')
    return constraints


class Recovery:
    """Adapters accept timeout=seconds and MUST enforce it at their I/O boundary.

    model(payload, timeout=...) -> JSON string/dict; verifier(plan,constraints,timeout=...)
    -> list[Check dict]. No internal adapter retries. emit(event) persists checkpoints.
    """
    def __init__(self, model, verifier, policy=None, *, sleep=time.sleep, emit=None,
                 clock=time.monotonic, evidence_tools=(), fingerprint=plan_fingerprint):
        self.model, self.verifier = model, verifier
        self.policy = policy or Policy()
        self.sleep, self.clock = sleep, clock
        self.emit = emit or (lambda event: None)
        self.evidence_tools = tuple(islice(evidence_tools, self.policy.evidence_query_limit))
        self.fingerprint = fingerprint
        self.events = []
        self.model_calls = self.operation_calls = 0
        self._started = None
        self._finished = False
        self._terminal = None

    def event(self, kind, **fields):
        event = deepcopy(dict(kind=kind, **fields))
        self.events.append(event)
        self.emit(deepcopy(event))

    def _guard(self):
        if self._started is None:
            self._started = self.clock()
        if self._terminal is not None:
            raise self._terminal
        if self.clock() - self._started >= self.policy.max_run_seconds:
            raise _Stop('overall_time_limit', True)

    @property
    def remaining_timeout(self):
        self._guard()
        return min(self.policy.timeout_seconds, self.policy.max_run_seconds - (self.clock() - self._started))

    def call(self, operation, fn):
        """One attempt is charged for every callback, including retries/corrections."""
        if self._finished:
            raise RuntimeError('Create a new Recovery instance for a new request')
        for attempt in range(self.policy.technical_retries + 1):
            self._guard()
            if self.operation_calls >= self.policy.max_operations:
                raise _Stop('overall_call_limit', True)
            if operation == 'model' and self.model_calls >= self.policy.max_model_calls:
                raise _Stop('overall_model_call_limit', True)
            self.operation_calls += 1
            self.model_calls += int(operation == 'model')
            self.event('operation_started', operation=operation, attempt=attempt + 1,
                       operation_calls=self.operation_calls)
            try:
                value = fn()
                self._guard()  # Do not accept a response returned after the deadline.
                return value
            except Exception as exc:
                if isinstance(exc, _Stop):
                    raise
                self._guard()
                classification = classify_api_error(exc)
                if classification == 'other':
                    raise
                self.event('technical_error', operation=operation, attempt=attempt + 1,
                           classification=classification, error_type=type(exc).__name__)
                if classification == 'permanent':
                    raise PermanentError() from None
                if attempt == self.policy.technical_retries:
                    raise _Stop('technical_retry_limit', True) from None
                multiplier = 2 ** attempt if self.policy.backoff_mode == 'exponential' else 1
                delay = min(self.policy.max_backoff_seconds, self.policy.backoff_seconds * multiplier)
                if delay >= self.policy.max_run_seconds - (self.clock() - self._started):
                    raise _Stop('overall_time_limit', True) from None
                self.event('retry_wait', operation=operation, delay_seconds=delay)
                self.sleep(delay)

    def _conflict(self, exc, constraints):
        hard = {c['constraint_id'] for c in constraints if c['hardness'] == 'hard'}
        if (not exc.constraint_ids or len(set(exc.constraint_ids)) != len(exc.constraint_ids)
                or not set(exc.constraint_ids) <= hard or not isinstance(exc.evidence, str)
                or not exc.evidence.strip() or type(exc.proven) is not bool):
            raise ValueError('Conflict requires known hard constraint IDs and evidence')
        return dict(constraint_ids=exc.constraint_ids, evidence=exc.evidence, proven=exc.proven)

    def _check_conflicts(self, report):
        conflicts = [c for c in report if c.get('failure_kind') == 'hard_conflict']
        if conflicts:
            raise HardConstraintConflict([c['constraint_id'] for c in conflicts],
                '\n'.join(c['evidence'] for c in conflicts), proven=all(c['conflict_proven'] for c in conflicts))

    def _failure(self, exc, constraints):
        conflict = None
        if isinstance(exc, HardConstraintConflict):
            try:
                conflict = self._conflict(exc, constraints)
                reason = 'hard_constraint_conflict' if conflict['proven'] else 'possible_hard_conflict'
                execution_error = False
            except ValueError:
                reason, execution_error = 'execution_error', True
        elif isinstance(exc, _Stop):
            reason, execution_error = exc.reason, exc.execution_error
        elif isinstance(exc, NoMatchingOptions):
            reason, execution_error = 'no_matching_options', False
        else:
            reason = 'permanent_error' if isinstance(exc, PermanentError) else 'execution_error'
            execution_error = True
        self.event('failure', reason=reason, error_type=type(exc).__name__, conflict=conflict)
        return reason, execution_error, conflict

    def _operation_result(self, reason, *, value=None, execution_error=False, conflict=None):
        success = reason in ('tool_success', 'option_found')
        if not success:
            self._terminal = _Stop(reason, execution_error)
        return dict(status='PASS' if success else 'ERROR' if execution_error else 'PARTIAL',
                    termination_reason=reason, explanation=TERMINATION_REASONS[reason],
                    value=value, execution_error=execution_error, conflict=conflict,
                    model_calls=self.model_calls, operation_calls=self.operation_calls)

    def run_tool(self, tool, arguments, *, argument_schema, correct_arguments=None, constraints=()):
        """Validate/correct tool arguments, then execute with bounded retries.

        argument_schema is a Pydantic class. tool(args, timeout=...) returns data.
        correct_arguments(payload, timeout=...) returns dict/JSON in a single call;
        its invocations count as model calls. Tool output still needs verification.
        """
        original_constraints = []
        try:
            original_constraints = _constraints(constraints, allow_empty=True)
            self._guard()
            args = deepcopy(arguments)
            for correction in range(self.policy.argument_correction_limit + 1):
                try:
                    if isinstance(args, str):
                        args = json.loads(args)
                    valid = argument_schema.model_validate(args).model_dump(mode='json')
                    result = self.call('tool', lambda: tool(deepcopy(valid), timeout=self.remaining_timeout))
                    return self._operation_result('tool_success', value=result)
                except (ValidationError, InvalidToolArguments, json.JSONDecodeError) as exc:
                    errors = ([{'loc': list(e['loc']), 'type': e['type']} for e in exc.errors()]
                              if isinstance(exc, ValidationError) else exc.errors if isinstance(exc, InvalidToolArguments)
                              else [{'loc': [], 'type': 'invalid_json'}])
                    self.event('invalid_tool_arguments', correction=correction, errors=errors)
                    if correct_arguments is None:
                        raise _Stop('invalid_tool_arguments', True) from None
                    if correction == self.policy.argument_correction_limit:
                        raise _Stop('argument_correction_limit', True) from None
                    payload = dict(arguments=args, errors=errors, schema=argument_schema.model_json_schema(),
                                   constraints=original_constraints)
                    args = self.call('model', lambda: correct_arguments(deepcopy(payload), timeout=self.remaining_timeout))
        except Exception as exc:
            reason, error, conflict = self._failure(exc, original_constraints)
            return self._operation_result(reason, execution_error=error, conflict=conflict)

    def find_option(self, searches, constraints, option_verifier):
        """Primary plus bounded alternative searches; select only verified hard passes.

        search(constraints, timeout=...) -> ranked option list.
        option_verifier(option, constraints, timeout=...) -> checks.
        Exhaustion is no_matching_options, never an inferred contradiction.
        """
        original = []
        try:
            original = _constraints(constraints)
            for index, search in enumerate(islice(searches, self.policy.alternative_search_limit + 1)):
                try:
                    options = self.call('search', lambda: search(deepcopy(original), timeout=self.remaining_timeout))
                except NoMatchingOptions:
                    options = []
                if not isinstance(options, list):
                    raise ValueError('Search must return a list')
                self.event('search_result', search_index=index, option_count=len(options))
                for option in options:
                    report = complete_report(self.call('option_verifier', lambda: option_verifier(
                        deepcopy(option), deepcopy(original), timeout=self.remaining_timeout)), original)
                    self._check_conflicts(report)
                    safe = not any(c.get('failure_kind') == 'unsupported_claim' for c in report)
                    if safe and all(statuses(report)[c['constraint_id']] == 'PASS' for c in original if c['hardness'] == 'hard'):
                        return self._operation_result('option_found', value=deepcopy(option))
                    self.event('option_rejected', search_index=index, report=report)
            raise NoMatchingOptions()
        except Exception as exc:
            reason, error, conflict = self._failure(exc, original)
            return self._operation_result(reason, execution_error=error, conflict=conflict)

    def verify(self, plan, constraints):
        report = complete_report(self.call('verifier', lambda: self.verifier(
            deepcopy(plan), deepcopy(constraints), timeout=self.remaining_timeout)), constraints)
        self._check_conflicts(report)
        for index, tool in enumerate(self.evidence_tools):
            missing = {c['constraint_id'] for c in report if c['status'] == 'UNVERIFIABLE'
                       and c.get('failure_kind') in (None, 'missing_information')}
            if not missing:
                break
            try:
                supplement = complete_report(self.call('evidence_tool', lambda: tool(
                    deepcopy(plan), deepcopy(constraints), timeout=self.remaining_timeout)), constraints)
            except NoMatchingOptions:
                self.event('evidence_query', source_index=index, requested=sorted(missing), found=False)
                continue
            self._check_conflicts(supplement)
            updates = {c['constraint_id']: c for c in supplement if c['constraint_id'] in missing
                       and (c['status'] != 'UNVERIFIABLE' or c.get('failure_kind') == 'unsupported_claim')}
            report = [updates.get(c['constraint_id'], c) for c in report]
            self.event('evidence_query', source_index=index, requested=sorted(missing), report=report)
        return report

    def generate(self, payload, *, initial_output=_MISSING):
        payload = deepcopy(payload)
        for correction in range(self.policy.correction_limit + 1):
            raw = (initial_output if correction == 0 and initial_output is not _MISSING else
                   self.call('model', lambda: self.model(deepcopy(payload), timeout=self.remaining_timeout)))
            try:
                obj = json.loads(raw) if isinstance(raw, str) else raw
                return Itinerary.model_validate(obj).model_dump(mode='json')
            except (ValueError, TypeError, ValidationError):
                # Never log arbitrary exception text (may contain credentials or response bodies).
                self.event('invalid_output', correction=correction, output=raw)
                if correction == self.policy.correction_limit:
                    raise _Stop('invalid_output', True) from None
                payload['format_feedback'] = 'Return only JSON matching this schema.'
                payload['schema'] = Itinerary.model_json_schema()

    def run(self, initial, constraints, *, initial_report=None):
        if self._finished:
            raise RuntimeError('Create a new Recovery instance for a new request')
        history, report, final_report = [], [], []
        current = best = initial_snapshot = initial_checks = None
        original = []
        reason, execution_error, conflict = 'repair_limit', False, None
        factual_revisions = 0
        unsupported = False
        pending_rejection = None
        try:
            try:
                original = _constraints(constraints)
            except (ValueError, TypeError, ValidationError):
                raise _Stop('invalid_constraints', True) from None
            self._guard()
            try:
                current = Itinerary.model_validate(initial).model_dump(mode='json')
            except (ValueError, TypeError, ValidationError):
                current = self.generate(dict(plan=initial, constraints=original,
                    schema=Itinerary.model_json_schema()), initial_output=initial)
            initial_snapshot = canonical(current)
            report = self.verify(current, original) if initial_report is None else complete_report(initial_report, original)
            initial_checks = canonical(report)
            self.event('initial', plan=current, report=report)
            self._check_conflicts(report)
            unsupported = any(c.get('failure_kind') == 'unsupported_claim' for c in report)
            if not unsupported:
                best, final_report = deepcopy(current), deepcopy(report)
            else:
                self.event('unsupported_claims', plan=current, report=report, accepted=False)
            last_fingerprint = self.fingerprint(current)
            seen = {last_fingerprint: 0}
            for attempt in range(1, self.policy.repair_limit + 1):
                self._guard()
                if all(c['status'] == 'PASS' for c in report):
                    reason = 'all_checks_pass'; break
                if not unsupported and all(c['status'] in ('PASS', 'UNVERIFIABLE') for c in report):
                    reason = 'missing_information'; break
                if unsupported and factual_revisions >= self.policy.factual_revision_limit:
                    reason = 'unsupported_claims'; break
                if unsupported:
                    factual_revisions += 1
                allowed = sorted({i for c in report if c['status'] != 'PASS' for i in c['activity_ids']})
                protected = [c['constraint_id'] for c in report if c['status'] == 'PASS']
                entry = dict(attempt=attempt, before=deepcopy(current), before_report=deepcopy(report),
                             accepted=False, allowed_activity_ids=allowed, protected_check_ids=protected)
                history.append(entry)
                self.event('repair_started', attempt=attempt, factual_revision=unsupported)
                candidate = self.generate(dict(plan=current, constraints=original, report=report,
                    strategy=self.policy.strategy, allowed_activity_ids=allowed,
                    protected_check_ids=protected, rejected_candidate=pending_rejection,
                    schema=Itinerary.model_json_schema()))
                entry['candidate'] = deepcopy(candidate)
                self.event('candidate', attempt=attempt, plan=candidate)
                after = self.verify(candidate, original)  # Recheck even repeated/rejected candidates.
                entry.update(report=after, **transitions(report, after))
                fingerprint = self.fingerprint(candidate)
                repeated = fingerprint in seen
                repeat_reason = 'unchanged_plan' if fingerprint == last_fingerprint else 'repeated_plan'
                if repeated:
                    entry['cycle_origin_attempt'] = seen[fingerprint]
                seen.setdefault(fingerprint, attempt)
                last_fingerprint = fingerprint
                candidate_unsupported = any(c.get('failure_kind') == 'unsupported_claim' for c in after)
                if repeated:
                    entry['reason'] = repeat_reason
                elif candidate_unsupported:
                    entry['reason'] = 'unsupported_claims'
                elif self.policy.strategy != 'whole_plan' and not in_scope(current, candidate, allowed):
                    entry['reason'] = 'outside_edit_scope'
                elif self.policy.strategy == 'protected_targeted' and any(statuses(after)[i] != 'PASS' for i in protected):
                    entry['reason'] = 'protected_check_regression'
                elif best is not None and rank(after, original) >= rank(report, original):
                    entry['reason'] = 'no_strict_improvement'
                else:
                    entry.update(accepted=True, reason='strict_improvement' if best is not None else 'grounded_fallback')
                    current, report = candidate, after
                    best, final_report = deepcopy(candidate), deepcopy(after)
                unsupported = candidate_unsupported or any(c.get('failure_kind') == 'unsupported_claim' for c in report)
                pending_rejection = None if entry['accepted'] else dict(plan=candidate, report=after, reason=entry['reason'])
                self.event('repair', **entry)
                if repeated:
                    reason = repeat_reason; break
            if all(c['status'] == 'PASS' for c in report):
                reason = 'all_checks_pass'
            elif reason == 'repair_limit' and unsupported:
                reason = 'unsupported_claims'
            elif reason == 'repair_limit' and all(c['status'] in ('PASS', 'UNVERIFIABLE') for c in report):
                reason = 'missing_information'
        except Exception as exc:
            reason, execution_error, conflict = self._failure(exc, original)
            if history and 'reason' not in history[-1]:
                history[-1]['reason'] = reason
        self._finished = True
        result = dict(initial_plan=initial_snapshot, initial_report=initial_checks,
            final=best, final_report=final_report, constraints=original, history=deepcopy(history),
            status='ERROR' if execution_error else 'PASS' if reason == 'all_checks_pass' else
                   'CONFLICT' if reason == 'hard_constraint_conflict' else 'PARTIAL',
            termination_reason=reason, explanation=TERMINATION_REASONS[reason], execution_error=execution_error,
            conflict=conflict, claims_status='UNVERIFIED' if best is None and unsupported else None,
            unresolved=[c['constraint_id'] for c in original if statuses(final_report).get(c['constraint_id']) != 'PASS'],
            model_calls=self.model_calls, operation_calls=self.operation_calls, factual_revisions=factual_revisions,
            elapsed_seconds=0 if self._started is None else self.clock() - self._started,
            policy=asdict(self.policy), events=deepcopy(self.events))
        self.event('final', result=result)
        return result


def recovery_node(controller):
    """LangGraph-compatible state update. Connect this node directly to END.

    Do not connect a graph back-edge or the older event controller: this owns the loop.
    """
    def node(state):
        draft = state['draft']
        if hasattr(draft, 'model_dump'):
            draft = draft.model_dump(mode='json')
        result = controller.run(draft, state['constraints'])
        return {'final': result['final'], 'recovery_result': result}
    return node
