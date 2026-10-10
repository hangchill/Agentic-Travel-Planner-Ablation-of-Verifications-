"""Label experimental availability separately from observed OSM evidence.

No complete OSM parser is implemented. Effective schedules are typed JSON:
weekly schedules for assumptions, verbatim osm_opening_hours for observed data.
The calendar is static; no locale or runtime holiday computation is used.
"""
import csv
from datetime import date, datetime
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HOLIDAY_FILE = ROOT/'data/metadata/us_public_holidays.csv'
DAYS = ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')
HOURS_FIELDS = ['opening_hours_effective','opening_hours_is_assumed','has_explicit_holiday_rule',
                'holiday_rule_raw','holiday_rule_status','holiday_rule_source']
DEFAULT_SCHEDULE = {day:[['11:00','22:00']] for day in DAYS}
STATUSES = ('EXPLICIT_CLOSED','EXPLICIT_OPEN','EXPLICIT_SPECIAL_HOURS','UNKNOWN','ASSUMED')


def missing(value):
    if value is None:return True
    if isinstance(value,str):return not value.strip()
    # Support pandas nullable and floating NaN without importing pandas here.
    import pandas as pd
    return bool(pd.isna(value))


def split_rules(raw):
    """Mask quoted comments for token detection, split only unquoted semicolons.

    Retain all unparsed text; unterminated quotes prevent confident classification.
    """
    pieces=[];piece='';masked='';quoted=False;escaped=False
    for char in raw:
        if escaped:
            piece+=char;masked+=' ' if quoted else char;escaped=False;continue
        if char=='\\' and quoted:
            piece+=char;masked+=' ';escaped=True;continue
        if char=='"':
            quoted=not quoted;piece+=char;masked+=' ';continue
        if char==';' and not quoted:
            pieces.append(piece);piece=''
        else:piece+=char
        masked+=' ' if quoted else char
    pieces.append(piece)
    return pieces,masked,quoted


def holiday_rule(raw):
    if missing(raw):
        return dict(has_explicit_holiday_rule=False,holiday_rule_raw=None,
            holiday_rule_status='ASSUMED',holiday_rule_source='experimental_default')
    pieces,masked,unterminated=split_rules(raw)
    has_ph=bool(re.search(r'(?<![\w])PH(?![\w])',masked))
    result=dict(has_explicit_holiday_rule=has_ph,holiday_rule_raw=raw if has_ph else None,
        holiday_rule_status='UNKNOWN',holiday_rule_source='openstreetmap' if has_ph else None)
    if not has_ph or unterminated:return result
    # Full raw source is always retained; only one standalone PH clause is classified.
    clauses=[p.strip() for p in pieces if re.search(r'(?<![\w])PH(?![\w])',split_rules(p)[1])]
    if len(clauses)!=1 or '||' in raw or any('"' in p for p in clauses):return result
    clause=clauses[0]
    if re.fullmatch(r'PH\s+(off|closed)',clause):result['holiday_rule_status']='EXPLICIT_CLOSED'
    elif re.fullmatch(r'PH\s+(open|24/7)',clause):result['holiday_rule_status']='EXPLICIT_OPEN'
    elif holiday_intervals(clause) is not None:result['holiday_rule_status']='EXPLICIT_SPECIAL_HOURS'
    return result


def holiday_intervals(clause):
    match=re.fullmatch(r'PH\s+(\d{2}:\d{2}-\d{2}:\d{2}(?:\s*,\s*\d{2}:\d{2}-\d{2}:\d{2})*)',clause)
    if not match:return None
    intervals=[]
    for part in match[1].split(','):
        start,end=part.strip().split('-')
        sh,sm=map(int,start.split(':'));eh,em=map(int,end.split(':'))
        if not (0<=sh<=23 and 0<=sm<=59 and 0<=eh<=24 and 0<=em<=59 and (eh<24 or em==0)):return None
        # Overnight/equal-bound intervals need fuller semantics; preserve as UNKNOWN.
        if (sh,sm)>=(eh,em):return None
        intervals.append([start,end])
    return intervals


def hours_fields(raw):
    assumed=missing(raw)
    effective={'format':'weekly','schedule':DEFAULT_SCHEDULE} if assumed else {'format':'osm_opening_hours','raw':raw}
    return dict(opening_hours_effective=json.dumps(effective,ensure_ascii=False,separators=(',',':')),
        opening_hours_source='experimental_default' if assumed else 'openstreetmap',
        opening_hours_is_assumed=assumed,**holiday_rule(raw))


