"""Reproduce frozen naturalized wording plans against canonical semantic values."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from scripts.benchmark.validate_semantic_cases import BENCHMARK, MANIFEST_COLUMNS as CASE_COLUMNS, load_data, resolve_variant

PLAN_PATH = Path(__file__).parent / 'fixtures/naturalized_wording_plans.json'
STYLES = {'V1': 'concise/direct', 'V2': 'conversational', 'V3': 'detailed/persona-style'}
MANIFEST_COLUMNS = ['prompt_id', 'semantic_case_id', 'difficulty', 'wording_variant',
                    'wording_style', 'user_request', 'expected_solvability', 'trip_days'] + [
                    k for k in CASE_COLUMNS if k not in {'semantic_case_id', 'difficulty', 'trip_days', 'expected_solvability'}]
OUTPUT_NAME = 'prompt_variants_naturalized.jsonl'


def load_cases(path=BENCHMARK / 'semantic_cases.jsonl'):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def case_digest(case):
    return hashlib.sha256(json.dumps(case, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def entity_names(data):
    return {row[kind + '_id']: row['name'] for kind in ['restaurant', 'attraction']
            for row in data[kind + 's'].to_dict('records')}


def display_name(entity_id, names):
    if entity_id not in names: raise ValueError(f'Cannot resolve canonical entity ID: {entity_id}')
    name = names[entity_id]
    return name.title() if name.isupper() else name


def number(v):
    return str(int(v)) if isinstance(v, (int, float)) and v == int(v) else str(v)


def clock(value):
    hour, minute = map(int, value.split(':'))
    if hour == 12 and minute == 0: return 'noon'
    if hour == 0 and minute == 0: return 'midnight'
    return f"{hour % 12 or 12}{':' + str(minute).zfill(2) if minute else ''} {'am' if hour < 12 else 'pm'}"


def date_time(value):
    from datetime import datetime
    t = datetime.fromisoformat(value)
    return f"{clock(t.strftime('%H:%M'))} on {t.strftime('%B')} {t.day}, {t.year}"


def natural_phrase(c, names):
    """Semantic units rendered independently from frozen sentence/order plans."""
    key = resolve_variant(c)['legacy_constraint_type']; v = c['value'].get('value', True)
    name = lambda i: display_name(i, names)
    money = lambda x: f'${x:,.0f}' if float(x).is_integer() else f'${x:,.2f}'
    if key in {'trip_duration_days', 'number_of_travellers', 'traveller_type'}:
        return None  # Their frozen intro realizes duration/party context together.
    if key == 'required_departure_airport': return f'depart from {v}'
    if key == 'required_arrival_airport': return f'arrive at {v}'
    if key in {'departure_time_preference', 'arrival_time_preference'}:
        return f"{'depart' if key.startswith('departure') else 'arrive'} between {clock(v['start'])} and {clock(v['end'])}"
    if key == 'direct_flight_only': return 'use a nonstop flight' if v else 'allow connecting flights'
    if key == 'airline_preference': return f'fly with {v}'
    if key == 'accommodation_type': return f'stay in a {v}'
    if key == 'minimum_hotel_rating': return f'choose a hotel rated at least {number(v)} stars'
    if key == 'required_neighbourhood': return f"stay {'on the' if v == 'Upper West Side' else 'in'} {v}"
    if key == 'accommodation_amenity':
        return {'wifi': 'make sure the accommodation has Wi-Fi', 'breakfast': 'make sure breakfast is available at the accommodation',
                'gym': 'make sure the accommodation has a gym'}[v]
    if key in {'check_in_constraint', 'check_out_constraint'}: return f"check {'in' if key == 'check_in_constraint' else 'out'} at {date_time(v)}"
    if key == 'accommodation_budget_per_night': return f'keep accommodation at or below {money(v)}/night'
    if key == 'required_attraction': return 'visit ' + ' and '.join(name(i) for i in v)
    if key == 'excluded_attraction': return 'avoid visiting ' + ' and '.join(name(i) for i in v)
    if key == 'attraction_category': return f'include at least one {v} attraction'
    if key == 'avoid_attraction_category': return f'avoid {v} attractions'
    if key == 'minimum_attraction_rating': return f'choose attractions rated at least {number(v)} stars'
    if key == 'minimum_attraction_count': return f"visit at least {number(v)} attraction{'s' if v != 1 else ''}"
    if key == 'maximum_attraction_count': return f'visit no more than {number(v)} attractions'
    if key == 'dietary_requirement': return f'make all dining {v.replace("_", "-")}-compatible'
    if key in {'cuisine', 'excluded_cuisine'}:
        cuisine = 'diner-style' if v == 'diner' else v.title()
        return f"{'include' if key == 'cuisine' else 'avoid'} {cuisine} food"
    if key == 'minimum_restaurant_rating': return f'choose restaurants rated at least {number(v)} stars'
    if key == 'required_restaurant': return 'eat at ' + ' and '.join(name(i) for i in v)
    if key == 'avoid_restaurant': return 'avoid eating at ' + ' and '.join(name(i) for i in v)
    if key == 'meal_budget_per_person': return f'keep each meal at or below {money(v)} per person'
    if key == 'preferred_transport_mode': return 'use public transit for getting around' if v == 'transit' else f'travel by {v}'
    if key == 'avoid_transport_mode': return f'avoid travelling by {v}'
    if key in {'max_travel_time', 'max_walking_time'}:
        return f"keep each {'journey' if key == 'max_travel_time' else 'walking leg'} to {number(v)} minutes or less"
    if key == 'max_walking_distance': return f'keep each walking leg to {number(v / 1000)} km or less'
    if key == 'earliest_start_time': return f'start each day no earlier than {clock(v)}'
    if key == 'latest_end_time': return f'finish each day by {clock(v)}'
    if key in {'required_activity_time', 'meal_time_constraint'}:
        target = 'visit ' + name(v['entity_id']) if 'entity_id' in v else 'schedule ' + v['meal']
        return f"{target} on day {v['trip_day']} between {clock(v['window']['start'])} and {clock(v['window']['end'])}"
    if key == 'max_activities_per_day': return f'schedule no more than {number(v)} activities per day'
    if key == 'free_time_requirement': return f'leave at least {number(v)} minutes of free time each day'
    if key == 'buffer_time_requirement': return f'leave at least {number(v)} minutes between activities'
    budget = {'total_budget': 'the total trip budget', 'daily_budget': 'daily spending', 'food_budget': 'food spending for the whole trip',
              'attraction_budget': 'attraction spending for the whole trip', 'accommodation_budget': 'accommodation spending for the whole trip', 'flight_budget': 'the flight budget'}
    if key in budget: return f'keep {budget[key]} at or below {money(v)}'
    if c['category'] == 'subjective':
        target = c['value']['target']; attr = c['value']['attribute'].replace('_', ' ')
        if attr == 'crowdedness': return 'places that are less crowded'
        noun = {'restaurant': 'restaurants', 'attraction': 'attractions', 'itinerary': 'an itinerary'}[target]
        return f"{noun} that {'are' if attr == 'good for groups' else 'feel' if target != 'itinerary' else 'feels'} {attr}"
    if key == 'accessibility_requirement': return 'make the itinerary step-free'
    if key == 'weather_sensitive_preference': return 'avoid any plans that would involve being out in the rain'
    if key == 'indoor_only_preference': return 'keep all activities indoors'
    if key == 'avoid_repeated_categories': return 'use a different category for each attraction'
    if key == 'required_rest_period': return f'include a rest break of at least {number(v)} minutes'
    if key == 'special_event_requirement': return 'attend an NYC holiday concert on November 2, 2026'
    raise ValueError(f'No naturalization for {key}')


def generate_prompts(cases=None, random_state=42, data=None):
    if random_state != 42: raise ValueError('Frozen wording configuration requires random_state=42')
    cases = cases if cases is not None else load_cases(); names = entity_names(data if data is not None else load_data())
    plans = json.loads(PLAN_PATH.read_text()); lookup = {c['semantic_case_id']: c for c in cases}
    if set(lookup) != set(plans['case_digests']): raise ValueError('Frozen case set changed; review and refreeze wording plans')
    for key, case in lookup.items():
        if case_digest(case) != plans['case_digests'][key]: raise ValueError(f'Frozen semantics changed: {key}')
    prompts = []
    for plan in plans['prompts']:
        case = lookup[plan['semantic_case_id']]
        phrases = {c['constraint_id']: natural_phrase(c, names) for c in case['constraints']}
        text = plan['template'].format_map({k: v for k, v in phrases.items() if v is not None})
        prompts.append(dict(prompt_id=plan['prompt_id'], semantic_case_id=case['semantic_case_id'], difficulty=case['difficulty'],
                            wording_variant=plan['wording_variant'], wording_style=STYLES[plan['wording_variant']],
                            user_request=text, expected_solvability=case['expected_solvability']))
    return prompts


def manifest_rows(prompts, cases):
    from scripts.benchmark.validate_semantic_cases import manifest_rows as case_rows
    lookup = {c['semantic_case_id']: c for c in case_rows(cases)}
    return [{k: p[k] if k in p else lookup[p['semantic_case_id']][k] for k in MANIFEST_COLUMNS} for p in prompts]


def write_prompts(prompts, cases, output_dir=BENCHMARK):
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / OUTPUT_NAME).write_text(''.join(json.dumps(p, ensure_ascii=False, sort_keys=True) + '\n' for p in prompts), encoding='utf-8')
    with (output_dir / 'benchmark_manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_COLUMNS, lineterminator='\n'); writer.writeheader(); writer.writerows(manifest_rows(prompts, cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--random-state', type=int, default=42); parser.add_argument('--output-dir', type=Path, default=BENCHMARK)
    args = parser.parse_args(); cases = load_cases(); prompts = generate_prompts(cases, args.random_state)
    from scripts.benchmark.validate_prompt_variants import validate_prompts
    report = validate_prompts(prompts, cases); write_prompts(prompts, cases, args.output_dir); print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
