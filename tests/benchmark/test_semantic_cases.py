import copy
import json
from collections import Counter

import pytest
from jsonschema.exceptions import ValidationError

from scripts.benchmark.generate_semantic_cases import generate_cases, write_cases
from scripts.benchmark.validate_semantic_cases import (
    BENCHMARK, AVAILABLE_FOR_BENCHMARK_DESIGN, benchmark_availability, feasibility, load_catalog, load_data, metadata, resolve_variant,
    signature, validate_cases,
)


@pytest.fixture(scope='module')
def data():
    return load_data()


@pytest.fixture(scope='module')
def cases(data):
    return generate_cases(data=data)


def test_deterministic_generation_and_reproducibility(cases, data, tmp_path):
    assert cases == generate_cases(random_state=42, data=data)
    assert cases != generate_cases(random_state=43, data=data)
    write_cases(cases, tmp_path)
    for name in ['semantic_cases.jsonl', 'semantic_case_manifest.csv']:
        assert (tmp_path / name).read_bytes() == (BENCHMARK / name).read_bytes()


def test_counts_unique_semantics_and_metadata(cases, data):
    assert len(cases) == 60
    assert Counter(c['difficulty'] for c in cases) == dict(easy=15, medium=15, hard=15, unsolvable=15)
    assert len({signature(c) for c in cases}) == 60
    for c in cases:
        assert c['metadata'] == metadata(c['constraints'], benchmark_design=True)
        reason, affected, witness = feasibility(c, data)
        if c['expected_solvability'] == 'SOLVABLE':
            assert reason is None
            assert witness['restaurant_ids']
        else:
            assert reason == c['unsat_reason']
            assert affected == c['affected_constraint_ids']
    validate_cases(cases, data)


def test_supported_family_and_variant_coverage(cases):
    catalog = load_catalog()
    supported = {v['legacy_constraint_type'] for e in catalog['constraints'] for v in e['variants'] if v['currently_supported']}
    supported_types = {e['constraint_type'] for e in catalog['constraints'] if e['currently_supported']}
    solvable = [c for c in cases if c['expected_solvability'] == 'SOLVABLE']
    assert supported <= {v for c in solvable for v in c['metadata']['constraint_variants_present']}
    assert supported_types <= {t for c in solvable for t in c['metadata']['constraint_types_present']}
    for case in solvable:
        assert all(benchmark_availability(resolve_variant(c)) != 'UNAVAILABLE' for c in case['constraints'])
    category_cases = Counter(cat for c in cases for cat in c['metadata']['categories_present'])
    assert set(category_cases) == set(catalog['categories'])
    assert min(category_cases.values()) >= 2


def test_named_and_scheduled_referential_integrity(cases, data):
    for case in cases:
        for c in case['constraints']:
            v = c['value'].get('value')
            if c['value'].get('kind') == 'entity':
                kind = 'restaurant' if c['category'] == 'food' else 'attraction'
                assert set(v) <= set(data[kind + 's'][kind + '_id'])
            if isinstance(v, dict) and 'entity_id' in v:
                assert v['entity_id'] in set(data[v['entity_type'] + 's'][v['entity_type'] + '_id'])


@pytest.mark.parametrize('mutation', ['metadata', 'duration', 'duplicate', 'unknown_entity', 'unknown_type', 'unknown_variant', 'operator', 'unsat_reason', 'affected', 'unsupported'])
def test_invalid_cases_rejected(cases, data, mutation):
    bad = copy.deepcopy(cases)
    if mutation == 'metadata': bad[0]['metadata']['constraint_count'] += 1
    elif mutation == 'duration': bad[0]['trip_days'] += 1
    elif mutation == 'duplicate': bad[1] = copy.deepcopy(bad[0]); bad[1]['semantic_case_id'] = 'OTHER'
    elif mutation == 'unknown_entity':
        c = next(c for case in bad for c in case['constraints'] if c['value'].get('kind') == 'entity' and c['category'] == 'attraction')
        c['value']['value'] = ['ATTR_999999']
    elif mutation == 'unknown_type': bad[0]['constraints'][0]['type'] = 'unknown'
    elif mutation == 'unknown_variant': bad[0]['constraints'][0]['value']['kind'] = 'unknown'
    elif mutation == 'operator': bad[0]['constraints'][0]['operator'] = 'exclude'
    elif mutation == 'unsat_reason': bad[-1]['unsat_reason'] = 'contradiction'
    elif mutation == 'affected': bad[-1]['affected_constraint_ids'] = ['NONEXISTENT']
    elif mutation == 'unsupported':
        c = copy.deepcopy(bad[45]['constraints'][1]); c['constraint_id'] = 'C02'
        bad[0]['constraints'].append(c); bad[0]['metadata'] = metadata(bad[0]['constraints'], benchmark_design=True)
    with pytest.raises((ValueError, ValidationError)):
        validate_cases(bad, data)


def test_duplicate_signature_ignores_presentation(cases):
    altered = copy.deepcopy(cases[30])
    altered['constraints'].reverse()
    for c in altered['constraints']:
        c['constraint_id'] = 'different'; c['explicitness'] = 'explicit'
    assert signature(altered) == signature(cases[30])


