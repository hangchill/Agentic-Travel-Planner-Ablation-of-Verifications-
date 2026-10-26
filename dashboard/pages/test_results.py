import streamlit as st
from dashboard import data_loader as data
from dashboard.components import pc, cs, repair_process, evaluation
from dashboard.components.common import freshness


def render(ctx):
    st.title('TEST results')
    run = ctx['run']
    if run.partition != 'TEST':
        st.warning('TEST results require an actual TEST run. TRAIN results are never substituted.')
        return
    tabs = st.tabs(['Personal Constraints (PC)', 'Commonsense Constraints (CS)', 'Repair Process / Efficiency', 'ChinaTravel Evaluation'])
    with tabs[0]:
        pc.render(ctx)
    with tabs[1]:
        cs.render(ctx)
    with tabs[2]:
        repair_process.render(ctx)
    with tabs[3]:
        evaluation.render(ctx)
    st.caption('All four tables have independent difficulty/strategy controls; sidebar proposal filters select cohorts.')
    freshness(run)
