"""Validate semantic cases against the catalog, canonical data and evidence model."""
import argparse
import csv
import copy
import itertools
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / 'data/benchmark'
REASONS = {'unsupported_information', 'contradiction', 'no_feasible_entity',
           'impossible_budget', 'impossible_schedule'}
ASSUMED_CATEGORIES = {'flight', 'accommodation', 'transport', 'budget'}
AVAILABLE_FOR_BENCHMARK_DESIGN = 'AVAILABLE_FOR_BENCHMARK_DESIGN'
EXTENSION_FIELDS = {'benchmark_support_assumption', 'solvability_basis'}
INTERACTING_SCOPES = {frozenset(pair) for pair in [
    ('trip', 'schedule'), ('attraction', 'schedule'), ('food', 'schedule'),
    ('flight', 'accommodation'), ('flight', 'transport'), ('accommodation', 'transport'),
    *[('budget', category) for category in ['flight', 'accommodation', 'food', 'attraction', 'transport']]
]}


def benchmark_availability(variant):
    if variant['currently_supported']:
        return 'CURRENT_DATA'
    if variant['category'] in ASSUMED_CATEGORIES:
        return AVAILABLE_FOR_BENCHMARK_DESIGN
    return 'UNAVAILABLE'


MANIFEST_COLUMNS = ['semantic_case_id', 'difficulty', 'trip_days', 'expected_solvability',
                    'constraint_count', 'category_count', 'subjective_constraint_count',
                    'implicit_constraint_count', 'hard_constraint_count', 'soft_constraint_count',
                    'interaction_count', 'unsat_reason', 'benchmark_support_assumption', 'solvability_basis',
                    'categories_present', 'constraint_types_present', 'constraint_variants_present',
                    'category_distribution', 'type_distribution', 'variant_distribution']


def load_catalog():
    return json.loads((BENCHMARK / 'constraint_catalog.json').read_text())


def resolve_variant(constraint, catalog=None):
    matches = [v for e in (catalog or load_catalog())['constraints']
               if e['constraint_type'] == constraint['type']
               for v in e['variants'] if constraint['operator'] in v['allowed_operators']
               and all(constraint['value'].get(k) == value for k, value in v['selector'].items())]
    if len(matches) != 1:
        raise ValueError('Unknown or ambiguous structured variant')
    return matches[0]


def scope(c):
    # A subjective preference interacts with its target, not an unrelated preference.
    if c['category'] == 'subjective':
        return {'restaurant': 'food', 'attraction': 'attraction',
                'place': 'attraction', 'itinerary': 'schedule'}[c['value']['target']]
    return c['category']


def metadata(constraints, catalog=None, benchmark_design=False):
    categories = sorted({c['category'] for c in constraints})
    result = dict(constraint_count=len(constraints), category_count=len(categories),
                categories_present=categories,
                constraint_types_present=sorted({c['type'] for c in constraints}),
                constraint_variants_present=sorted({resolve_variant(c, catalog)['legacy_constraint_type'] for c in constraints}),
                subjective_constraint_count=sum(c['verification'] in {'llm_subjective', 'deterministic_plus_llm'} for c in constraints),
                implicit_constraint_count=sum(c['explicitness'] == 'implicit' for c in constraints),
                hard_constraint_count=sum(c['hardness'] == 'hard' for c in constraints),
                soft_constraint_count=sum(c['hardness'] == 'soft' for c in constraints),
                interaction_count=sum(scope(a) == scope(b) or frozenset([scope(a), scope(b)]) in INTERACTING_SCOPES
                                      for a, b in itertools.combinations(constraints, 2)))
    if benchmark_design:
        assumed = any(benchmark_availability(resolve_variant(c, catalog)) == AVAILABLE_FOR_BENCHMARK_DESIGN for c in constraints)
        result.update(benchmark_support_assumption=assumed,
                      solvability_basis='assumed_full_domain_availability' if assumed else 'validated_current_data')
    return result


