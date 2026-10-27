import streamlit as st
from dashboard.components.examples import render as examples


def render(ctx):
    st.title('Examples')
    st.write('These examples are selected to illustrate the mechanisms studied in the project rather than to provide additional aggregate performance evidence.')
    st.caption('Sources are bound automatically: TRAIN R0–R3 interdependencies; TEST R2 protection, R3 widening, and R4 matrix guidance. Candidate, accepted, and post-hoc selected states remain distinct.')
    examples(ctx['runs'])
