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


def test_make_multi_field_figure_colors_match_trace_and_axis():
    history = dashboard.fetch_history_frame('NVDA', '1mo', '1d')

    fig = dashboard.make_multi_field_figure('NVDA', history, ['Close', 'Volume'])
    assert len(fig.data) == 2

    for i, field in enumerate(['Close', 'Volume']):
        suffix = '' if i == 0 else str(i + 1)
        axis = fig.layout['yaxis' + suffix]
        expected_color = dashboard.FIELD_COLORS[field]
        assert fig.data[i].line.color == expected_color
        assert axis.tickfont.color == expected_color, 'axis tick color must match its trace color'
        assert axis.title.font.color == expected_color, 'axis title color must match its trace color'
    assert fig.layout.yaxis.side == 'left'
    assert fig.layout.yaxis2.side == 'right'


def test_make_multi_field_figure_adds_free_offset_axis_for_a_third_field():
    history = dashboard.fetch_history_frame('NVDA', '1mo', '1d')
    fig = dashboard.make_multi_field_figure('NVDA', history, ['Open', 'Close', 'Volume'])
    assert len(fig.data) == 3

    third_axis = fig.layout.yaxis3
    assert third_axis.anchor == 'free'
    assert third_axis.overlaying == 'y'
    assert third_axis.position == dashboard.AXIS_STEP
    assert fig.layout.xaxis.domain == (dashboard.AXIS_STEP, 1.0), 'domain must shrink to make room for the 3rd axis'


def test_make_multi_field_figure_with_no_fields_is_empty_but_does_not_crash():
    history = dashboard.fetch_history_frame('NVDA', '1mo', '1d')
    fig = dashboard.make_multi_field_figure('NVDA', history, [])
    assert len(fig.data) == 0
    assert 'NVDA' in fig.layout.title.text


def test_render_charts_lazy_fetch_and_cache():
    cache = {}

    graphs, status = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'])
    assert len(graphs) == 1
    assert 'NVDA' in cache and cache['NVDA'] is not None
    assert '1 fetched this update' in status
    assert '1 cached total' in status

    graphs_again, status_again = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'])
    assert len(graphs_again) == 1
    assert '0 fetched this update' in status_again, status_again
    assert '1 cached total' in status_again

    graphs, status = dashboard.render_charts(['NVDA', 'AMD'], cache, '1mo', '1d', ['Close'])
    assert len(graphs) == 2
    assert '1 fetched this update' in status
    assert '2 cached total' in status

    graphs, status = dashboard.render_charts(['AMD'], cache, '1mo', '1d', ['Close'])
    assert len(graphs) == 1
    assert '0 fetched this update' in status
    assert '2 cached total' in status, 'unchecking should not evict the cache'


def test_render_charts_skips_symbols_with_no_data():
    cache = {}
    graphs, status = dashboard.render_charts(['NOT_A_REAL_TICKER_XYZ'], cache, '1mo', '1d', ['Close'])
    assert graphs == []
    assert cache['NOT_A_REAL_TICKER_XYZ'] is None
    assert '0 fetched this update' in status


def test_render_charts_includes_field_table_when_record_available():
    cache = {}
    symbol_records = {
        'NVDA': {'symbol': 'NVDA', 'longName': 'NVIDIA Corporation', 'marketCap': 4600000000000},
    }

    panels, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'], symbol_records)
    assert len(panels) == 1
    panel = panels[0]
    assert len(panel.children) == 2, 'single value_field: just the graph and a field table, no toggle button'
    assert isinstance(panel.children[0], dashboard.dcc.Graph)
    table = panel.children[1]
    assert isinstance(table, dashboard.html.Table)
    assert len(table.children) == 3, 'one row per field in the record'

    # a symbol with no record falls back to just the graph, no table
    panels_no_record, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'], {})
    assert len(panels_no_record[0].children) == 1


def test_render_charts_adds_field_checklist_for_multiple_value_fields():
    cache = {}
    panels, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close', 'Volume'])
    assert len(panels) == 1
    checklist, graph = panels[0].children
    assert isinstance(checklist, dashboard.dcc.Checklist)
    assert checklist.id == {'type': 'field-checklist', 'index': 'NVDA'}
    assert checklist.value == ['Close', 'Volume'], 'all configured fields plotted together by default'
    assert isinstance(graph, dashboard.dcc.Graph)
    assert len(graph.figure.data) == 2


if __name__ == '__main__':
    test_compute_check_order()
    test_make_multi_field_figure_colors_match_trace_and_axis()
    test_make_multi_field_figure_adds_free_offset_axis_for_a_third_field()
    test_make_multi_field_figure_with_no_fields_is_empty_but_does_not_crash()
    test_render_charts_lazy_fetch_and_cache()
    test_render_charts_skips_symbols_with_no_data()
    test_render_charts_includes_field_table_when_record_available()
    test_render_charts_adds_field_checklist_for_multiple_value_fields()
    print('ALL GOOD')