def signature(case):
    def normalize(v):
        if isinstance(v, list):
            return sorted((normalize(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
        if isinstance(v, dict):
            return {k: normalize(x) for k, x in v.items()}
        return v
    items = []
    for c in case['constraints']:
        value = normalize(c['value'])
        op = c['operator']
        if op == 'prefer':
            op = 'eq'
            if c['category'] == 'subjective' and value['attribute'] != 'crowdedness':
                value.setdefault('value', True)
        items.append(json.dumps(dict(type=c['type'], operator=op, value=value,
                                    hardness=c['hardness']), sort_keys=True))
    return json.dumps([case['trip_days'], sorted(items)])


def load_data():
    return {name: pd.read_csv(ROOT / 'data/processed' / f'{name}.csv').fillna('')
            for name in ['restaurants', 'attractions', 'restaurant_reviews', 'attraction_reviews']}


def cuisines(row):
    return json.loads(row['cuisine']) if row['cuisine'] else []


def numeric_match(value, operator, target):
    return {'eq': lambda: value == target, 'gte': lambda: value >= target,
            'lte': lambda: value <= target, 'between': lambda: target['min'] <= value <= target['max']}[operator]()


def minutes(value):
    hour, minute = map(int, value.split(':'))
    return 60 * hour + minute



def design_contradiction(resolved):
    """Check singleton/choice and exclusion consistency; no invented domain rows.

    A logical contradiction remains invalid even when the evidence domain is assumed.
    Flight/hotel prices and routing feasibility are deliberately not asserted here.
    """
    selections = {}
    selection_ids = {}
    forbidden = {}
    forbidden_ids = {}
    for c, legacy in resolved:
        if c['category'] not in ASSUMED_CATEGORIES:
            continue
        key = (c['type'], c['value']['kind'])
        # preferred/avoided mode are variants sharing a single selection scope.
        value = c['value']['value']; operator = c['operator']
        if operator in {'eq', 'in'}:
            options = value if operator == 'in' else [value]
            options = {json.dumps(v, sort_keys=True) for v in options}
            selections[key] = selections.get(key, options) & options
            selection_ids.setdefault(key, []).append(c['constraint_id'])
        elif operator in {'ne', 'not_in'}:
            options = value if operator == 'not_in' else [value]
            forbidden.setdefault(key, set()).update(json.dumps(v, sort_keys=True) for v in options)
            forbidden_ids.setdefault(key, []).append(c['constraint_id'])
    for key, options in selections.items():
        if not options - forbidden.get(key, set()):
            return selection_ids[key] + forbidden_ids.get(key, [])
    amenities = [(c, legacy) for c, legacy in resolved if legacy == 'accommodation_amenity']
    for (a, _), (b, _) in itertools.combinations(amenities, 2):
        if a['operator'] != b['operator'] and a['value']['value'] == b['value']['value']:
            return [a['constraint_id'], b['constraint_id']]
    return []

def feasibility(case, data, catalog=None):
    """Return a verified failure and its involved IDs, or hard-feasibility witnesses.

    Restaurant requirements share one dining-selection scope. Attraction inclusions
    require visits collectively. No route, opening-hour or subjective truth is inferred.
    """
    hard = [c for c in case['constraints'] if c['hardness'] == 'hard']
    resolved = [(c, resolve_variant(c, catalog)['legacy_constraint_type']) for c in hard]
    assumed = case['metadata'].get('benchmark_support_assumption', False)
    unsupported = [c['constraint_id'] for c in hard if not resolve_variant(c, catalog)['currently_supported']
                   and not (assumed and benchmark_availability(resolve_variant(c, catalog)) == AVAILABLE_FOR_BENCHMARK_DESIGN)]
    if unsupported:
        return 'unsupported_information', unsupported, {}
    conflict = design_contradiction(resolved)
    if conflict:
        return 'contradiction', conflict, {}
    for kind in ['restaurant', 'attraction']:
        includes = [(c, set(c['value']['value'])) for c, v in resolved if v == f'required_{kind}']
        excludes = [(c, set(c['value']['value'])) for c, v in resolved if v == ('avoid_restaurant' if kind == 'restaurant' else 'excluded_attraction')]
        for (a, x), (b, y) in itertools.product(includes, excludes):
            if x & y:
                return 'contradiction', [a['constraint_id'], b['constraint_id']], {}
    low, high = 0, len(data['attractions'])
    count_ids = []
    for c, v in resolved:
        if v in {'minimum_attraction_count', 'maximum_attraction_count'}:
            count_ids.append(c['constraint_id'])
            if v == 'minimum_attraction_count': low = max(low, c['value']['value'])
            else: high = min(high, c['value']['value'])
    if low > high:
        return 'contradiction', count_ids, {}
    restaurants = data['restaurants'].to_dict('records')
    # Fixed NYC scope: NJ entries retained in the frozen source are not witnesses.
    restaurants = [r for r in restaurants if ', NY ' in r['address'] or ', New York ' in r['address']]
    food_constraints = [(c, v) for c, v in resolved if c['category'] == 'food']
    for c, v in food_constraints:
        t, op = c['value']['value'], c['operator']
        if v == 'required_restaurant': restaurants = [r for r in restaurants if r['restaurant_id'] in t]
        elif v == 'avoid_restaurant': restaurants = [r for r in restaurants if r['restaurant_id'] not in t]
        elif v == 'dietary_requirement': restaurants = [r for r in restaurants if r[f'diet_{t}'] == 'yes']
        elif v in {'cuisine', 'excluded_cuisine'}:
            choices = t if isinstance(t, list) else [t]
            restaurants = [r for r in restaurants if (bool(set(cuisines(r)) & set(choices)) if v == 'cuisine'
                           else bool(cuisines(r)) and not set(cuisines(r)) & set(choices))]
        elif v == 'minimum_restaurant_rating': restaurants = [r for r in restaurants if r['rating'] != '' and float(r['rating']) >= t]
    if food_constraints and not restaurants:
        return 'no_feasible_entity', [c['constraint_id'] for c, v in food_constraints if v != 'meal_budget_per_person'], {}
    for c, v in food_constraints:
        if v == 'meal_budget_per_person':
            t = c['value']['value']; cap = t['max'] if isinstance(t, dict) else t
            # A complete bounded source interval must fit the requested range.
            affordable = [r for r in restaurants if r['price_max'] != '' and float(r['price_max']) <= cap
                          and (not isinstance(t, dict) or float(r['price_min']) >= t['min'])]
            if not affordable:
                # Prove budget failure only with known lower bounds for every candidate.
                if restaurants and all(r['price_min'] != '' and float(r['price_min']) > cap for r in restaurants):
                    return 'impossible_budget', [x['constraint_id'] for x, _ in food_constraints], {}
                return 'no_feasible_entity', [x['constraint_id'] for x, _ in food_constraints], {}
            restaurants = affordable
    attractions = data['attractions'].to_dict('records')
    attraction_constraints = [(c, v) for c, v in resolved if c['category'] == 'attraction']
    for c, v in attraction_constraints:
        t = c['value']['value']
        if v == 'excluded_attraction': attractions = [a for a in attractions if a['attraction_id'] not in t]
        elif v == 'avoid_attraction_category': attractions = [a for a in attractions if a['category'] not in (t if isinstance(t, list) else [t])]
    available = {a['attraction_id'] for a in attractions}
    required = set()
    required_categories = set()
    for c, v in attraction_constraints:
        if v == 'required_attraction': required.update(c['value']['value'])
        if v == 'attraction_category':
            t = c['value']['value']; required_categories.update(t if isinstance(t, list) else [t])
    if not required <= available or not required_categories <= {a['category'] for a in attractions} or low > len(available) or len(required) > high:
        return 'no_feasible_entity', [c['constraint_id'] for c, _ in attraction_constraints], {}
    selected = [a for a in attractions if a['attraction_id'] in required]
    for category in sorted(required_categories):
        if not any(a['category'] == category for a in selected):
            selected.append(next(a for a in attractions if a['category'] == category))
    repeat_rule = any(v == 'avoid_repeated_categories' and c['value']['value'] for c, v in resolved)
    if repeat_rule and len({a['category'] for a in selected}) < len(selected):
        return 'no_feasible_entity', [c['constraint_id'] for c, v in resolved if c['category'] in {'other', 'attraction'}], {}
    for a in attractions:
        if len(selected) >= max(low, len(required_categories), len(required)): break
        if a not in selected and (not repeat_rule or a['category'] not in {x['category'] for x in selected}): selected.append(a)
    if len(selected) < low or len(selected) > high:
        return 'no_feasible_entity', [c['constraint_id'] for c, _ in attraction_constraints], {}
    start, end = 0, 1440
    schedule = [(c, v) for c, v in resolved if c['category'] == 'schedule' or v == 'required_rest_period']
    for c, v in schedule:
        if v == 'earliest_start_time': start = max(start, minutes(c['value']['value']))
        elif v == 'latest_end_time': end = min(end, minutes(c['value']['value']))
    capacity = None
    rest = free = buffer = 0
    windows = []
    for c, v in schedule:
        t = c['value']['value']
        if v == 'max_activities_per_day': capacity = t if capacity is None else min(capacity, t)
        elif v == 'required_rest_period': rest = max(rest, t)
        elif v == 'free_time_requirement': free = max(free, t)
        elif v == 'buffer_time_requirement': buffer = max(buffer, t)
        elif v in {'required_activity_time', 'meal_time_constraint'}: windows.append(t)
    invalid = start >= end or max(rest, free) + max(0, len(selected) - 1) * buffer > end - start
    invalid |= capacity is not None and len(selected) > capacity * case['trip_days']
    invalid |= any(minutes(w['window']['start']) < start or minutes(w['window']['end']) > end for w in windows)
    if invalid:
        return 'impossible_schedule', [c['constraint_id'] for c, _ in schedule] + [c['constraint_id'] for c, v in attraction_constraints if v == 'minimum_attraction_count'], {}
    return None, [], {'restaurant_ids': [r['restaurant_id'] for r in restaurants],
                      'attraction_ids': [a['attraction_id'] for a in selected]}


def validate_cases(cases, data=None, require_coverage=True):
    catalog = load_catalog(); data = data or load_data()
    schema = json.loads((BENCHMARK / 'benchmark_schema.json').read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    ids, signatures = set(), set()
    for case in cases:
        # The strict existing schema is unchanged. Validate its core projection
        # and separately validate the closed benchmark-design metadata extension.
        core = copy.deepcopy(case)
        extension = {k: core['metadata'].pop(k) for k in EXTENSION_FIELDS if k in core['metadata']}
        if extension:
            Draft202012Validator({'type': 'object', 'additionalProperties': False,
                'required': sorted(EXTENSION_FIELDS), 'properties': {
                    'benchmark_support_assumption': {'type': 'boolean'},
                    'solvability_basis': {'enum': ['assumed_full_domain_availability', 'validated_current_data']}}}).validate(extension)
        validator.validate(core)
        if case['semantic_case_id'] in ids or signature(case) in signatures: raise ValueError('Duplicate semantic case/set')
        ids.add(case['semantic_case_id']); signatures.add(signature(case))
        constraints = case['constraints']; constraint_ids = [c['constraint_id'] for c in constraints]
        if len(set(constraint_ids)) != len(constraint_ids): raise ValueError('Duplicate constraint ID')
        if case['metadata'] != metadata(constraints, catalog, benchmark_design=bool(extension)): raise ValueError('Incorrect metadata')
        for c in constraints:
            variant = resolve_variant(c, catalog); v = c['value'].get('value', True)
            if case['expected_solvability'] == 'SOLVABLE' and not variant['currently_supported'] and not (extension.get('benchmark_support_assumption') and benchmark_availability(variant) == AVAILABLE_FOR_BENCHMARK_DESIGN): raise ValueError('Unsupported solvable variant')
            if variant['legacy_constraint_type'] == 'trip_duration_days' and not numeric_match(case['trip_days'], c['operator'], v): raise ValueError('Inconsistent trip duration')
            if isinstance(v, dict):
                if 'min' in v and v['min'] > v['max']: raise ValueError('Reversed bounds')
                window = v.get('window', v)
                if 'start' in window and window['start'] >= window['end']: raise ValueError('Reversed time window')
                if 'trip_day' in v and v['trip_day'] > case['trip_days']: raise ValueError('Invalid trip day')
                if 'entity_id' in v:
                    table = data[v['entity_type'] + 's']; column = v['entity_type'] + '_id'
                    if v['entity_id'] not in set(table[column]): raise ValueError('Unknown scheduled entity')
            if c['value'].get('kind') == 'entity':
                kind = 'restaurant' if c['category'] == 'food' else 'attraction'
                if not set(v) <= set(data[kind + 's'][kind + '_id']): raise ValueError('Unknown named entity')
        reason, affected, _ = feasibility(case, data, catalog)
        if case['expected_solvability'] == 'SOLVABLE':
            if reason: raise ValueError(f"Infeasible solvable case {case['semantic_case_id']}: {reason}")
        else:
            requested = case['affected_constraint_ids']
            if case['unsat_reason'] not in REASONS or reason != case['unsat_reason']: raise ValueError('Unverified unsat reason')
            if not set(requested) <= set(constraint_ids) or set(requested) != set(affected): raise ValueError('Invalid affected constraints')
    if require_coverage:
        if len(cases) != 60 or Counter(c['difficulty'] for c in cases) != Counter(dict(easy=15, medium=15, hard=15, unsolvable=15)): raise ValueError('Incorrect difficulty counts')
        supported = {v['legacy_constraint_type'] for e in catalog['constraints'] for v in e['variants'] if v['currently_supported']}
        covered = {v for c in cases if c['expected_solvability'] == 'SOLVABLE' for v in c['metadata']['constraint_variants_present']}
        design = any(c['metadata'].get('benchmark_support_assumption') for c in cases)
        if design:
            supported |= {v['legacy_constraint_type'] for e in catalog['constraints'] for v in e['variants']
                          if benchmark_availability(v) == AVAILABLE_FOR_BENCHMARK_DESIGN}
        if not supported <= covered: raise ValueError(f'Missing supported/design variants: {supported - covered}')
    return coverage(cases, catalog)


def coverage(cases, catalog=None):
    catalog = catalog or load_catalog()
    cs = [x for case in cases for x in case['constraints']]
    variants = Counter(resolve_variant(c, catalog)['legacy_constraint_type'] for c in cs)
    supported = {v['legacy_constraint_type'] for e in catalog['constraints'] for v in e['variants'] if v['currently_supported']}
    return dict(case_count=len(cases), difficulty=dict(Counter(c['difficulty'] for c in cases)),
                types=dict(sorted(Counter(c['type'] for c in cs).items())), variants=dict(sorted(variants.items())),
                supported_variants_without_coverage=sorted(supported - variants.keys()),
                hardness=dict(Counter(c['hardness'] for c in cs)), explicitness=dict(Counter(c['explicitness'] for c in cs)),
                verification=dict(Counter(c['verification'] for c in cs)),
                categories=dict(Counter(c['category'] for c in cs)),
                solvability_basis=dict(Counter(c['metadata'].get('solvability_basis', 'validated_current_data') for c in cases)),
                benchmark_availability=dict(Counter(benchmark_availability(resolve_variant(c, catalog)) for c in cs)),
                design_variants_without_coverage=sorted({v['legacy_constraint_type'] for e in catalog['constraints'] for v in e['variants']
                    if benchmark_availability(v) == AVAILABLE_FOR_BENCHMARK_DESIGN} - variants.keys()),
                assumed_availability_case_count=sum(c['metadata'].get('benchmark_support_assumption', False) for c in cases),
                category_case_counts=dict(Counter(cat for c in cases for cat in c['metadata']['categories_present'])),
                unsat_reasons=dict(Counter(c['unsat_reason'] for c in cases if 'unsat_reason' in c)))


def manifest_rows(cases):
    rows = []
    for c in cases:
        row = {}
        for k in MANIFEST_COLUMNS:
            if k in {'category_distribution', 'type_distribution', 'variant_distribution'}:
                field = {'category_distribution': 'category', 'type_distribution': 'type'}.get(k)
                value = dict(Counter(x[field] if field else resolve_variant(x)['legacy_constraint_type']
                                     for x in c['constraints']))
            else:
                value = c.get(k, c['metadata'].get(k, ''))
            row[k] = json.dumps(value, sort_keys=True, separators=(',', ':')) if isinstance(value, (dict, list, bool)) else value
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=BENCHMARK / 'semantic_cases.jsonl')
    parser.add_argument('--manifest', type=Path, default=BENCHMARK / 'semantic_case_manifest.csv')
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    result = validate_cases(cases)
    with args.manifest.open(newline='') as stream: actual = list(csv.DictReader(stream))
    expected = [{k: str(v) for k, v in row.items()} for row in manifest_rows(cases)]
    if actual != expected: raise ValueError('Manifest differs from cases')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
