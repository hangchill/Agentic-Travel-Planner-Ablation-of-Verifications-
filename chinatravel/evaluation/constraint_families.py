"""Conservative structural classification of ChinaTravel DSL; never executes code."""

import ast
from copy import deepcopy

NORMALIZER_VERSION = "1.0.0"
CONSTRAINT_FAMILIES = (
    "trip_specification", "party_resources", "monetary_budget", "accommodation",
    "dining", "attraction", "transport_mode", "travel_extent", "schedule_order",
)

# Tags describe measured values separately from activity-selection predicates.
_CALL_TAGS = {
    "day_count": {"trip_specification"}, "people_count": {"trip_specification"},
    "activity_tickets": {"party_resources"}, "metro_tickets": {"party_resources"},
    "taxi_cars": {"party_resources"},
    "room_count": {"accommodation"}, "room_type": {"accommodation"},
    "accommodation_type": {"accommodation"}, "restaurant_type": {"dining"},
    "attraction_type": {"attraction"},
    "activity_cost": {"monetary_budget"}, "activity_price": {"monetary_budget"},
    "innercity_transport_cost": {"monetary_budget"},
    "innercity_transport_price": {"monetary_budget"},
    "innercity_transport_distance": {"travel_extent"},
    "innercity_transport_time": {"travel_extent"},
    "activity_start_time": {"schedule_order"}, "activity_end_time": {"schedule_order"},
    "activity_time": {"schedule_order"},
    "innercity_transport_start_time": {"schedule_order"},
    "innercity_transport_end_time": {"schedule_order"},
    "innercity_transport_type": {"mode"}, "intercity_transport_type": {"mode"},
    "activity_type": {"activity_type"}, "activity_position": {"position"},
    "activity_transports": set(), "target_city": set(),
    "allactivities": set(), "dayactivities": {"day_scope"},
}
_DOMAIN = {"accommodation": "accommodation", "attraction": "attraction",
           "breakfast": "dining", "lunch": "dining", "dinner": "dining"}
_BUILTINS = {"set", "len", "list"}
_METHODS = {"add", "append"}
_NODES = (
    ast.Module, ast.Assign, ast.AugAssign, ast.Expr, ast.For, ast.If,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call, ast.Attribute,
    ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.List, ast.Tuple, ast.Set,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.BitAnd, ast.BitOr, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
)


def _union(values):
    return set().union(*values)


def _families(tags):
    families = tags & set(CONSTRAINT_FAMILIES)
    domains = {tag.split(":", 1)[1] for tag in tags if tag.startswith("domain:")}
    if not families:
        if "sequence" in tags or {"position", "day_scope"} <= tags:
            families = {"schedule_order"}
        elif domains:
            families = domains
        elif "mode" in tags:
            families = {"transport_mode"}
    return families


