import streamlit as st
from dashboard import data_loader as data
from dashboard.components.examples import render as examples


def render(ctx):
    st.title('Representative examples — candidate finder')
    st.caption('Review candidate examples manually before selecting them for reporting.')
    examples(ctx['run'], ctx['a'], data.analysis_table(ctx['run'], 'r4_selections'))
