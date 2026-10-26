import numpy as np
import plotly.graph_objects as go
import streamlit as st
from dashboard.components.common import cards, table
from dashboard.metrics import matrix_coverage


def render(m, minimum):
    if m.empty:
        st.info('Matrix evidence: Unavailable.')
        return
    m = m[(m.source_family != 'commonsense_repair') & (m.source_family != m.destination_family)].copy()
    coverage = matrix_coverage(m)
    cards({k: coverage.get(k) for k in ['supported cells', 'possible cells', 'median support (supported)', 'max support']})
    st.caption(f'Coverage: {coverage.get("coverage", 0):.1%}. Observed repair-regression relationships are descriptive. Cell supports count opportunities, not independent queries. Diagonal cells are excluded.')
    families = sorted(set(m.source_family) | set(m.destination_family))
    def pivot(key):
        return m.pivot(index='source_family', columns='destination_family', values=key).reindex(index=families, columns=families).to_numpy()
    rates, support, counts = pivot('regression_rate'), pivot('support_count'), pivot('regression_count')
    visible = np.where((support > 0) & (support >= minimum), rates, np.nan)
    fig = go.Figure(go.Heatmap(z=visible, x=families, y=families, zmin=0, zmax=1,
                              colorscale=[[0, '#e6f4f1'], [1, '#145c6b']],
                              customdata=np.stack([counts, support], axis=-1),
                              hovertemplate='Repaired: %{y}<br>Regressed: %{x}<br>Rate: %{z:.3f}<br>Regressions: %{customdata[0]}<br>Support: %{customdata[1]}<extra></extra>'))
    fig.update_layout(xaxis_title='Regressed PC family', yaxis_title='Repaired PC family',
                      plot_bgcolor='#d8dde2', height=560)
    st.plotly_chart(fig, width='stretch')
    st.caption('Gray = no support, diagonal, or hidden by minimum support. Pale green = observed zero regressions with positive support. The cell table distinguishes all statuses.')
    m['status'] = np.select([m.support_count == 0, m.support_count < minimum, m.regression_count == 0],
                            ['No support', 'Below minimum support', 'Observed zero regressions'], default='Observed regressions')
    with st.expander('All persisted cells and support', expanded=False):
        table(m, 'Matrix cells')
    st.subheader('Strongest supported observed repair-regression relationships')
    sort = st.selectbox('Sort relationships by', ['regression_rate', 'support_count', 'regression_count'])
    top = st.slider('Top N relationships', 1, 80, 15)
    strong = m[(m.support_count > 0) & (m.support_count >= minimum)].sort_values(sort, ascending=False).head(top)
    table(strong, 'Supported relationships')
