"""Generate structured NYC semantic cases only; never generate prompt variants."""
import argparse
import csv
import json
import random
from pathlib import Path

from scripts.benchmark.validate_semantic_cases import (
    BENCHMARK, MANIFEST_COLUMNS, cuisines, feasibility, load_catalog, load_data,
    manifest_rows, metadata, validate_cases,
)


def generate_cases(random_state=42, data=None):
    rng = random.Random(random_state)
    catalog = load_catalog(); data = data or load_data()
    variants = {v['legacy_constraint_type']: (e, v) for e in catalog['constraints'] for v in e['variants']}
    restaurants = sorted((r for r in data['restaurants'].to_dict('records')
                          if ', NY ' in r['address'] and r['price_max'] != ''), key=lambda r: r['restaurant_id'])
    attractions = sorted(data['attractions'].to_dict('records'), key=lambda a: a['attraction_id'])
    rng.shuffle(restaurants); rng.shuffle(attractions)
    reviewed_restaurants = set(data['restaurant_reviews']['restaurant_id'])
    reviewed_attractions = set(data['attraction_reviews']['attraction_id'])
    tagged = next(r for r in restaurants if r['diet_vegetarian'] == 'yes' and r['restaurant_id'] in reviewed_restaurants)
    culinary = [r for r in restaurants if cuisines(r) and r['restaurant_id'] in reviewed_restaurants]
    reviewed_places = [a for a in attractions if a['attraction_id'] in reviewed_attractions]
    subjective = [v for v in variants if variants[v][0]['constraint_type'] == 'subjective_preference']
    cases = []

    def constraint(legacy, value, operator=None, softness=False, implicit=False):
        family, variant = variants[legacy]
        if operator is None: operator = variant['allowed_operators'][0]
        return dict(type=family['constraint_type'], category=family['category'], operator=operator,
                    value={**variant['selector'], 'value': value},
                    hardness='soft' if softness else 'hard', explicitness='implicit' if implicit else 'explicit',
                    verification=variant['verification_type'])

    def add(difficulty, days, constraints):
        index = len(cases) + 1
        for j, c in enumerate(constraints, 1): c['constraint_id'] = f'C{j:02d}'
        case = dict(semantic_case_id=f'SC_{index:03d}', difficulty=difficulty, trip_days=days,
                    expected_solvability='UNSOLVABLE' if difficulty == 'unsolvable' else 'SOLVABLE',
                    constraints=constraints, metadata=metadata(constraints, catalog, benchmark_design=True))
        if difficulty == 'unsolvable':
            reason, affected, _ = feasibility(case, data, catalog)
            if not reason: raise ValueError('Unsolvable template has a witness')
            case.update(unsat_reason=reason, affected_constraint_ids=affected)
        cases.append(case)

    def future_values(days, i):
        # Design placeholders only: no flight/hotel/routing/cost datasets are read.
        return {
            'required_departure_airport': ['SIN', 'LHR', 'SFO'][i % 3],
            'required_arrival_airport': ['JFK', 'LGA', 'EWR'][i % 3],
            'departure_time_preference': dict(start='08:00', end='12:00'),
            'arrival_time_preference': dict(start='14:00', end='18:00'),
            'direct_flight_only': True, 'airline_preference': ['Delta', 'United', 'Singapore Airlines'][i % 3],
            'accommodation_type': 'hotel', 'minimum_hotel_rating': 4,
            'required_neighbourhood': ['Midtown', 'Upper West Side', 'Chelsea'][i % 3],
            'accommodation_amenity': ['wifi', 'breakfast', 'gym'][i % 3],
            'check_in_constraint': '2026-11-01T18:00:00-05:00',
            'check_out_constraint': f'2026-11-{1 + days:02d}T11:00:00-05:00',
            'accommodation_budget_per_night': 250 + 25 * (i % 3),
            'preferred_transport_mode': 'transit', 'avoid_transport_mode': 'car',
            'max_travel_time': 60, 'max_walking_time': 20, 'max_walking_distance': 1500,
            'total_budget': 2500 + days * 500, 'daily_budget': 500,
            'food_budget': days * 120, 'attraction_budget': days * 100,
            'accommodation_budget': days * 300, 'flight_budget': 1500,
        }

    easy = [
        [('trip_duration_days', 1)], [('number_of_travellers', 2), ('traveller_type', 'couple')],
        [('required_arrival_airport', 'JFK'), ('direct_flight_only', True)],
        [('required_departure_airport', 'LHR'), ('departure_time_preference', dict(start='08:00', end='12:00'))],
        [('arrival_time_preference', dict(start='14:00', end='18:00'))],
        [('accommodation_type', 'hotel'), ('minimum_hotel_rating', 4)],
        [('required_neighbourhood', 'Midtown'), ('accommodation_amenity', 'wifi')],
        [('accommodation_budget_per_night', 250)],
        [('preferred_transport_mode', 'transit'), ('max_travel_time', 60)],
        [('avoid_transport_mode', 'car'), ('max_walking_distance', 1500)],
        [('total_budget', 4000)], [('daily_budget', 500), ('food_budget', 240)],
        [('required_attraction', [attractions[0]['attraction_id']]), ('minimum_attraction_count', 1)],
        [('required_restaurant', [restaurants[0]['restaurant_id']]), ('meal_budget_per_person', float(restaurants[0]['price_max']))],
        [('earliest_start_time', '10:00'), ('latest_end_time', '18:00')],
    ]
    for i, pairs in enumerate(easy):
        add('easy', 1 if i == 0 else 2 + i % 3, [constraint(v, x) for v, x in pairs])

    for i in range(15):
        days = 2 + i % 4; f = future_values(days, i)
        a = reviewed_places[15 + i]; r = culinary[i % len(culinary)]
        groups = [
            [('required_arrival_airport', f['required_arrival_airport']), ('accommodation_type', 'hotel'),
             ('flight_budget', f['flight_budget']), ('accommodation_budget_per_night', f['accommodation_budget_per_night'])],
            [('required_neighbourhood', f['required_neighbourhood']), ('required_attraction', [a['attraction_id']]),
             ('preferred_transport_mode', 'transit'), ('max_walking_time', 20)],
            [('required_attraction', [a['attraction_id']]), ('required_restaurant', [r['restaurant_id']]),
             ('meal_time_constraint', dict(meal='lunch', trip_day=1, window=dict(start='12:00', end='13:00'))),
             ('meal_budget_per_person', float(r['price_max']))],
            [('total_budget', f['total_budget']), ('flight_budget', 1500), ('accommodation_budget', f['accommodation_budget']),
             ('food_budget', f['food_budget']), ('attraction_budget', f['attraction_budget'])],
            [('check_in_constraint', f['check_in_constraint']), ('check_out_constraint', f['check_out_constraint']),
             ('max_travel_time', 60), ('traveller_type', 'family')],
        ]
        cs = [constraint(v, x) for v, x in groups[i % 5]]
        if i % 5 == 1: cs.append(constraint('scenic_attraction', True, operator='prefer', softness=True, implicit=True))
        add('medium', days, cs)

    flight_keys = ['required_departure_airport', 'required_arrival_airport', 'departure_time_preference',
                   'arrival_time_preference', 'direct_flight_only', 'airline_preference']
    hotel_keys = ['accommodation_type', 'minimum_hotel_rating', 'required_neighbourhood', 'accommodation_amenity',
                  'check_in_constraint', 'check_out_constraint', 'accommodation_budget_per_night']
    transport_keys = ['preferred_transport_mode', 'avoid_transport_mode', 'max_travel_time', 'max_walking_time', 'max_walking_distance']
    budget_keys = ['total_budget', 'daily_budget', 'food_budget', 'attraction_budget', 'accommodation_budget', 'flight_budget']
    for i in range(15):
        days = 2 + i % 5; f = future_values(days, i)
        r = culinary[(i + 5) % len(culinary)]; a = reviewed_places[i]
        other_cuisine = next(cuisines(x)[0] for x in culinary if not set(cuisines(x)) & set(cuisines(r)))
        attraction_pairs = [
            [('required_attraction', [a['attraction_id']]), ('attraction_category', a['category'])],
            [('excluded_attraction', [attractions[200 + i]['attraction_id']]), ('minimum_attraction_count', 2)],
            [('avoid_attraction_category', next(x['category'] for x in attractions if x['category'] != a['category'])), ('maximum_attraction_count', 4)],
        ][i % 3]
        food_pairs = [
            [('cuisine', cuisines(r)[0]), ('excluded_cuisine', other_cuisine)],
            [('required_restaurant', [r['restaurant_id']]), ('meal_budget_per_person', float(r['price_max']))],
            [('avoid_restaurant', [r['restaurant_id']]), ('minimum_restaurant_rating', 4)],
            [('dietary_requirement', 'vegetarian'), ('required_restaurant', [tagged['restaurant_id']])],
        ][i % 4]
        schedule_pairs = [
            [('earliest_start_time', '09:00')], [('latest_end_time', '20:00')],
            [('required_activity_time', dict(entity_type='attraction', entity_id=a['attraction_id'], trip_day=1, window=dict(start='11:00', end='12:00')))],
            [('meal_time_constraint', dict(meal='dinner', trip_day=days, window=dict(start='18:00', end='19:00')))],
            [('max_activities_per_day', 4)], [('free_time_requirement', 60)], [('buffer_time_requirement', 15)],
        ][i % 7]
        keys = [flight_keys[i % 6], flight_keys[(i + 1) % 6], hotel_keys[i % 7],
                hotel_keys[(i + 1) % 7], transport_keys[i % 5], budget_keys[i % 6]]
        cs = [constraint(v, f[v]) for v in keys]
        cs += [constraint(v, x) for v, x in attraction_pairs + food_pairs + schedule_pairs]
        key = subjective[i % len(subjective)]
        cs.append(constraint(key, 'low' if key == 'crowdedness_preference' else True,
                             operator='prefer', softness=True, implicit=True))
        cs.append(constraint('avoid_repeated_categories', True) if i % 2 == 0
                  else constraint('required_rest_period', 30, implicit=True))
        if i % 3 == 0: cs.append(constraint('trip_duration_days', days))
        add('hard', days, cs)

    # These unavailable variants are outside the explicitly assumed four domains.
    unavailable = [
        [('accessibility_requirement', 'step_free'), ('indoor_only_preference', True)],
        [('weather_sensitive_preference', 'avoid_rain'), ('minimum_attraction_rating', 4)],
        [('special_event_requirement', dict(event_id='nyc_holiday_concert_2026_11_02', date='2026-11-02'))],
    ]
    for i, pairs in enumerate(unavailable):
        add('unsolvable', i + 1, [constraint(v, x) for v, x in pairs])
    for i in range(3):
        r = restaurants[80 + i]
        if i < 2:
            cs = [constraint('required_restaurant', [r['restaurant_id']]), constraint('avoid_restaurant', [r['restaurant_id']])]
        else:
            cs = [constraint('minimum_attraction_count', 5), constraint('maximum_attraction_count', 2)]
        add('unsolvable', i + 1, cs)
    for i in range(3):
        r = culinary[i]
        absent_cuisine = next(cuisines(x)[0] for x in culinary if not set(cuisines(x)) & set(cuisines(r)))
        add('unsolvable', i + 1, [constraint('required_restaurant', [r['restaurant_id']]), constraint('cuisine', absent_cuisine)])
    for i in range(3):
        r = restaurants[100 + i]
        add('unsolvable', i + 1, [constraint('required_restaurant', [r['restaurant_id']]), constraint('meal_budget_per_person', i + 1)])
    for i in range(3):
        add('unsolvable', i + 1, [constraint('earliest_start_time', f'{19 + i}:00'), constraint('latest_end_time', '10:00'), constraint('minimum_attraction_count', i + 1)])
    validate_cases(cases, data)
    return cases


def write_cases(cases, output_dir=BENCHMARK):
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'semantic_cases.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n' for c in cases), encoding='utf-8')
    with (output_dir / 'semantic_case_manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_COLUMNS, lineterminator='\n')
        writer.writeheader(); writer.writerows(manifest_rows(cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--random-state', type=int, default=42)
    parser.add_argument('--output-dir', type=Path, default=BENCHMARK)
    args = parser.parse_args()
    cases = generate_cases(args.random_state); write_cases(cases, args.output_dir)
    print(json.dumps(validate_cases(cases), indent=2))


if __name__ == '__main__': main()
