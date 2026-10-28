"""Launch from repository root: streamlit run dashboard/app.py."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from dashboard import data_loader as data
from dashboard.pages import (overview, train_interdependencies, test_results,
                             strategy_details, query_explorer, ablation_comparisons)


# Labels and order are presentation-only; module URL paths remain stable.
PAGE_SPECS = (
    (overview, 'Overview'),
    (query_explorer, 'Query Explorer'),
    (train_interdependencies, 'TRAIN set'),
    (test_results, 'TEST set'),
    (ablation_comparisons, 'Ablations & Comparisons'),
    (strategy_details, 'Strategy-Specific'),
)


def main():
    st.set_page_config(page_title='Repair analysis', page_icon='📊', layout='wide')
    ctx = {'runs': data.discover_runs()}
    pages = [st.Page(lambda module=module: module.render(ctx), title=title,
                     url_path=module.__name__.rsplit('.', 1)[-1], default=i == 0)
             for i, (module, title) in enumerate(PAGE_SPECS)]
    navigation = st.navigation(pages, position='top')
    with st.sidebar:
        if st.button('Refresh local data', key='refresh_data'):
            st.cache_data.clear()
            st.rerun()
    navigation.run()


if __name__ == '__main__':
    main()
