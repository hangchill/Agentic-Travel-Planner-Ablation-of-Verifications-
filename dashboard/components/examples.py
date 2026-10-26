import streamlit as st
from dashboard.components.common import table
from dashboard.metrics import candidate_examples, example_markdown, rollback_preservation
from dashboard import data_loader as data


def render(run, a, selections):
    categories = ['Cascading regression']
    categories += {'R2': ['R2 protection'], 'R3': ['R3 widening'],
                   'R4': ['R4 guidance', 'R4 limitation']}.get(run.strategy, [])
    category = st.selectbox('Example criteria', categories)
    preservation = rollback_preservation(data.checkpoints(run)) if category == 'R2 protection' else None
    found = candidate_examples(a, category, selections, preservation)
    st.caption('Candidate examples until manually reviewed and selected. These filters do not establish statistical representativeness. A cascade requires a targeted PC fix and a new candidate PC violation in the same proposal.')
    table(found, 'Candidate examples', ['query_uid', 'step', 'repair_phase', 'target_family',
                                       'editable_scope', 'accepted', 'targeted_fixed_count',
                                       'newly_violated_count', 'guidance', 'decision_reason'])
    if not found.empty:
        i = st.selectbox('Candidate to export', range(len(found)),
                         format_func=lambda i: f'{found.iloc[i].query_uid} · round {found.iloc[i].step}')
        summary = example_markdown(run, found.iloc[i].to_dict())
        st.markdown(summary)
        st.download_button('Export example summary', summary, file_name='candidate_example.md', mime='text/markdown')