def add_hours_rows(rows):
    """Return copies; raw general/kitchen hours and all unrelated fields remain untouched."""
    return [{**row,**hours_fields(row.get('opening_hours_raw'))} for row in rows]


def load_holiday_calendar(path=HOLIDAY_FILE):
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=['date','holiday_name','holiday_type','source']:raise ValueError('Invalid holiday schema')
        rows=list(reader)
    calendar={}
    for row in rows:
        day=date.fromisoformat(row['date'])
        if day.isoformat()!=row['date'] or day in calendar:raise ValueError('Noncanonical or duplicate holiday date')
        if not all(row.values()) or row['holiday_type'] not in {'federal','federal_observed'}:raise ValueError('Invalid holiday metadata')
        calendar[day]=row
    if not calendar:raise ValueError('Empty holiday calendar; coverage unknown')
    return calendar


def holiday_for_date(value,calendar=None):
    day=value.date() if isinstance(value,datetime) else value if isinstance(value,date) else date.fromisoformat(value)
    calendar=load_holiday_calendar() if calendar is None else calendar
    years={d.year for d in calendar}
    if day.year not in years:raise ValueError(f'Holiday coverage unavailable for {day.year}; configured years: {sorted(years)}')
    return calendar.get(day)


def resolve_hours(restaurant,value,calendar=None):
    """Return hours evidence, not an opening-state decision or verifier label.

    Experiment PH dates include federal actual and observed dates in metadata.
    Complex OSM rules stay verbatim, including all surrounding selectors.
    """
    holiday=holiday_for_date(value,calendar)
    fields=hours_fields(restaurant.get('opening_hours_raw'))
    effective=json.loads(fields['opening_hours_effective'])
    evidence='experimental_default' if fields['opening_hours_is_assumed'] else 'ordinary_osm'
    if holiday and not fields['opening_hours_is_assumed']:
        if fields['has_explicit_holiday_rule']:
            evidence='explicit_osm_ph'
            status=fields['holiday_rule_status']
            if status=='EXPLICIT_CLOSED':effective={'format':'holiday','intervals':[]}
            elif status=='EXPLICIT_OPEN':effective={'format':'holiday','intervals':[['00:00','24:00']]}
            elif status=='EXPLICIT_SPECIAL_HOURS':
                pieces,_,_=split_rules(fields['holiday_rule_raw'])
                clause=next(p.strip() for p in pieces if holiday_intervals(p.strip()) is not None)
                effective={'format':'holiday','intervals':holiday_intervals(clause)}
        else:evidence='ordinary_osm_holiday_unknown'
    return {**fields,'opening_hours_effective':effective,'is_public_holiday':holiday is not None,
            'holiday':holiday,'hours_evidence':evidence}


def hours_coverage(rows):
    rows=list(rows);total=len(rows)
    observed=sum(not missing(r.get('opening_hours_raw')) for r in rows)
    explicit=sum(holiday_rule(r.get('opening_hours_raw'))['has_explicit_holiday_rule'] for r in rows)
    counts={status:sum(r['holiday_rule_status']==status for r in rows) for status in STATUSES}
    return '\n'.join(['','## Effective hours and holiday evidence','',
        f'- Observed OSM opening hours: {observed} / {total}',
        f'- Experimental default hours: {total-observed} / {total}',
        f'- Effective opening-hours coverage: {sum(bool(r.get("opening_hours_effective")) for r in rows)} / {total}',
        f'- Restaurants with explicit OSM PH rules: {explicit}',
        f'- Matched observed OSM schedules containing unquoted PH tokens: {explicit}',
        *[f'- {status}: {counts[status]}' for status in STATUSES], '',
        'The 11:00–22:00 daily default is a controlled experimental assumption, not actual restaurant information.',
        'Calendar scope: 2026; actual federal dates plus separately labelled federal observed dates.',
        'The static calendar flags dates; it never implies blanket restaurant closure.',
        'Only explicit OSM PH syntax supplies holiday behaviour. Complex syntax remains UNKNOWN and raw text is preserved.',
        'Effective observed hours use typed JSON containing verbatim OSM syntax; no general schedule parser is supplied.',''])
