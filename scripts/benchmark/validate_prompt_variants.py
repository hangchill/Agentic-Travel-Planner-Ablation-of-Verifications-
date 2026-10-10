"""Validate frozen naturalized prompts using normalized semantic clause coverage.

Bounded natural-language validation: canonical names and equivalent value surfaces
are accepted; unknown content is rejected rather than silently guessed by an LLM.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from scripts.benchmark.generate_prompt_variants import (
    OUTPUT_NAME, PLAN_PATH, STYLES, case_digest, display_name, entity_names, load_cases, manifest_rows, natural_phrase,
)
from scripts.benchmark.validate_semantic_cases import BENCHMARK, load_catalog, load_data

FIELDS = {'prompt_id', 'semantic_case_id', 'difficulty', 'wording_variant',
          'wording_style', 'user_request', 'expected_solvability'}
NUMBER_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
                'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12}
MONTHS = {name: i + 1 for i, name in enumerate(['january','february','march','april','may','june',
                                              'july','august','september','october','november','december'])}


def normalize(text, year=2026):
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    text = text.replace('’', "'").replace('–', '-').replace('—', '-')
    text = re.sub(r'(?<=\d),(?=\d)', '', text)
    for word, value in NUMBER_WORDS.items(): text = re.sub(r'\b' + word + r'\b', str(value), text)
    text = re.sub(r'\b(?:an?|1) hour\b', '60 minutes', text)
    text = re.sub(r'\b(\d+(?:\.\d+)?) hours\b', lambda m: f'{float(m[1]) * 60:g} minutes', text)
    text = re.sub(r'\b(\d+(?:\.\d+)?)\s*(?:km|kilometres?|kilometers?)\b', lambda m: f'{float(m[1]) * 1000:g} meters', text)
    text = re.sub(r'\bmetres?\b', 'meters', text)
    text = re.sub(r'\bminutes?\b', 'minutes', text)
    text = re.sub(r'\bUSD\s*(\d+(?:\.\d+)?)', r'$\1', text, flags=re.I)
    text = re.sub(r'\$(\d+(?:\.\d+)?)', lambda m: f'${float(m[1]):g}', text)
    def ampm(m):
        h = int(m[1]); minute = int(m[2] or 0)
        if not 1 <= h <= 12 or minute >= 60: raise ValueError('Invalid naturalized clock')
        return f"{h % 12 + (12 if m[3] == 'pm' else 0):02d}:{minute:02d}"
    text = re.sub(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', ampm, text)
    text = re.sub(r'\bnoon\b', '12:00', text); text = re.sub(r'\bmidnight\b', '00:00', text)
    for month, value in MONTHS.items():
        text = re.sub(r'\b' + month + r' (\d{1,2})(?:,? (\d{4}))?\b',
                      lambda m: f'{int(m[2] or year):04d}-{value:02d}-{int(m[1]):02d}', text)
    # Validate ISO offsets as local NYC timestamps; offsets are not ignored.
    def iso(m):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        d = datetime.fromisoformat(m[0]); local = d.astimezone(ZoneInfo('America/New_York'))
        return local.strftime('%H:%M on %Y-%m-%d')
    text = re.sub(r'\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}', iso, text)
    aliases = {
        r'\bnonstop\b': 'direct', r'\bno connections\b': 'direct',
        r'\bpublic transport\b': 'public transit', r'\bat most\b': 'at or below',
        r'\bno more than\b': 'at or below', r'\b(?:an?|1) hour\b': '60 minutes',
        r'\bwi[ -]?fi\b': 'wifi', r'\bstar rating of at least\b': 'rated at least',
        r'\b(?:travelling|traveling)\b': 'travelling', r'\bfamily[ -]friendly\b': 'family friendly',
        r'\b(not earlier than)\b': 'no earlier than', r'\bnot later than\b': 'by',
    }
    for pattern, replacement in aliases.items(): text = re.sub(pattern, replacement, text)
    # Punctuation/case/accent normalization accepts canonical display equivalents.
    return re.sub(r'\s+', ' ', re.sub(r'[^\w$:. -]', ' ', text)).strip()


def folded_frame(text):
    return re.sub(r'[^\w$]', '', text)


def validate_equivalence(prompt, case, names):
    raw = prompt['user_request']
    if re.search(r'\b(?:ATTR|REST)_\d+\b', raw): raise ValueError('Internal entity ID exposed')
    text = normalize(raw)
    plans = json.loads(PLAN_PATH.read_text())['prompts']
    plan = next(p for p in plans if p['prompt_id'] == prompt['prompt_id'])
    # Match complete, value-aware predicates, longest first to avoid confusing
    # a scheduled visit with an independent required visit to the same entity.
    clauses = [(c, natural_phrase(c, names)) for c in case['constraints']]
    clauses = sorted([(c, phrase) for c, phrase in clauses if phrase], key=lambda x: -len(normalize(x[1])))
    remainder = text
    for c, phrase in clauses:
        expected = normalize(phrase)
        # Alternate name spellings/casing are normalized against canonical data;
        # no IDs or exact ISO strings are required in user_request.
        match = re.search(r'(?<!\w)' + re.escape(expected) + r'(?!\w)', remainder)
        if not match: raise ValueError(f"Missing/changed semantic constraint {c['constraint_id']}")
        remainder = remainder[:match.start()] + ' ' + remainder[match.end():]
    # Sentence plans contain framing/ordering, not entity names, payloads or IDs.
    # Comparing the residual protects against new constraints and modality changes
    # without requiring exact value surface forms or old controlled-language clauses.
    frame = re.sub(r'\{C\d+\}', '', plan['template'])
    if folded_frame(remainder) != folded_frame(normalize(frame)):
        raise ValueError('Extra content, altered duration/party context, polarity or hard/soft framing')
    # All names must resolve, even for clauses only realized through intro context.
    for c in case['constraints']:
        value = c['value'].get('value')
        ids = value if c['value'].get('kind') == 'entity' else ([value['entity_id']] if isinstance(value, dict) and 'entity_id' in value else [])
        for entity_id in ids:
            canonical = normalize(display_name(entity_id, names))
            if canonical not in text: raise ValueError(f'Missing canonical name: {entity_id}')


def validate_prompts(prompts, cases=None, data=None):
    cases = cases if cases is not None else load_cases(); names = entity_names(data if data is not None else load_data())
    lookup = {c['semantic_case_id']: c for c in cases}
    if len(cases) != 60 or len(lookup) != 60: raise ValueError('Expected 60 unique semantic cases')
    if len(prompts) != 180: raise ValueError('Expected 180 prompts')
    digests = json.loads(PLAN_PATH.read_text())['case_digests']
    if set(lookup) != set(digests) or any(case_digest(c) != digests[c['semantic_case_id']] for c in cases):
        raise ValueError('Frozen semantics/modality changed; wording review required')
    counters = Counter(); expected_ids = {}
    for case in cases:
        counters[case['difficulty']] += 1
        expected_ids[case['semantic_case_id']] = f"{case['difficulty'].upper()}_{counters[case['difficulty']]:03d}"
    ids = set(); texts = set(); groups = {}
    for p in prompts:
        if set(p) != FIELDS or any(not isinstance(v, str) or not v.strip() for v in p.values()): raise ValueError('Invalid prompt schema')
        if p['semantic_case_id'] not in lookup: raise ValueError('Orphan semantic case')
        case = lookup[p['semantic_case_id']]; variant = p['wording_variant']
        if variant not in STYLES or p['wording_style'] != STYLES[variant]: raise ValueError('Invalid style')
        if p['prompt_id'] != expected_ids[p['semantic_case_id']] + '_' + variant: raise ValueError('Invalid prompt ID')
        if p['difficulty'] != case['difficulty'] or p['expected_solvability'] != case['expected_solvability']: raise ValueError('Incorrect linked labels')
        normalized = ' '.join(p['user_request'].split()).casefold()
        if p['prompt_id'] in ids or normalized in texts: raise ValueError('Duplicate prompt ID/text')
        ids.add(p['prompt_id']); texts.add(normalized); groups.setdefault(p['semantic_case_id'], []).append(variant)
        validate_equivalence(p, case, names)
    if set(groups) != set(lookup) or any(Counter(vs) != Counter(STYLES.keys()) for vs in groups.values()): raise ValueError('Expected 3 styles per case')
    if counters != Counter(dict(easy=15, medium=15, hard=15, unsolvable=15)): raise ValueError('Unbalanced difficulties')
    catalog = load_catalog(); families = {t for c in cases for t in c['metadata']['constraint_types_present']}
    variants = {v for c in cases for v in c['metadata']['constraint_variants_present']}
    if families != {e['constraint_type'] for e in catalog['constraints']} or variants != set(catalog['legacy_type_mapping']): raise ValueError('Coverage incomplete')
    return dict(prompt_count=180, semantic_case_count=60, variants_per_case=3, semantic_difficulties=dict(counters),
                prompt_difficulties=dict(Counter(p['difficulty'] for p in prompts)), generalized_types_covered=18, structured_variants_covered=66,
                validation='Normalized semantic values/names plus frozen modality/context plans')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompts', type=Path, default=BENCHMARK / OUTPUT_NAME)
    parser.add_argument('--manifest', type=Path, default=BENCHMARK / 'benchmark_manifest.csv')
    args = parser.parse_args(); cases = load_cases(); prompts = [json.loads(line) for line in args.prompts.read_text().splitlines() if line.strip()]
    report = validate_prompts(prompts, cases)
    with args.manifest.open(newline='') as stream: actual = list(csv.DictReader(stream))
    expected = [{k: str(v) for k, v in row.items()} for row in manifest_rows(prompts, cases)]
    if actual != expected: raise ValueError('Benchmark manifest differs from prompts/cases')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