def test_interaction_count_simple_pairs():
    def c(category):
        return {'category': category}
    from scripts.benchmark.validate_semantic_cases import scope
    assert scope(c('food')) == 'food'
    case = json.loads((BENCHMARK / 'semantic_cases.jsonl').read_text().splitlines()[14])
    assert case['metadata']['interaction_count'] == 1


def test_all_generalized_types_and_planned_variants_covered(cases):
    catalog = load_catalog()
    solvable = [c for c in cases if c['expected_solvability'] == 'SOLVABLE']
    assert {e['constraint_type'] for e in catalog['constraints']} <= {
        t for c in solvable for t in c['metadata']['constraint_types_present']}
    planned = {v['legacy_constraint_type'] for e in catalog['constraints'] for v in e['variants']
               if benchmark_availability(v) == AVAILABLE_FOR_BENCHMARK_DESIGN}
    assert planned <= {v for c in solvable for v in c['metadata']['constraint_variants_present']}
    for category in ['flight', 'accommodation', 'transport', 'budget']:
        assert sum(category in c['metadata']['categories_present'] for c in solvable) >= 10
    for e in catalog['constraints']:
        if e['category'] in {'flight', 'accommodation', 'transport', 'budget'}:
            assert all(not v['currently_supported'] for v in e['variants'])


def test_assumed_support_metadata_and_cross_category_cases(cases):
    for case in cases:
        assumed = any(benchmark_availability(resolve_variant(c)) == AVAILABLE_FOR_BENCHMARK_DESIGN
                      for c in case['constraints'])
        assert case['metadata']['benchmark_support_assumption'] == assumed
        assert case['metadata']['solvability_basis'] == (
            'assumed_full_domain_availability' if assumed else 'validated_current_data')
        # Preserve actual availability/verification declarations in constraints.
        for c in case['constraints']:
            assert c['verification'] == resolve_variant(c)['verification_type']
    categories = [set(c['metadata']['categories_present']) for c in cases if c['expected_solvability'] == 'SOLVABLE']
    for combination in [{'flight', 'accommodation', 'budget'}, {'accommodation', 'attraction', 'transport'},
                        {'attraction', 'food', 'schedule'}, {'flight', 'accommodation', 'food', 'transport', 'schedule'}]:
        assert any(combination <= cats for cats in categories)
    assert any({'flight_budget', 'accommodation_budget', 'food_budget', 'attraction_budget'} <=
               set(c['metadata']['constraint_variants_present']) for c in cases)


@pytest.mark.parametrize('field,value', [('benchmark_support_assumption', False),
                                        ('benchmark_support_assumption', 'true'),
                                        ('solvability_basis', 'validated_current_data'),
                                        ('solvability_basis', 'implemented')])
def test_misleading_assumption_metadata_rejected(cases, data, field, value):
    bad = copy.deepcopy(next(c for c in cases if c['metadata']['benchmark_support_assumption']))
    bad['metadata'][field] = value
    with pytest.raises((ValueError, ValidationError)):
        validate_cases([bad], data, require_coverage=False)


def test_unavailable_failures_are_not_assumed_domains(cases):
    unavailable = [c for c in cases if c.get('unsat_reason') == 'unsupported_information']
    assert len(unavailable) == 3
    for case in unavailable:
        assert not case['metadata']['benchmark_support_assumption']
        assert all(resolve_variant(c)['category'] not in {'flight', 'accommodation', 'transport', 'budget'}
                   for c in case['constraints'] if c['constraint_id'] in case['affected_constraint_ids'])


def test_conflicting_future_placeholders_rejected(cases, data):
    bad = copy.deepcopy(cases[8])
    preferred = next(c for c in bad['constraints'] if c['type'] == 'transport_requirement')
    excluded = copy.deepcopy(preferred)
    excluded.update(constraint_id='C99', operator='ne')
    bad['constraints'].append(excluded)
    bad['metadata'] = metadata(bad['constraints'], benchmark_design=True)
    reason, affected, _ = feasibility(bad, data)
    assert reason == 'contradiction'
    assert set(affected) == {preferred['constraint_id'], 'C99'}
    with pytest.raises(ValueError, match='Infeasible solvable'):
        validate_cases([bad], data, require_coverage=False)


def test_metadata_extension_does_not_allow_arbitrary_fields(cases, data):
    bad = copy.deepcopy(cases[0])
    bad['metadata']['made_up_field'] = True
    with pytest.raises(ValidationError):
        validate_cases([bad], data, require_coverage=False)


def test_missing_extension_field_rejected(cases, data):
    bad = copy.deepcopy(cases[2])
    del bad['metadata']['solvability_basis']
    with pytest.raises(ValidationError):
        validate_cases([bad], data, require_coverage=False)


def test_manifest_distributions_match_case_occurrences(cases):
    from scripts.benchmark.validate_semantic_cases import coverage, manifest_rows
    rows = manifest_rows(cases)
    report = coverage(cases)
    for column, key in [('category_distribution', 'categories'), ('type_distribution', 'types'),
                        ('variant_distribution', 'variants')]:
        total = Counter()
        for row in rows:
            total.update(json.loads(row[column]))
        assert dict(total) == report[key]
    assert Counter(row['solvability_basis'] for row in rows) == report['solvability_basis']
    assert sum(row['benchmark_support_assumption'] == 'true' for row in rows) == report['assumed_availability_case_count']
