import pandas as pd
import streamlit as st
from dashboard.components.common import table, cards
from dashboard.metrics import (localisation_summary, protection_summary, scope_summary, guidance_summary, rollback_preservation, scope_round_summary,
                               localisation_cohort, localisation_reasons, protection_round_summary,
                               rollback_cohort, scope_round_usage, guidance_cohort, support_rows,
                               value_distribution, selection_cohort)
from dashboard import data_loader as data


def render(run, a, q):
    if a.empty:
        st.info('No matching proposals for strategy diagnostics.')
        return
    if run.strategy == 'R0':
        st.caption('Global baseline: measured edit footprint only; common performance metrics are on TEST set.')
        table(a, 'R0 edit footprints', ['query_uid', 'step', 'changed_slot_count', 'changed_slot_rate'])
        st.bar_chart(value_distribution(a, 'changed_slot_count'))
    elif run.strategy == 'R1':
        st.caption('Localisation success requires a logged editable location; missing location evidence stays unknown. A successful one-slot repair is shown separately and does not prove localisation success for all other proposals.')
        cards(localisation_cohort(a))
        table(localisation_summary(a), 'R1 localisation by round')
        table(localisation_reasons(a), 'R1 failure reasons')
        table(data.analysis_table(run, 'localization').query('query_uid in @a.query_uid') if not data.analysis_table(run, 'localization').empty else pd.DataFrame(), 'R1 generated localisation evidence')
        st.info('Repairs confined to intended scope (%): Unavailable unless explicitly validated in persisted evidence.')
    elif run.strategy == 'R2':
        st.caption('Harmful candidate = at least one previously passing, explicitly protected PC regressed. Candidate regressions include rejected proposals; accepted-state regressions exclude them.')
        summary = protection_summary(a)
        table(summary, 'R2 protection funnel')
        st.bar_chart(summary[['all candidates', 'harmful candidates', 'rejected harmful candidates', 'harmful candidates accepted']].T.rename(columns={0: 'candidates'}))
        preservation = rollback_preservation(data.checkpoints(run))
        if not preservation.empty:
            preservation = preservation.merge(a[['query_uid', 'step']].drop_duplicates(), on=['query_uid', 'step'])
            rejected = preservation[preservation.rejected]
            cards(rollback_cohort(preservation, len(q)))
            table(rejected, 'R2 verified plan preservation')
        table(protection_round_summary(a), 'R2 harmful candidates by round')
        table(a, 'R2 candidate versus accepted', ['query_uid', 'step', 'accepted', 'protected_regression_count', 'fixed_count', 'newly_violated_count', 'accepted_fixed_count', 'accepted_newly_violated_count', 'decision_reason', 'before_personal_constraints', 'after_personal_constraints', 'accepted_personal_constraints_after'])
    elif run.strategy == 'R3':
        st.caption('Scope widening is observed from the logged schedule. It is not assumed to be triggered by failure. Successful repair here means at least one targeted PC fixed; CS rounds are separate diagnostics.')
        per_query, cohort = scope_summary(a, len(q))
        table(cohort, 'R3 Slot Day Plan')
        if not cohort.empty:
            st.bar_chart(cohort.set_index('scope')['queries reaching'])
        table(per_query, 'R3 query scopes')
        table(scope_round_usage(a), 'R3 round scopes')
        table(scope_round_summary(a), 'R3 escalation after each round')
        table(a, 'R3 observed widening events', ['query_uid', 'step', 'editable_scope', 'next_scope', 'next_scope_escalation', 'escalation_reason', 'targeted_fixed_count'])
    else:
        st.caption('Matrix advice is advisory. Supported means at least one logged relationship has positive support; a proposal can also contain unsupported cells. Logging does not establish that the model followed advice. Structural guards can force an unchanged proposal while accepted remains True.')
        cards(guidance_cohort(a))
        table(guidance_summary(a), 'R4 guidance by round')
        supports = support_rows(a)
        table(supports, 'R4 logged support distribution')
        if not supports.empty:
            st.bar_chart(value_distribution(supports, 'guidance_support'))
        for name in ['r4_selections', 'r4_trials', 'r4_safety_summary', 'r4_matrix_guidance']:
            frame = data.analysis_table(run, name)
            if not frame.empty and 'query_uid' in frame:
                frame = frame[frame.query_uid.isin(q.query_uid)]
            if 'step' in frame and not frame.empty:
                frame = frame.merge(a[['query_uid', 'step']].drop_duplicates(), on=['query_uid', 'step'], how='inner')
            table(frame, name)
        s = data.analysis_table(run, 'r4_selections')
        if not s.empty:
            s = s[s.query_uid.isin(q.query_uid)]
            cards(selection_cohort(s))
