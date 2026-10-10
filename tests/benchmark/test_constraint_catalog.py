import copy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker
ROOT=Path(__file__).resolve().parents[2]
CATALOG=json.loads((ROOT/'data/benchmark/constraint_catalog.json').read_text())
SCHEMA=json.loads((ROOT/'data/benchmark/benchmark_schema.json').read_text())
ENTRIES=CATALOG['constraints']
CATEGORIES={'trip','flight','accommodation','attraction','food','transport','schedule','budget','subjective','other'}
OPERATORS={'eq','ne','gte','lte','in','not_in','include','exclude','between','prefer'}
VERIFICATION={'deterministic','llm_subjective','deterministic_plus_llm','unavailable_until_data_added'}
VALIDATOR=Draft202012Validator(SCHEMA,format_checker=FormatChecker())
VARIANTS=[(e,v) for e in ENTRIES for v in e['variants']]

def example_value(schema):
    if 'const' in schema:return schema['const']
    if '$ref' in schema:return example_value(SCHEMA['$defs']['values'][schema['$ref'].split('/')[-1]])
    if 'enum' in schema:return schema['enum'][0]
    if schema.get('format')=='date-time':return '2026-10-10T10:00:00-04:00'
    if schema.get('format')=='date':return '2026-10-10'
    kind=schema.get('type')
    if kind=='object':return {k:example_value(v) for k,v in schema['properties'].items()}
    if kind=='array':return [example_value(schema['items'])]
    if kind=='boolean':return True
    if kind in ['integer','number']:return max(1,schema.get('minimum',0))
    if 'pattern' in schema:
        if 'ATTR' in schema['pattern']:return 'ATTR_0001'
        if 'REST' in schema['pattern']:return 'REST_0001'
        if '[A-Z]' in schema['pattern']:return 'JFK'
        return '10:00'
    return 'example'

def fixture(branch):
    props=branch['properties'];constraint={k:props[k]['const'] for k in ['type','category','operator','verification']}
    constraint.update(constraint_id='C1',value=example_value(props['value']),hardness='hard',explicitness='explicit')
    variant=next(v for e,v in VARIANTS if e['constraint_type']==constraint['type'] and constraint['operator'] in v['allowed_operators'] and all(constraint['value'].get(k)==val for k,val in v['selector'].items()))
    metadata=dict(constraint_variants_present=[variant['legacy_constraint_type']],constraint_count=1,category_count=1,categories_present=[constraint['category']],constraint_types_present=[constraint['type']],subjective_constraint_count=int(constraint['category']=='subjective'),implicit_constraint_count=0,hard_constraint_count=1,soft_constraint_count=0,interaction_count=0)
    return dict(semantic_case_id='SC_TEST',difficulty='easy',expected_solvability='SOLVABLE',trip_days=1,constraints=[constraint],metadata=metadata)

def find_branch(legacy,op=None):
    family,variant=next((e,v) for e,v in VARIANTS if v['legacy_constraint_type']==legacy)
    for branch in SCHEMA['properties']['constraints']['items']['oneOf']:
        p=branch['properties'];selectors={k:v['const'] for k,v in p['value']['properties'].items() if k!='value'}
        if p['type']['const']==family['constraint_type'] and selectors==variant['selector'] and p['operator']['const'] in variant['allowed_operators'] and (op is None or p['operator']['const']==op):return branch
    raise AssertionError('Missing variant branch')

def test_family_catalog_unique_and_complete():
    assert len(ENTRIES)==18
    assert len({e['constraint_type'] for e in ENTRIES})==18
    assert set(CATALOG['categories'])==CATEGORIES
    assert set(CATALOG['operators'])==OPERATORS
    assert set(CATALOG['verification_types'])==VERIFICATION
    assert {e['category'] for e in ENTRIES}==CATEGORIES
    legacy=[v['legacy_constraint_type'] for _,v in VARIANTS]
    assert len(legacy)==len(set(legacy))==66
    assert CATALOG['legacy_type_mapping']=={v['legacy_constraint_type']:e['constraint_type'] for e,v in VARIANTS}
    for e in ENTRIES:
        assert e['category'] in CATEGORIES and e['value_type']=='object'
        assert set(e['allowed_operators'])=={o for v in e['variants'] for o in v['allowed_operators']}
        assert e['currently_supported']==any(v['currently_supported'] for v in e['variants'])
        assert set(e['verification_types'])=={v['verification_type'] for v in e['variants']}
        for v in e['variants']:
            assert v['category']==e['category'] and v['description'] and v['notes'] and v['selector']
            assert set(v['allowed_operators'])<=OPERATORS
            assert v['verification_type'] in VERIFICATION
            assert v['default_hardness'] in {'hard','soft'}

