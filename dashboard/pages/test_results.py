import streamlit as st
from dashboard.components import pc, cs, repair_process, evaluation
from dashboard.page_context import unfiltered


def render(ctx):
    st.title('TEST set')
    st.caption('Final TEST benchmark reporting')
    ctx = unfiltered(ctx['runs'], 'TEST')
    tabs = st.tabs(['Personal Constraints (PC)', 'Commonsense Constraints (CS)', 'Repair Process / Efficiency', 'ChinaTravel Evaluation'])
    with tabs[0]:
        pc.render(ctx)
    with tabs[1]:
        cs.render(ctx)
    with tabs[2]:
        repair_process.render(ctx)
    with tabs[3]:
        evaluation.render(ctx)
    st.caption('All four tables have independent, page-local difficulty and strategy controls.')
