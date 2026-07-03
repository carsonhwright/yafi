import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard


def test_compute_check_order():
    order = dashboard.compute_check_order(['NVDA'], [])
    assert order == ['NVDA']

    order = dashboard.compute_check_order(['NVDA', 'AMD'], order)
    assert order == ['NVDA', 'AMD'], 'newly checked symbols append to the end'

    order = dashboard.compute_check_order(['AMD'], order)
    assert order == ['AMD'], 'unchecking removes from order without disturbing the rest'

    order = dashboard.compute_check_order(['AMD', 'INTC'], order)
    assert order == ['AMD', 'INTC']

    order = dashboard.compute_check_order(['INTC', 'AMD'], order)
    assert order == ['AMD', 'INTC'], 're-checking existing symbols must not reorder them'


def test_render_charts_lazy_fetch_and_cache():
    cache = {}

    graphs, status = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', 'Close')
    assert len(graphs) == 1
    assert 'NVDA' in cache and cache['NVDA'] is not None
    assert '1 fetched this update' in status
    assert '1 cached total' in status

    graphs_again, status_again = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', 'Close')
    assert len(graphs_again) == 1
    assert '0 fetched this update' in status_again, status_again
    assert '1 cached total' in status_again

    graphs, status = dashboard.render_charts(['NVDA', 'AMD'], cache, '1mo', '1d', 'Close')
    assert len(graphs) == 2
    assert '1 fetched this update' in status
    assert '2 cached total' in status

    graphs, status = dashboard.render_charts(['AMD'], cache, '1mo', '1d', 'Close')
    assert len(graphs) == 1
    assert '0 fetched this update' in status
    assert '2 cached total' in status, 'unchecking should not evict the cache'


def test_render_charts_skips_symbols_with_no_data():
    cache = {}
    graphs, status = dashboard.render_charts(['NOT_A_REAL_TICKER_XYZ'], cache, '1mo', '1d', 'Close')
    assert graphs == []
    assert cache['NOT_A_REAL_TICKER_XYZ'] is None
    assert '0 fetched this update' in status


def test_render_charts_includes_field_table_when_record_available():
    cache = {}
    symbol_records = {
        'NVDA': {'symbol': 'NVDA', 'longName': 'NVIDIA Corporation', 'marketCap': 4600000000000},
    }

    panels, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', 'Close', symbol_records)
    assert len(panels) == 1
    panel = panels[0]
    assert len(panel.children) == 2, 'panel should contain the graph and a field table'
    table = panel.children[1]
    assert isinstance(table, dashboard.html.Table)
    assert len(table.children) == 3, 'one row per field in the record'

    # a symbol with no record falls back to just the graph, no table
    panels_no_record, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', 'Close', {})
    assert len(panels_no_record[0].children) == 1


if __name__ == '__main__':
    test_compute_check_order()
    test_render_charts_lazy_fetch_and_cache()
    test_render_charts_skips_symbols_with_no_data()
    test_render_charts_includes_field_table_when_record_available()
    print('ALL GOOD')
