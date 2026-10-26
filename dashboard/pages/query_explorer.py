import streamlit as st
from dashboard.components.query_explorer import render as explorer


def render(ctx):
    st.title('Query explorer')
    q = ctx['q']
    if q.empty:
        st.info('No query evidence matches the current filters.')
        return
    uid = st.selectbox('Query UID', sorted(q.query_uid.unique()))
    filters = dict(ctx['filters'])
    if any(filters.get(k, 'All') != 'All' for k in ('phase', 'round', 'family', 'outcome')):
        filters['allowed_steps'] = set(zip(ctx['a'].query_uid, ctx['a'].step, ctx['a'].repair_strategy)) if not ctx['a'].empty else set()
    explorer(ctx['run'], uid, filters)
