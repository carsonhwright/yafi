import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard
from ticker_time import HistoryContext


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
    history = HistoryContext().fetch_history_frame('NVDA', '1mo', '1d')

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
    history = HistoryContext().fetch_history_frame('NVDA', '1mo', '1d')
    fig = dashboard.make_multi_field_figure('NVDA', history, ['Open', 'Close', 'Volume'])
    assert len(fig.data) == 3

    third_axis = fig.layout.yaxis3
    assert third_axis.anchor == 'free'
    assert third_axis.overlaying == 'y'
    assert third_axis.position == dashboard.AXIS_STEP
    assert fig.layout.xaxis.domain == (dashboard.AXIS_STEP, 1.0), 'domain must shrink to make room for the 3rd axis'


def test_make_multi_field_figure_with_no_fields_is_empty_but_does_not_crash():
    history = HistoryContext().fetch_history_frame('NVDA', '1mo', '1d')
    fig = dashboard.make_multi_field_figure('NVDA', history, [])
    assert len(fig.data) == 0
    assert 'NVDA' in fig.layout.title.text


def test_history_context_caches_dataframes_and_tickers():
    context = HistoryContext()
    history = context.fetch_history_frame('NVDA', '1mo', '1d')
    assert history is not None
    assert context.dataframes['NVDA'] is history
    assert 'NVDA' in context.tickers


def test_history_context_caches_the_no_data_case_too():
    context = HistoryContext()
    history = context.fetch_history_frame('NOT_A_REAL_TICKER_XYZ', '1mo', '1d')
    assert history is None
    assert context.dataframes['NOT_A_REAL_TICKER_XYZ'] is None, 'a miss should be cached too, not just a hit'


def test_render_charts_lazy_fetch_and_cache():
    cache = HistoryContext()

    graphs, status = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'])
    assert len(graphs) == 1
    assert 'NVDA' in cache.dataframes and cache.dataframes['NVDA'] is not None
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
    cache = HistoryContext()
    graphs, status = dashboard.render_charts(['NOT_A_REAL_TICKER_XYZ'], cache, '1mo', '1d', ['Close'])
    assert graphs == []
    assert cache.dataframes['NOT_A_REAL_TICKER_XYZ'] is None
    assert '0 fetched this update' in status


def _find(children, cls):
    return [c for c in children if isinstance(c, cls)]


def test_render_charts_includes_field_table_when_record_available():
    cache = HistoryContext()
    symbol_records = {
        'NVDA': {'symbol': 'NVDA', 'longName': 'NVIDIA Corporation', 'marketCap': 4600000000000},
    }

    panels, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'], symbol_records)
    assert len(panels) == 1
    panel = panels[0]
    assert not _find(panel.children, dashboard.dcc.Checklist), 'single value_field: no field checklist'
    tables = _find(panel.children, dashboard.html.Table)
    assert len(tables) == 1
    assert len(tables[0].children) == 3, 'one row per field in the record'

    # a symbol with no record falls back to no table
    panels_no_record, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'], {})
    assert not _find(panels_no_record[0].children, dashboard.html.Table)


def test_render_charts_adds_field_checklist_for_multiple_value_fields():
    cache = HistoryContext()
    panels, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close', 'Volume'])
    assert len(panels) == 1
    children = panels[0].children

    checklists = _find(children, dashboard.dcc.Checklist)
    assert len(checklists) == 1
    assert checklists[0].id == {'type': 'field-checklist', 'index': 'NVDA'}
    assert checklists[0].value == ['Close', 'Volume'], 'all configured fields plotted together by default'

    graphs = _find(children, dashboard.dcc.Graph)
    assert len(graphs) == 1
    assert len(graphs[0].figure.data) == 2


def test_render_charts_adds_analysis_button_and_stores_for_every_panel():
    cache = HistoryContext()
    panels, _ = dashboard.render_charts(['NVDA'], cache, '1mo', '1d', ['Close'])
    children = panels[0].children

    button_rows = _find(children, dashboard.html.Div)
    assert len(button_rows) == 1, 'a button container div should be present'
    buttons = button_rows[0].children
    assert len(buttons) == len(dashboard.ANALYSIS_FUNCTIONS)
    button = buttons[0]
    assert button.id == {'type': 'analysis-button', 'index': 'NVDA', 'name': 'outside_stddev'}
    assert button.children == dashboard.ANALYSIS_FUNCTIONS['outside_stddev'][0]

    stores = _find(children, dashboard.dcc.Store)
    active_fields_store = next(s for s in stores if s.id == {'type': 'active-fields', 'index': 'NVDA'})
    assert active_fields_store.data == ['Close']
    highlight_store = next(s for s in stores
                            if s.id == {'type': 'highlight-flag', 'index': 'NVDA', 'name': 'outside_stddev'})
    assert highlight_store.data is False, 'highlighting starts off'


def test_contiguous_ranges_collapses_runs_of_consecutive_positions():
    assert dashboard._contiguous_ranges(set()) == []
    assert dashboard._contiguous_ranges({5}) == [(5, 5)]
    assert dashboard._contiguous_ranges({2, 3, 4, 9}) == [(2, 4), (9, 9)]
    assert dashboard._contiguous_ranges({9, 2, 4, 3}) == [(2, 4), (9, 9)], 'order of input must not matter'


def test_make_multi_field_figure_shades_background_where_outliers_are_active():
    history = HistoryContext().fetch_history_frame('NVDA', '1mo', '1d')

    plain_fig = dashboard.make_multi_field_figure('NVDA', history, ['Close'])
    assert plain_fig.data[0].mode == 'lines'
    assert plain_fig.layout.shapes == (), 'no highlighting active: no shaded bands'

    _, outside_stddev = dashboard.ANALYSIS_FUNCTIONS['outside_stddev']
    expected_positions = set(outside_stddev(history, 'Close').tolist())
    expected_ranges = dashboard._contiguous_ranges(expected_positions)

    highlighted_fig = dashboard.make_multi_field_figure(
        'NVDA', history, ['Close'], active_highlights={'outside_stddev': outside_stddev})
    assert highlighted_fig.data[0].mode == 'lines', 'highlighting shades the background, not the trace'
    shapes = highlighted_fig.layout.shapes
    assert len(shapes) == len(expected_ranges)
    for shape in shapes:
        assert shape.fillcolor == dashboard.OUTLIER_MARKER_COLOR
        assert shape.yref == 'y domain', 'must span the full chart height, not one axis'
        assert shape.y0 == 0 and shape.y1 == 1


if __name__ == '__main__':
    test_compute_check_order()
    test_make_multi_field_figure_colors_match_trace_and_axis()
    test_make_multi_field_figure_adds_free_offset_axis_for_a_third_field()
    test_make_multi_field_figure_with_no_fields_is_empty_but_does_not_crash()
    test_contiguous_ranges_collapses_runs_of_consecutive_positions()
    test_make_multi_field_figure_shades_background_where_outliers_are_active()
    test_history_context_caches_dataframes_and_tickers()
    test_history_context_caches_the_no_data_case_too()
    test_render_charts_lazy_fetch_and_cache()
    test_render_charts_skips_symbols_with_no_data()
    test_render_charts_includes_field_table_when_record_available()
    test_render_charts_adds_field_checklist_for_multiple_value_fields()
    test_render_charts_adds_analysis_button_and_stores_for_every_panel()
    print('ALL GOOD')
