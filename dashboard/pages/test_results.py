import streamlit as st
from dashboard import data_loader as data
from dashboard.metrics import team_table, trajectory, round_summary
from dashboard.components import pc, cs, repair_process
from dashboard.components.common import table, freshness


def summary(ctx, kind, filename):
    # Unfiltered uses generated CSV verbatim; subset tables reuse authoritative helpers.
    full = data.test_table(ctx['run'], 'per_query')
    q = ctx['test_q']
    if len(q) == len(full) and set(q.query_uid) == set(full.query_uid):
        return data.test_table(ctx['run'], filename)
    return team_table(q, kind)


def render(ctx):
    st.title('TEST results')
    run = ctx['run']
    if run.partition != 'TEST':
        st.warning('TEST results require an actual TEST run. TRAIN results are never substituted.')
        return
    q = ctx['test_q']
    tabs = st.tabs(['Personal Constraints (PC)', 'Commonsense Constraints (CS)', 'Repair process', 'Benchmark definitions'])
    with tabs[0]:
        pc.render(ctx)
    with tabs[1]:
        cs.render(ctx)
    st.caption('PC and CS comparisons have their own cross-strategy controls. Repair process and benchmark definitions use the sidebar-selected strategy/difficulty.')
    freshness(run)
    if data.test_folder(run) is None:
        st.info(data.reporting_binding(run)[1])
        with tabs[2]:
            st.info('Selected run reporting is Unavailable; available PC/CS comparison runs remain visible.')
        return
    if q.empty:
        with tabs[2]:
            st.info('No queries match the sidebar filters.')
        return
    with tabs[2]:
        observed = []
        matching = set(zip(ctx['a'].query_uid, ctx['a'].step)) if not ctx['a'].empty else set()
        for uid, bundle in data.checkpoints(run).items():
            if uid in set(q.query_uid):
                for cp in bundle['checkpoints']:
                    observed.extend(r for r in trajectory(cp)['rounds'] if (uid, r['step']) in matching)
        repair_process.render(q, summary(ctx, 'process', 'table3_repair_process'), ctx['a'], round_summary(observed, len(q)))
    with tabs[3]:
        st.warning('ChinaTravel raw benchmark CS micro/macro includes the evaluator exception column. The CS reporting table instead counts exceptions as failing all standard checks. Keep these definitions distinct.')
        table(summary(ctx, 'benchmark', 'table4_eval_exp'), 'ChinaTravel benchmark metrics')
