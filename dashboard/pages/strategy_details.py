import streamlit as st
from dashboard.components.strategy_specific import render as strategy


def render(ctx):
    st.title(f'Strategy details · {ctx["run"].label}')
    strategy(ctx['run'], ctx['a'], ctx['q'])
