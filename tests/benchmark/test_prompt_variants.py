import copy
import csv
import json
import re
from collections import Counter

import pytest

from scripts.benchmark.generate_prompt_variants import (
    OUTPUT_NAME, display_name, entity_names, generate_prompts, load_cases, manifest_rows, write_prompts,
)
from scripts.benchmark.validate_prompt_variants import normalize, validate_equivalence, validate_prompts
from scripts.benchmark.validate_semantic_cases import BENCHMARK, load_data


@pytest.fixture(scope='module')
def context():
    cases = load_cases(); data = load_data()
    return cases, data, generate_prompts(cases, data=data)


def test_counts_ids_links_coverage_and_hidden_ids(context):
    cases, data, prompts = context
    report = validate_prompts(prompts, cases, data)
    assert len(cases) == 60 and len(prompts) == 180
    assert report['generalized_types_covered'] == 18 and report['structured_variants_covered'] == 66
    assert Counter(p['semantic_case_id'] for p in prompts) == {c['semantic_case_id']: 3 for c in cases}
    assert len({p['prompt_id'] for p in prompts}) == len({p['user_request'] for p in prompts}) == 180
    assert all(re.fullmatch(r'(EASY|MEDIUM|HARD|UNSOLVABLE)_\d{3}_V[123]', p['prompt_id']) for p in prompts)
    assert Counter(p['difficulty'] for p in prompts) == dict(easy=45, medium=45, hard=45, unsolvable=45)
    assert not any(re.search(r'\b(?:ATTR|REST)_\d+\b', p['user_request']) for p in prompts)
    assert any('ATTR_' in json.dumps(c) for c in cases)
    assert any('REST_' in json.dumps(c) for c in cases)
    events = [c['value']['value']['event_id'] for case in cases for c in case['constraints'] if c['value'].get('kind') == 'special_event']
    assert events == ['nyc_holiday_concert_2026_11_02']


def test_frozen_deterministic_regeneration(context, tmp_path):
    cases, data, prompts = context
    assert prompts == generate_prompts(cases, random_state=42, data=data)
    with pytest.raises(ValueError, match='random_state=42'): generate_prompts(cases, random_state=43, data=data)
    write_prompts(prompts, cases, tmp_path)
    for name in [OUTPUT_NAME, 'benchmark_manifest.csv']:
        assert (tmp_path / name).read_bytes() == (BENCHMARK / name).read_bytes()
    assert not (tmp_path / 'prompt_variants.jsonl').exists()
    assert cases == load_cases()


def test_entity_resolution_uses_canonical_data_and_normalized_names(context):
    cases, data, prompts = context; names = entity_names(data)
    lookup = {c['semantic_case_id']: c for c in cases}
    assert display_name('ATTR_2738', names) == 'High Rock Park'
    assert normalize(display_name('REST_0292', names)) == normalize('taïm Mediterranean Kitchen')
    with pytest.raises(ValueError, match='Cannot resolve'): display_name('ATTR_999999', names)
    changed = copy.deepcopy(next(p for p in prompts if 'High Rock Park' in p['user_request']))
    changed['user_request'] = changed['user_request'].replace('High Rock Park', 'HIGH ROCK PARK')
    validate_equivalence(changed, lookup[changed['semantic_case_id']], names)
    for p in prompts: validate_equivalence(p, lookup[p['semantic_case_id']], names)


def test_manifest_layers_and_metadata(context):
    cases, data, prompts = context
    rows = manifest_rows(prompts, cases); lookup = {c['semantic_case_id']: c for c in cases}
    required = {'prompt_id', 'semantic_case_id', 'difficulty', 'wording_variant', 'wording_style', 'user_request', 'expected_solvability'}
    for row in rows:
        assert required <= row.keys()
        case = lookup[row['semantic_case_id']]
        assert row['constraint_count'] == len(case['constraints'])
        assert row['category_count'] == case['metadata']['category_count']
        assert row['solvability_basis'] == case['metadata']['solvability_basis']
    with (BENCHMARK / 'semantic_case_manifest.csv').open(newline='') as f: semantic = list(csv.DictReader(f))
    with (BENCHMARK / 'benchmark_manifest.csv').open(newline='') as f: prompt_rows = list(csv.DictReader(f))
    assert len(semantic) == 60 and len(prompt_rows) == 180
    assert 'prompt_id' not in semantic[0] and 'prompt_id' in prompt_rows[0]
    assert Counter(r['solvability_basis'] for r in rows) == dict(assumed_full_domain_availability=111, validated_current_data=69)


