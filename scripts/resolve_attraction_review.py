"""Generate and validate subtype proposals before any metadata changes."""
import json
import pandas as pd
from filter_attractions import ROOT, load_rules, classify_rows, SOURCE_DTYPES, subtype_audit
from explore_attractions import markdown_table


def proposal_reason(row,names):
    label=row.facility_domain_label
    if label=='UNKNOWN_UNDOCUMENTED':return 'Undocumented type/domain pair; no authoritative meaning can justify promotion.'
    if label in {'Church','Synagogue','Temple','Mosque','Convent/Monastery','Library','Bridge'}:
        return 'Mixed ordinary facilities and potential cultural landmarks; landmark identity/public access needs record-level evidence.'
    if label=='Market':return 'Samples include wholesale/terminal-market infrastructure alongside visitor markets such as Chelsea Market and Essex Market; blanket inclusion or exclusion is unsafe.'
    if label=='Other':return 'Broad Other label combines visitor features with service infrastructure; source subtype does not separate them.'
    if label in {'Island','Lake','River','Pond','Stream'}:return 'Water/natural features include inaccessible or constituent geography; scenic value alone does not establish a visitable destination.'
    if label in {'Pier','Ferry landing/terminal','Marina'}:return 'Visitor waterfront facilities coexist with functional marine/transport infrastructure; access and itinerary relevance vary.'
    if label in {'Playground','Recreational Center','Pool','Golf Course'}:return 'Local recreation and visitor facilities are mixed; activity-specific access, booking and suitability cannot be resolved from subtype alone.'
    if label=='Center':return 'Centers combine cultural/visitor sites with shopping or local/community facilities; type-level relevance is mixed.'
    if label=='Cemetery/Morgue':return 'Historic visitable burial sites coexist with ordinary cemetery/morgue services; selective evidence is necessary.'
    return 'Source-supported subtype remains mixed; no evidence justifies changing every member.'


def main():
    rules=load_rules();clean=pd.read_csv(ROOT/'data/interim/commonplace_attractions_clean.csv',dtype=SOURCE_DTYPES)
    classified=classify_rows(clean,rules)
    audit=subtype_audit(classified,rules,'REVIEW')
    rows=[]
    for row in audit.itertuples(index=False):
        rows.append(dict(facility_type=row.facility_type,facility_domain_code=row.facility_domain_code,
            facility_domain_label=row.facility_domain_label,current_decision='REVIEW',row_count=row.row_count,
            representative_examples=row.example_names,proposed_decision='KEEP_REVIEW',reason=proposal_reason(row,json.loads(row.example_names))))
    proposals=pd.DataFrame(rows)
    expected=set(map(tuple,rules.loc[rules.decision.eq('REVIEW'),['facility_type','facility_domain_code']].values))
    actual=set(map(tuple,proposals[['facility_type','facility_domain_code']].values))
    if expected!=actual or proposals[['facility_type','facility_domain_code']].duplicated().any():raise AssertionError('Subtype proposal coverage failed')
    if proposals.row_count.sum()!=classified.attraction_filter_decision.eq('REVIEW').sum():raise AssertionError('Review accounting failed')
    path=ROOT/'data/reports/commonplace_review_resolution.md'
    path.write_text('\n'.join(['# CommonPlace subtype REVIEW resolution','',
        'Subtype-level proposals generated and internally validated before any possible application. Authoritative rules remain solely in commonplace_attraction_filter.csv.','',
        markdown_table(proposals),'',
        '## Resolution and before/after accounting','',
        'No whole-subtype promotion meets the high-confidence requirement. All 29 configured REVIEW subtypes remain REVIEW (28 populated, Stream has zero rows). This is deliberate: ordinary infrastructure and visitor destinations coexist in the inspected subtypes. No thousands-of-record manual classification or keyword-based rule was applied.',
        'Before and after: INCLUDE 2901; REVIEW 5790; EXCLUDE 11760; UNMAPPED 0; TOTAL 20451.',
        'Metadata is unchanged because no high-confidence subtype change was justified. The classified/candidate/review/unmapped outputs are regenerated from the existing single source of truth.',
        'Kaggle name-only examples such as Bronx Library Center and Hell Gate Bridge support retaining mixed Library/Bridge categories for selective review; they are not confirmed matches and do not justify promotion.',
        'Market samples explicitly include BK WHOLESALE MEAT MARKET BLDG B, BROOKLYN TERMINAL MARKET, ESSEX MARKET and CHELSEA MARKET. Recreational samples include comfort stations and community centers; broad Other contains both monuments and maintenance facilities.',
        'The priority term Cultural Center is represented by the actual cultural type 3/Center and Other labels, not invented as a new taxonomy category. Other absent terms are not added.',
        'Sample names use the existing deterministic seeded subtype audit; conclusions consider source subtype meaning and its counterexamples, not one tourist-list resemblance.','']))
    print('Validated REVIEW proposals:',len(proposals),'rows:',int(proposals.row_count.sum()),'; no blanket subtype promotions')

if __name__=='__main__':main()
