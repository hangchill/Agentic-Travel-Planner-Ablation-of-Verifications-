"""Deterministic, domain-scoped DSL category comparison normalization."""
import ast
import json
from pathlib import Path
import re
import unicodedata
from chinatravel.environment.concept_labels import LEGACY_ENGLISH_CONCEPT_VALUE_ALIASES

TAXONOMY = json.loads(Path(__file__).with_name('category_taxonomy.json').read_text(encoding='utf-8'))
FUNCTION_DOMAINS = {'restaurant_type': 'restaurant', 'attraction_type': 'attraction',
                    'accommodation_type': 'accommodation', 'activity_type': 'activity',
                    'innercity_transport_type': 'transport', 'intercity_transport_type': 'transport'}


def _basic(value):
    value = unicodedata.normalize('NFKC', value).casefold().strip()
    value = value.translate(str.maketrans({'‐': '-', '‑': '-', '–': '-', '—': '-', '’': "'"}))
    return re.sub(r'\s+', ' ', value)


def _key(value):
    return re.sub(r'\s*[-/]\s*', ' ', _basic(value))


ALIASES = {}
for domain, pairs in TAXONOMY.items():
    aliases = {}
    legacy = LEGACY_ENGLISH_CONCEPT_VALUE_ALIASES.get(domain, {})
    for raw, canonical in pairs.items():
        canonical = legacy.get(canonical, canonical)
        aliases[_key(raw)] = canonical
        aliases[_key(canonical)] = canonical
    for raw, canonical in legacy.items():
        aliases[_key(raw)] = canonical
        aliases[_key(canonical)] = canonical
    ALIASES[domain] = aliases
# Explicit requested synonym; no general food/cuisine suffix guessing.
ALIASES['restaurant'][_key('Sichuan food')] = 'Sichuan cuisine'


def normalize_category_label(value, domain='restaurant'):
    """Known aliases use canonical English; unknowns retain basic normalized text.

    This function is not applied to arbitrary DSL strings or entity identities.
    """
    if not isinstance(value, str):
        return value
    return ALIASES.get(domain, {}).get(_key(value), _basic(value))


def normalize_operand(value, domain, expression, diagnostics=None):
    if isinstance(value, str):
        normalized = normalize_category_label(value, domain)
        if diagnostics is not None:
            diagnostics.append(dict(category_domain=domain, expression=expression,
                                    raw_label=value, normalized_label=normalized))
        return normalized
    if isinstance(value, (list, tuple, set, frozenset)):
        return type(value)(normalize_operand(item, domain, expression, diagnostics) for item in value)
    return value


def normalize_comparisons(tree, helper_name):
    """Normalize only comparisons traced to categorical concept functions.

    Propagate domains through assignments and collection mutation. Mixed-domain
    or reused noncategorical variables are conservatively left alone.
    Python's native comparison evaluation/short-circuiting stays intact.
    """
    origins = {}
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assignments.extend((t.id, node.value) for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            assignments.append((node.target.id, node.iter))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.attr in ('add', 'append', 'extend', 'update'):
                assignments.extend((node.func.value.id, arg) for arg in node.args)
    def domains(node):
        if isinstance(node, ast.Name):
            return origins.get(node.id, set())
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FUNCTION_DOMAINS:
                    return {FUNCTION_DOMAINS[node.func.id]}
                if node.func.id in ('set', 'list', 'tuple'):
                    return set().union(*(domains(arg) for arg in node.args))
            return {'noncategorical'}
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            return set().union(*(domains(item) for item in node.elts))
        if isinstance(node, ast.Constant):
            return {'literal'}
        if isinstance(node, (ast.BinOp, ast.Subscript)):
            return domains(node.left) | domains(node.right) if isinstance(node, ast.BinOp) else domains(node.value)
        return set()
    for _ in range(len(assignments) + 1):
        changed = False
        for name, value in assignments:
            new = origins.get(name, set()) | domains(value)
            if new != origins.get(name, set()):
                origins[name] = new
                changed = True
        if not changed:
            break
    class Comparisons(ast.NodeTransformer):
        def visit_Compare(self, node):
            self.generic_visit(node)
            operands = [node.left, *node.comparators]
            known = set().union(*(domains(item) for item in operands)) & set(FUNCTION_DOMAINS.values())
            # Raw literal operands are expected, but ambiguous observed variables
            # must not turn an entity-identity comparison into category equality.
            ambiguous = any('noncategorical' in domains(item) for item in operands)
            if len(known) == 1 and not ambiguous and not any(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops):
                domain = next(iter(known))
                wrapped = [ast.copy_location(ast.Call(func=ast.Name(id=helper_name, ctx=ast.Load()),
                    args=[item, ast.Constant(domain), ast.Constant(ast.unparse(item))], keywords=[]), item)
                    for item in operands]
                node.left, node.comparators = wrapped[0], wrapped[1:]
            return node
    return ast.fix_missing_locations(Comparisons().visit(tree))