class _Analyzer:
    """Propagate value/guard provenance through the supported template subset.

    This is a syntactic approximation, not execution or a general theorem prover.
    Multiple independent result writes retain evidence rather than using a
    family-priority rule that could hide cross-family requirements.
    """

    def __init__(self):
        self.env = {"plan": set()}
        self.predicates = []

    def expression(self, node):
        if isinstance(node, ast.Name):
            return self.env.get(node.id, {"unresolved"})
        if isinstance(node, ast.Constant):
            return set()
        if isinstance(node, ast.Call):
            args = _union(self.expression(arg) for arg in node.args)
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in _BUILTINS:
                    return args
                # The measured concept, not its activity argument, defines value semantics.
                return set(_CALL_TAGS[name]) | (args & {"unresolved"})
        if isinstance(node, ast.Compare):
            tags = _union(self.expression(part) for part in (node.left, *node.comparators))
            parts = (node.left, *node.comparators)
            # Interpret activity-type literals only in their comparison, never POI text.
            if any(isinstance(part, ast.Call) and isinstance(part.func, ast.Name)
                   and part.func.id == "activity_type" for part in parts):
                literals = {item.value for part in parts for item in ast.walk(part)
                            if isinstance(item, ast.Constant) and isinstance(item.value, str)}
                tags |= {"domain:" + _DOMAIN[value] for value in literals if value in _DOMAIN}
                if literals & {"train", "airplane"}:
                    tags.add("mode")
            if "monetary_budget" in tags and any(
                isinstance(operator, (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
                for operator in node.ops
            ) and any(isinstance(part, ast.Constant) and type(part.value) in (int, float)
                      for part in parts):
                tags.add("budget_bound")
            return tags
        return _union(self.expression(child) for child in ast.iter_child_nodes(node))

    def block(self, statements, guards=frozenset()):
        for node in statements:
            if isinstance(node, ast.For):
                if not isinstance(node.target, ast.Name):
                    raise ValueError("Unsupported loop target")
                iterator = self.expression(node.iter)
                self.env[node.target.id] = iterator
                self.block(node.body, set(guards) | iterator)
                if node.orelse:
                    raise ValueError("Loop else is outside supported templates")
            elif isinstance(node, ast.If):
                condition = self.expression(node.test)
                snapshot = deepcopy(self.env)
                self.block(node.body, set(guards) | condition)
                then_env = deepcopy(self.env)
                self.env = snapshot
                self.block(node.orelse, set(guards) | condition)
                self.env = {name: then_env.get(name, set()) | self.env.get(name, set())
                            for name in then_env.keys() | self.env.keys()}
            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if not isinstance(target, ast.Name):
                        raise ValueError("Unsupported assignment target")
                    value = self.expression(node.value)
                    if target.id == "result":
                        # Literal result initializers are not requirements themselves.
                        tags = value | set(guards)
                        if not isinstance(node.value, (ast.Constant, ast.Compare, ast.BoolOp,
                                                       ast.UnaryOp, ast.Name)):
                            tags.add("unresolved")
                        predicate = node.value
                        while isinstance(predicate, ast.UnaryOp) and isinstance(predicate.op, ast.Not):
                            predicate = predicate.operand
                        if isinstance(predicate, ast.BoolOp):
                            # Explicit result clauses are requirements, unlike
                            # domain/mode filters guarding a quantity check.
                            self.predicates.extend(
                                self.expression(clause) | set(guards)
                                for clause in predicate.values
                                if self.expression(clause) | set(guards)
                            )
                        elif tags:
                            self.predicates.append(tags)
                        self.env[target.id] = tags
                    else:
                        # Guards select what gets counted; cost==0 is not money accumulation.
                        selectors = {tag for tag in guards if tag.startswith("domain:")}
                        selectors |= set(guards) & {"day_scope", "position", "sequence", "mode", "unresolved"}
                        if isinstance(node, ast.AugAssign):
                            self.env[target.id] = self.env.get(target.id, set()) | value | selectors
                        else:
                            tags = value | selectors
                            if isinstance(node.value, ast.Constant) and type(node.value.value) is bool:
                                if "position" in guards:
                                    tags.add("sequence")
                            self.env[target.id] = tags
            elif isinstance(node, ast.Expr):
                call = node.value
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                        and isinstance(call.func.value, ast.Name)):
                    raise ValueError("Unsupported expression statement")
                name = call.func.value.id
                tags = _union(self.expression(arg) for arg in call.args)
                selectors = {tag for tag in guards if tag.startswith("domain:")}
                selectors |= set(guards) & {"day_scope", "unresolved"}
                self.env[name] = self.env.get(name, set()) | tags | selectors


def classify_constraint(descriptor: dict) -> dict:
    """Classify one source descriptor without executing or importing the verifier.

    Invalid descriptor indices raise ValueError; malformed/unsupported DSL returns
    unmapped. Source fields are copied verbatim, including optional NL text.
    """
    index = descriptor.get("constraint_index")
    if type(index) is not int or index < 1:
        raise ValueError("constraint_index must be a positive 1-based integer")
    result = deepcopy(descriptor)
    result.update(family=None, classification_status="unmapped", matched_pattern_id=None,
                  normalizer_version=NORMALIZER_VERSION,
                  features={"concept_functions": [], "operators": [], "candidate_families": []},
                  reason=None)
    code = descriptor.get("hard_logic_py")
    if not isinstance(code, str):
        result["reason"] = "missing_or_non_string_dsl"
        return result
    try:
        tree = ast.parse(code, mode="exec")
    except (SyntaxError, ValueError, TypeError, RecursionError):
        result["reason"] = "malformed_dsl"
        return result
    calls = sorted({node.func.id for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)})
    result["features"]["concept_functions"] = [name for name in calls if name in _CALL_TAGS]
    result["features"]["operators"] = sorted({type(node).__name__ for node in ast.walk(tree)
        if isinstance(node, (ast.cmpop, ast.boolop, ast.unaryop, ast.operator))})
    for node in ast.walk(tree):
        if not isinstance(node, _NODES):
            result["reason"] = "unsupported_syntax"
            return result
        if isinstance(node, ast.Call):
            valid = (isinstance(node.func, ast.Name) and node.func.id in _CALL_TAGS.keys() | _BUILTINS)
            valid |= (isinstance(node.func, ast.Attribute) and node.func.attr in _METHODS
                      and isinstance(node.func.value, ast.Name))
            if not valid or node.keywords:
                result["reason"] = "unsupported_call"
                return result
    analyzer = _Analyzer()
    try:
        analyzer.block(tree.body)
    except (ValueError, RecursionError):
        result["reason"] = "unsupported_structure"
        return result
    groups = [_families(tags) for tags in analyzer.predicates]
    families = _union(groups)
    result["features"]["candidate_families"] = sorted(families)
    if any("unresolved" in tags for tags in analyzer.predicates):
        result["reason"] = "unresolved_result_dependency"
    elif any("monetary_budget" in tags and "budget_bound" not in tags
             for tags in analyzer.predicates):
        result["reason"] = "no_numeric_budget_bound"
    elif len(families) > 1:
        # Independent writes/Boolean clauses give compound evidence. A single
        # mixed-domain selector without distinct requirements is ambiguous.
        explicit_composition = len([group for group in groups if group]) > 1 or any(
            isinstance(node, ast.BoolOp) for node in ast.walk(tree)
        )
        result["classification_status"] = "compound" if explicit_composition else "ambiguous"
        result["reason"] = "multiple_families"
    elif len(families) == 1 and all(groups):
        family = next(iter(families))
        result.update(family=family, classification_status="mapped",
                      matched_pattern_id=f"structural.{family}.v1", reason=None)
    else:
        result["reason"] = "no_supported_result_pattern"
    return result


def classify_constraints(descriptors: list[dict]) -> list[dict]:
    """Classify descriptors in supplied order, preserving their source indices."""
    return [classify_constraint(descriptor) for descriptor in descriptors]
