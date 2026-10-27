"""Presentation/filtering only over the standalone comparison builder's outputs."""
import shlex

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import data_loader as data
from dashboard.components.common import table
from scripts.result_analysis.ablation_comparisons import COMPARISONS, DIFFICULTIES


def render(ctx):
    st.title('Ablations & Comparisons')
    st.caption('TEST pairwise experimental questions. Delta = Right - Left. Positive deltas are not automatically better.')
    identifiers = list(COMPARISONS)
    if 'ablation_comparison' in st.session_state and st.session_state['ablation_comparison'] not in identifiers:
        st.session_state['ablation_comparison'] = 'r0_vs_r4_matrix'
    selected = st.selectbox('Comparison', identifiers, format_func=lambda key: COMPARISONS[key][0], key='ablation_comparison')
    definition = COMPARISONS[selected]
    st.write(definition[4])
    st.caption('Strategy comparison — not a matrix ablation' if selected == 'r3_vs_r4' else definition[3])
    bundle = data.comparison_bundle(selected)
    if not bundle['ready']:
        st.info(bundle['reason'])
        st.code('python -m scripts.result_analysis.ablation_comparisons.build_ablation_comparisons --help')
        return
    validity, metadata = bundle['validity'], bundle['metadata']
    st.subheader(validity['classification'])
    if validity['classification'] != 'Controlled ablation':
        st.warning('This comparison does not establish a causal treatment effect.')
    st.write(validity['reason'])
    if selected == 'r0_vs_r4_matrix':
        st.markdown('**Intended design question:** Does adding matrix-guided repair improve outcomes relative to R0?')
        st.markdown('**Empirical validity:** Are R0 and R4 sufficiently controlled to isolate matrix guidance?')
    st.caption(f"{validity['cohort_label']} · original left N={validity['n_left']}, right N={validity['n_right']}, matched N={validity['n_matched']}")
    with st.expander('Compatibility checklist'):
        table(pd.DataFrame(validity['checks']), 'Comparison compatibility checklist')
        if validity.get('implementation_audit'):
            st.caption(validity.get('implementation_audit_basis',''))
            table(pd.DataFrame(validity['implementation_audit']), 'R0 R4 implementation audit')
        if validity['excluded_left'] or validity['excluded_right']:
            st.write({'Excluded left UIDs': validity['excluded_left'], 'Excluded right UIDs': validity['excluded_right']})
        if validity.get('errors'):
            st.write(validity['errors'])
    if validity['available']:
        difficulty = st.selectbox('Difficulty', list(DIFFICULTIES), index=3, key='ablation_difficulty')
        cohort = validity['difficulty_cohorts'][difficulty]
        if not cohort['compatible']:
            st.info('Selected difficulty populations are unavailable or incompatible. No paired values or deltas are displayed.')
        else:
            summary = bundle['summary']
            summary = summary[summary.difficulty == difficulty].copy()
            left, right = definition[1:3]
            shown = summary[['metric_group','metric','left_value','right_value','delta','unit','direction']].rename(
                columns={'metric_group':'Group','metric':'Metric','left_value':left,'right_value':right,'delta':'Delta (R4 - R0)' if selected=='r0_vs_r4_matrix' else 'Delta (Right - Left)', 'unit':'Unit','direction':'Better'})
            table(shown, 'Pairwise common results')
            st.caption('Higher/lower/descriptive comes from the metric catalog. Loop candidate metrics include rejected proposals; accepted metrics are separate. Table 4 CS micro retains the raw evaluator-exception caveat.')
            st.subheader('Mechanism-specific evidence')
            st.caption('R3 uses scheduled widening. R4 selected outcomes are post-hoc diagnostics, separate from the benchmark final accepted trajectory.')
            mechanism = bundle['mechanism']
            mechanism = mechanism[mechanism.difficulty == difficulty]
            displayed_mechanism = mechanism[['side','run','metric','value','evidence_n','unit','source','denominator']].copy()
            if displayed_mechanism.unit.eq('Not applicable').any():
                displayed_mechanism['value'] = displayed_mechanism.value.map(lambda v: 'Unavailable' if pd.isna(v) else str(v))
                displayed_mechanism.loc[displayed_mechanism.unit.eq('Not applicable'),'value'] = 'Not applicable'
            table(displayed_mechanism, 'Pairwise mechanism evidence')
            metric = st.selectbox('Supplementary metric comparison', summary.metric.tolist(), key='ablation_metric')
            row = summary[summary.metric == metric].iloc[0]
            chart = pd.DataFrame({'Run':[left,right],'Value':[row.left_value,row.right_value]})
            if chart.Value.notna().any():
                st.plotly_chart(px.bar(chart, x='Run', y='Value', title=metric, labels={'Value':str(row.unit)}), width='stretch')
            with st.expander('Metric definitions, denominators and availability'):
                table(summary[['metric','source','denominator','n_values_left','n_values_right','unavailable_reason']], 'Pairwise metric sources')
    with st.expander('Reproducibility and provenance'):
        st.write({'Generated at':metadata['generated_at'],'Output folder':bundle['folder'],'Source runs':metadata['source_runs'],'Notes':metadata['notes']})
        st.code(shlex.join(metadata['command']))
        st.caption('Every displayed number is read from generated CSV/JSON. Regenerate the CLI outputs after final experiments, then refresh Streamlit. Source/output hashes are checked before display.')
