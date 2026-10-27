import streamlit as st
from dashboard.page_context import diagnostics
from dashboard.components.strategy_specific import render as strategy


def render(ctx):
    st.title('Strategy-Specific')
    st.caption('TEST strategy behaviour and diagnostics')
    local = diagnostics(ctx['runs'], 'TEST', 'details')
    if local is None:
        return
    strategy(local['run'], local['a'], local['q'])
