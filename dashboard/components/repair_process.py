import streamlit as st
from dashboard.components.common import table
from dashboard.metrics import process_summary, round_counters, proposal_counter_stats, cohort_counter_stats


def render(q, summary, a, rounds):
    st.caption('Changed rounds use the team translated-candidate comparison, including rejected R2 candidates. No-progress uses the explicit persisted decision reason. Costs cover repair only.')
    table(summary, 'Repair process team reporting table')
    table(process_summary(q), 'Additional process summary')
    table(q, 'Filtered TEST per query')
    if not a.empty:
        table(proposal_counter_stats(a), 'Observed proposal counters')
        per_query = round_counters(a, q)
        table(per_query, 'Complete counters per observed query')
        if not per_query.empty:
            stats = cohort_counter_stats(per_query)
            table(stats, 'Counter mean median and valid N')
    table(rounds, 'Round diagnostics')
    if not rounds.empty:
        st.line_chart(rounds.set_index('round')[['plan changed (%)', 'plan unchanged (%)']])
    st.caption('Round diagnostics use observed rounds only. Active after round N means a later round is persisted. Missing rounds are not carried forward. CS message changes are not benchmark check fixes. Budget exhaustion reflects the logged stop reason, even when a run stops before its nominal limit.')