@pytest.mark.parametrize('left,right', [('1500 metres', '1.5 km'), ('60 minutes', 'an hour'),
    ('USD 250', '$250'), ('$250.00', '$250'), ('18:00', '6pm'), ('12:00', 'noon'),
    ('2026-11-01T18:00:00-05:00', '6 pm on November 1, 2026'),
    ('6 pm on November 1, 2026', '6pm on November 1')])
def test_numeric_datetime_normalization(left, right):
    assert normalize(left) == normalize(right)


@pytest.mark.parametrize('before,after', [('1.5 km', '1500 metres'), ('60 minutes', 'an hour'),
    ('$250', 'USD 250'), ('6 pm on November 1, 2026', '6pm on November 1'),
    ('6 pm on November 1, 2026', '2026-11-01T18:00:00-05:00')])
def test_equivalent_surfaces_accepted(context, before, after):
    cases, data, prompts = context; names = entity_names(data)
    changed = copy.deepcopy(next(p for p in prompts if before in p['user_request']))
    changed['user_request'] = changed['user_request'].replace(before, after)
    case = next(c for c in cases if c['semantic_case_id'] == changed['semantic_case_id'])
    validate_equivalence(changed, case, names)


@pytest.mark.parametrize('mutation', ['duration', 'number', 'time', 'date', 'entity', 'exclusion',
    'hardness', 'softness', 'preference', 'omission', 'addition', 'orphan', 'id', 'style', 'label', 'duplicate', 'count', 'internal_id'])
def test_corruptions_rejected(context, mutation):
    cases, data, prompts = context; bad = copy.deepcopy(prompts)
    def find(fragment): return next(p for p in bad if fragment in p['user_request'])
    if mutation == 'duration': bad[0]['user_request'] = bad[0]['user_request'].replace('one-day', 'two-day')
    elif mutation == 'number':
        p = find('$250'); p['user_request'] = p['user_request'].replace('$250', '$251')
    elif mutation == 'time':
        p = find('8 am'); p['user_request'] = p['user_request'].replace('8 am', '9 am')
    elif mutation == 'date':
        p = find('November 1, 2026'); p['user_request'] = p['user_request'].replace('November 1, 2026', 'November 2, 2026')
    elif mutation == 'entity':
        p = find('High Rock Park'); p['user_request'] = p['user_request'].replace('High Rock Park', 'Central Park')
    elif mutation == 'exclusion':
        p = find('avoid eating at'); p['user_request'] = p['user_request'].replace('avoid eating at', 'eat at')
    elif mutation == 'hardness':
        p = find('Please arrive at JFK'); p['user_request'] = p['user_request'].replace('Please arrive at JFK', 'If possible, I would prefer to arrive at JFK')
    elif mutation == 'softness':
        p = find("If possible, I'd prefer"); p['user_request'] = p['user_request'].replace("If possible, I'd prefer", 'I require')
    elif mutation == 'preference':
        p = find('restaurants that feel quiet'); p['user_request'] = p['user_request'].replace('restaurants that feel quiet', 'restaurants that feel noisy')
    elif mutation == 'omission':
        p = find('Please arrive at JFK and use a nonstop flight.'); p['user_request'] = p['user_request'].replace(' and use a nonstop flight', '')
    elif mutation == 'addition': bad[0]['user_request'] += ' Require family-friendly restaurants.'
    elif mutation == 'orphan': bad[0]['semantic_case_id'] = 'SC_ORPHAN'
    elif mutation == 'id': bad[0]['prompt_id'] = 'INVALID'
    elif mutation == 'style': bad[0]['wording_style'] = 'conversational'
    elif mutation == 'label': bad[0]['expected_solvability'] = 'UNSOLVABLE'
    elif mutation == 'duplicate': bad[1]['user_request'] = bad[0]['user_request']
    elif mutation == 'count': bad.pop()
    elif mutation == 'internal_id': bad[0]['user_request'] += ' Visit ATTR_2738.'
    with pytest.raises(ValueError): validate_prompts(bad, cases, data)


def test_frozen_modality_annotations_cannot_change(context):
    cases, data, prompts = context
    for field, value in [('hardness', 'soft'), ('explicitness', 'implicit')]:
        bad = copy.deepcopy(cases); bad[0]['constraints'][0][field] = value
        with pytest.raises(ValueError, match='Frozen semantics'): validate_prompts(prompts, bad, data)
