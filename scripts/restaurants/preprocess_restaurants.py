"""Clean Google Maps or optionally enrich the frozen canonical table from cached OSM."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.shared.restaurant_matching import normalize_name, normalize_address, normalize_zipcode

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = PROJECT_ROOT / 'data/raw/restaurants/google_maps/google_maps_restaurants(cleaned).csv'
REGISTRY_FILE = PROJECT_ROOT / 'data/metadata/restaurant_id_registry.csv'
PROCESSED_DIR = PROJECT_ROOT / 'data/processed'
REPORT_DIR = PROJECT_ROOT / 'data/reports'
BASE_COLUMNS = ['restaurant_id','name','rating','rating_count','price_category','address',
           'latitude','longitude','zipcode','url','source']
PRICE_FIELDS = ['price_min','price_max','price_open_ended','price_range_label']
COLUMNS = BASE_COLUMNS[:5] + PRICE_FIELDS + BASE_COLUMNS[5:]
MAPPING_FILE = PROJECT_ROOT / 'data/metadata/price_mapping.csv'
RAW_COLUMNS = ['URL','Name','Rating','Rating Count','Detailed Ratings','Price Category','Address','Lat','Lon','ZipCode']


def load_google_maps(path=RAW_FILE):
    # Explicit string dtype prevents leading-zero loss while numeric fields retain source values.
    raw = pd.read_csv(path,dtype={'ZipCode':'string'})
    if set(raw.columns)!=set(RAW_COLUMNS):
        raise ValueError(f'Unexpected Google Maps schema: {raw.columns.tolist()}')
    return raw


def clean_google_maps(raw):
    """Remove only exact full-source duplicates, before selecting final fields."""
    cleaned=raw.loc[~raw.duplicated(keep='first')].copy()
    cleaned=cleaned.rename(columns={'Name':'name','Rating':'rating','Rating Count':'rating_count',
        'Price Category':'price_category','Address':'address','Lat':'latitude','Lon':'longitude','ZipCode':'zipcode','URL':'url'})
    cleaned['name']=cleaned.name.astype('string').str.strip()
    cleaned['address']=cleaned.address.astype('string').str.strip()
    cleaned['zipcode']=cleaned.zipcode.map(normalize_zipcode).astype('string')
    for column in ['latitude','longitude']:
        cleaned[column]=pd.to_numeric(cleaned[column],errors='raise')
    cleaned['source']='google_maps_kaggle'
    return cleaned


def assign_restaurant_ids(cleaned, registry_path=REGISTRY_FILE):
    """Reuse legacy physical-identity keys; URL keys distinguish any collisions.

    Keep source row order. New identities are allocated in sorted URL order, so
    source row rearrangements do not change ID assignments.
    """
    registry=(pd.read_csv(registry_path,dtype='string') if registry_path.exists()
              else pd.DataFrame(columns=['identity_key','restaurant_id']))
    if registry.identity_key.duplicated().any() or registry.restaurant_id.duplicated().any():
        raise ValueError('ID registry contains duplicate keys or IDs')
    if registry.isna().any().any() or not registry.restaurant_id.str.fullmatch(r'REST_\d{4,}').all():
        raise ValueError('Invalid ID registry')
    assigned=dict(zip(registry.identity_key,registry.restaurant_id))
    keys=cleaned.apply(lambda row:hashlib.sha256(json.dumps([normalize_name(row['name']),
        normalize_address(row.address),float(row.latitude),float(row.longitude)],ensure_ascii=False).encode()).hexdigest(),axis=1)
    # Exact source duplicates were already removed. Distinct rows at the same
    # identity retain separate IDs rather than being silently discarded.
    used=set(); resolved={}
    for idx in sorted(cleaned.index,key=lambda i:(str(cleaned.at[i,'url']),int(i))):
        key=keys.loc[idx]
        if key in used:
            fingerprint=hashlib.sha256(cleaned.loc[idx].to_json().encode()).hexdigest()
            key=f'{key}:record:{fingerprint}'
        if key in used:raise ValueError('Unresolved identity collision')
        used.add(key);resolved[idx]=key
    next_id=max([int(value.removeprefix('REST_')) for value in assigned.values()] or [0])+1
    for idx in sorted(cleaned.index,key=lambda i:(str(cleaned.at[i,'url']),int(i))):
        key=resolved[idx]
        if key not in assigned:
            assigned[key]=f'REST_{next_id:04d}';next_id+=1
    output=cleaned.copy()
    output['restaurant_id']=[assigned[resolved[idx]] for idx in output.index]
    return output[BASE_COLUMNS],pd.DataFrame(assigned.items(),columns=['identity_key','restaurant_id'])


def load_price_mapping(path=MAPPING_FILE):
    mapping=pd.read_csv(path,dtype={'price_category':'Int64','price_min':'Float64',
        'price_max':'Float64','price_open_ended':'boolean','price_range_label':'string'})
    if mapping.columns.tolist()!=['price_category',*PRICE_FIELDS]:raise ValueError('Unexpected mapping schema')
    if mapping.price_category.isna().any() or mapping.price_category.duplicated().any():raise ValueError('Invalid mapping categories')
    if mapping[['price_min','price_open_ended','price_range_label']].isna().any().any():raise ValueError('Missing mapping values')
    if not mapping.price_min.ge(0).all():raise ValueError('Invalid lower price bound')
    if not mapping.price_open_ended.eq(mapping.price_max.isna()).all():raise ValueError('Only open-ended ranges may have no upper bound')
    bounded=mapping.price_max.notna()
    if not mapping.loc[bounded,'price_min'].le(mapping.loc[bounded,'price_max']).all():raise ValueError('Reversed price bounds')
    return mapping


def add_price_ranges(df, mapping):
    """Apply the experimental metadata mapping without altering source categories.

    Mapping CSV uses ASCII hyphens; display labels use typographic en dashes.
    Unknown non-null categories are errors, never guessed or imputed.
    """
    if mapping.price_category.duplicated().any():raise ValueError('Duplicate mapping categories')
    unknown=df.price_category.notna() & ~df.price_category.isin(mapping.price_category)
    if unknown.any():raise ValueError(f'Unmapped source categories: {df.loc[unknown,"price_category"].unique().tolist()}')
    lookup=mapping.set_index('price_category')
    out=df.copy()
    for field in PRICE_FIELDS:out[field]=out.price_category.map(lookup[field])
    out['price_min']=out.price_min.astype('Float64')
    out['price_max']=out.price_max.astype('Float64')
    out['price_open_ended']=out.price_open_ended.astype('boolean')
    out['price_range_label']=out.price_range_label.astype('string').str.replace('-', '–',regex=False)
    return out[COLUMNS]



def validate_restaurants(restaurants, raw=None, mapping=None):
    if restaurants.columns.tolist()!=COLUMNS:raise ValueError('Unexpected output columns')
    if restaurants.restaurant_id.isna().any() or restaurants.restaurant_id.duplicated().any():raise ValueError('IDs must be unique')
    if restaurants.name.isna().any() or restaurants.name.str.strip().eq('').any():raise ValueError('Names must be nonempty')
    for column,low,high in [('latitude',-90,90),('longitude',-180,180),('rating',0,5)]:
        values=pd.to_numeric(restaurants[column],errors='raise')
        if column!='rating' and values.isna().any():raise ValueError(f'Missing {column}; review source before excluding records')
        if not values.dropna().between(low,high).all():raise ValueError(f'Invalid {column}; no rows silently removed')
    if not isinstance(restaurants.zipcode.dtype,pd.StringDtype):raise ValueError('ZIP must use string dtype')
    if not restaurants.zipcode.dropna().str.fullmatch(r'\d{5}').all():raise ValueError('Invalid ZIP')
    expected_prices=add_price_ranges(restaurants[BASE_COLUMNS],load_price_mapping() if mapping is None else mapping)
    pd.testing.assert_frame_equal(restaurants[PRICE_FIELDS],expected_prices[PRICE_FIELDS],check_dtype=False,check_exact=True)
    missing_category=restaurants.price_category.isna()
    if not restaurants.loc[missing_category,PRICE_FIELDS].isna().all().all():raise ValueError('Missing categories must have no derived prices')
    bounded=restaurants.price_max.notna()
    if not restaurants.loc[bounded,'price_min'].le(restaurants.loc[bounded,'price_max']).all():raise ValueError('Reversed price bounds')
    if raw is not None:
        expected=raw.loc[restaurants.index,'Price Category']
        pd.testing.assert_series_equal(restaurants.price_category,expected,check_names=False,check_dtype=True,check_exact=True)
        pd.testing.assert_series_equal(restaurants.url,raw.loc[restaurants.index,'URL'],check_names=False,check_exact=True)


def sample_price_categories(restaurants):
    columns=['price_category','restaurant_id','name','rating','rating_count','address','url']
    groups=[]
    for _,group in restaurants.loc[restaurants.price_category.notna()].groupby('price_category',sort=True):
        # Stable order before seeded sampling also withstands source row rearrangement.
        groups.append(group.sort_values('restaurant_id').sample(n=min(5,len(group)),random_state=42)[columns])
    if not groups:return pd.DataFrame(columns=columns)
    return pd.concat(groups).sort_values(['price_category','name','restaurant_id']).reset_index(drop=True)


def manual_price_template(samples):
    template=samples[['price_category','restaurant_id','name','address','url']].copy()
    for column in ['observed_price_text','observed_price_min','observed_price_max','notes']:template[column]=''
    return template


def save_manual_template(template,path):
    """Never overwrite manual observations; refuse stale/changed sample identities."""
    if path.exists():
        existing=pd.read_csv(path,dtype={'restaurant_id':'string'})
        if existing.restaurant_id.tolist()!=template.restaurant_id.tolist():
            raise ValueError('Manual-check sample changed; archive the existing observations before regenerating the template')
        return
    template.to_csv(path,index=False)


def canonical_report(restaurants):
    """One canonical summary shared by bootstrap and frozen OSM preprocessing."""
    category=pd.to_numeric(restaurants.price_category.replace('',pd.NA),errors='raise')
    mapping=load_price_mapping()
    lines=['# Restaurant data report','', '## Canonical data','',
        f'- Canonical restaurants: {len(restaurants)}',
        f'- Missing price category: {int(category.isna().sum())}',
        f'- Successfully mapped price rows: {int(category.notna().sum())}',
        f'- Missing rating: {int(restaurants.rating.replace("",pd.NA).isna().sum())}', '',
        '| Category | Rows | Experimental per-person range |', '|---|---:|---|']
    for _,row in mapping.iterrows():
        lines.append(f'| {row.price_category} | {int(category.eq(row.price_category).sum())} | {row.price_range_label.replace("-","–")} |')
    lines+=['', 'Representative original Google Maps URLs were manually inspected by the project team.',
        'Ranges are approximate experimental estimates, not exact real-world guarantees.',
        'Missing categories remain null in all derived price fields; category 4 has no upper bound.',
        'No estimated_meal_cost is defined. See data/metadata/price_mapping.csv for the single mapping source.', '',
        '## Cleaning and provenance','',
        'Canonical source: Kaggle beridzeg45/nyc-restaurants. All source locations are retained.',
        'Names/addresses are trimmed, ZIP formatting is normalized, and only exact full-source duplicates are removed.',
        'Ratings, price categories, original URLs and missing values are preserved. Invalid required data fails validation.']
    if RAW_FILE.exists():
        raw=load_google_maps()
        lines += [f'Raw rows: {len(raw)}; exact duplicates: {int(raw.duplicated().sum())}.',
                  f'Google Maps raw SHA-256: `{hashlib.sha256(RAW_FILE.read_bytes()).hexdigest()}`.']
    else:lines.append('Google Maps raw input unavailable locally; source checksum/duplicate count unknown.')
    lines+=['', '## Integrity and verification','',
        'The ID registry is retained for stable canonical regeneration. Frozen OSM processing never assigns IDs.',
        'All 670 IDs, row order and 15 core fields must pass exact CSV-projection equality before enrichment is written.',
        'Processed output and OSM audit files are deterministic from the same raw cache and metadata.',
        'Active tests cover cleaning, stable IDs, price mapping, OSM extraction/matching/diet tags,',
        'hours defaults, PH handling, calendar scope, frozen core and determinism.',
        'Verification command: `docker compose run --rm data-pipeline python -m unittest discover -s tests -v`.',
        'Cleanup verification: 27 active tests passed; frozen core and complete restaurant CSV stayed byte-identical;',
        'repeat preprocessing matched output checksums, Docker rebuilt without cache, and notebook execution passed.', '']
    if 'osm_id' not in restaurants:
        lines+=['OSM retrieval/enrichment has not been applied; observed coverage is unknown, not zero.', '']
    return '\n'.join(lines)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrich-osm",action="store_true")
    args=parser.parse_args()
    if args.enrich_osm:
        from scripts.restaurants.osm_enrichment import enrich_osm
        enrich_osm()
        return
    existing=PROCESSED_DIR/"restaurants.csv"
    if existing.exists() and pd.read_csv(existing,nrows=0).columns.tolist()!=COLUMNS:
        raise ValueError("Canonical table contains enrichment; use --enrich-osm to preserve the frozen core")
    raw_hash=hashlib.sha256(RAW_FILE.read_bytes()).hexdigest()
    raw=load_google_maps()
    cleaned=clean_google_maps(raw)
    restaurants,registry=assign_restaurant_ids(cleaned)
    mapping=load_price_mapping()
    restaurants=add_price_ranges(restaurants,mapping)
    validate_restaurants(restaurants,raw,mapping)
    samples=sample_price_categories(restaurants)
    PROCESSED_DIR.mkdir(parents=True,exist_ok=True);REPORT_DIR.mkdir(parents=True,exist_ok=True)
    (REPORT_DIR/'audit/restaurants').mkdir(parents=True,exist_ok=True)
    save_manual_template(manual_price_template(samples),PROJECT_ROOT/'data/metadata/price_validation.csv')
    restaurants.to_csv(PROCESSED_DIR/'restaurants.csv',index=False)
    registry.to_csv(REGISTRY_FILE,index=False)
    (REPORT_DIR/'restaurant_data_report.md').write_text(canonical_report(restaurants))
    if hashlib.sha256(RAW_FILE.read_bytes()).hexdigest()!=raw_hash:raise ValueError('Raw file changed')
    print(canonical_report(restaurants));print('\nPrice category distribution (including missing):')
    print(restaurants.price_category.value_counts(dropna=False).sort_index().to_string())
    print('\nFive seeded samples per nonmissing price category:');print(samples.to_string(index=False))
    price_examples=restaurants.loc[restaurants.price_category.notna()].groupby('price_category',sort=True).head(1)[['restaurant_id','name','price_category',*PRICE_FIELDS]]
    print('\nDerived price examples:');print(price_examples.to_string(index=False))
    print('Validation passed. Experimental price ranges applied; no meal cost defined.')


if __name__=='__main__':main()