def test_support_preserved_per_variant():
    assert sum(v['currently_supported'] for _,v in VARIANTS)==37
    for e,v in VARIANTS:
        assert type(v['currently_supported']) is bool and v['data_source']
        if v['currently_supported']:
            assert v['verification_type']!='unavailable_until_data_added'
            assert all(s=='verifier-only' or (ROOT/'data/processed'/s).is_file() for s in v['data_source'])
        else:assert v['verification_type']=='unavailable_until_data_added'
        if e['category'] in {'flight','accommodation','transport','budget'} or v['legacy_constraint_type']=='minimum_attraction_rating':assert not v['currently_supported']
    attraction=next(e for e in ENTRIES if e['constraint_type']=='attraction_requirement')
    assert attraction['currently_supported']
    assert not next(v for v in attraction['variants'] if v['selector']=={'kind':'rating'})['currently_supported']

def test_other_closed_and_explicit():
    other=next(e for e in ENTRIES if e['constraint_type']=='other_requirement')
    assert len(other['variants'])==6
    assert all(v['value_type']!='string' for v in other['variants'])
    case=fixture(find_branch('accessibility_requirement'))
    case['constraints'][0]['value']={'kind':'arbitrary','value':'free text'}
    assert not VALIDATOR.is_valid(case)

def test_schema_synchronized():
    Draft202012Validator.check_schema(SCHEMA)
    c=SCHEMA['properties']['constraints']['items']
    assert set(c['properties']['type']['enum'])=={e['constraint_type'] for e in ENTRIES}
    for _,v in VARIANTS:
        for op in v['allowed_operators']:find_branch(v['legacy_constraint_type'],op)
    assert len({json.dumps(b,sort_keys=True) for b in c['oneOf']})==len(c['oneOf'])

@pytest.mark.parametrize('branch',SCHEMA['properties']['constraints']['items']['oneOf'])
def test_each_variant_operator_machine_validatable(branch):VALIDATOR.validate(fixture(branch))

@pytest.mark.parametrize('legacy,expected',[('required_attraction','include'),('excluded_attraction','exclude'),('attraction_category','include'),('avoid_attraction_category','exclude'),('dietary_requirement','include'),('excluded_cuisine','exclude')])
def test_include_exclude_meanings(legacy,expected):VALIDATOR.validate(fixture(find_branch(legacy,expected)))

def test_examples_and_optional_boolean_preference():
    case=fixture(find_branch('attraction_category','include'));case['constraints'][0]['value']={'kind':'category','value':'museum'};VALIDATOR.validate(case)
    case=fixture(find_branch('quiet_restaurant','prefer'));case['constraints'][0]['value']={'target':'restaurant','attribute':'quiet'};VALIDATOR.validate(case)
    case['constraints'][0]['value']['value']=False;VALIDATOR.validate(case)
    case['constraints'][0]['value']['target']='attraction';assert not VALIDATOR.is_valid(case)

def test_fixed_destination():
    assert CATALOG['destination']=='New York City'
    case=fixture(find_branch('trip_duration_days'))
    for field in ['destination','location']:
        bad=copy.deepcopy(case);bad[field]='Boston';assert not VALIDATOR.is_valid(bad)
        bad=copy.deepcopy(case);bad['metadata'][field]='Boston';assert not VALIDATOR.is_valid(bad)
    case=fixture(find_branch('required_arrival_airport','eq'));case['constraints'][0]['value']['value']='SFO';assert not VALIDATOR.is_valid(case)

def test_invalid_category_operator_value_verification():
    case=fixture(find_branch('trip_duration_days','eq'))
    for field,value in [('type','trip_duration_days'),('category','other'),('operator','include'),('value',3),('verification','llm_subjective'),('hardness','optional'),('explicitness','unknown')]:
        bad=copy.deepcopy(case);bad['constraints'][0][field]=value;assert not VALIDATOR.is_valid(bad)
    case=fixture(find_branch('minimum_attraction_rating'));case['constraints'][0]['verification']='deterministic';assert not VALIDATOR.is_valid(case)

def test_unsolvable_contract():
    case=fixture(find_branch('trip_duration_days'));case.update(difficulty='unsolvable',expected_solvability='UNSOLVABLE');assert not VALIDATOR.is_valid(case)
    case.update(unsat_reason='Inconsistent duration requirements',affected_constraint_ids=['C1']);VALIDATOR.validate(case)
    case['expected_solvability']='SOLVABLE';assert not VALIDATOR.is_valid(case)


def test_every_legacy_meaning_preserves_metadata_and_payload():
    contract=json.loads((Path(__file__).parent/'fixtures/legacy_semantics.json').read_text())
    assert set(contract)==set(CATALOG['legacy_type_mapping'])
    for _,variant in VARIANTS:
        old=contract[variant['legacy_constraint_type']]
        for field in ['category','value_type','default_hardness','verification_type','data_source','currently_supported','description','notes']:
            assert variant[field]==old[field]
        for old_op,value_schema in old['operator_value_schemas'].items():
            op={'contains':'include','excludes':'exclude'}.get(old_op,old_op)
            branch=find_branch(variant['legacy_constraint_type'],op)
            assert branch['properties']['value']['properties']['value']==value_schema
        assert set(variant['allowed_operators'])-{'prefer'}=={{'contains':'include','excludes':'exclude'}.get(o,o) for o in old['allowed_operators']}
