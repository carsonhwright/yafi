import logging

import pandas as pd
import plotly.graph_objects as go
from dash import ALL, MATCH, Dash, Input, Output, State, dcc, html

from data_analysis import where_is_outside_stddev
from ticker_time import HistoryContext

logger = logging.getLogger('yafi.dashboard')

GRID_COLUMNS = 4
CHECKLIST_GROUP_SIZE = 100
SIDEBAR_WIDTH = '240px'


def _chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def compute_check_order(checked, previous_order):
    """Returns `previous_order` with newly-checked symbols appended and unchecked ones dropped."""
    checked = checked or []
    order = [symbol for symbol in (previous_order or []) if symbol in checked]
    for symbol in checked:
        if symbol not in order:
            order.append(symbol)
    return order


FIELD_COLORS = {
    'Open': "#2281c5",
    'High': "#0b584c",
    'Low': "#5a360d",
    'Close': '#9467bd',
    'Volume': '#ff7f0e',
}
AXIS_STEP = 0.08
OUTLIER_MARKER_COLOR = '#e63946'

# Registry of per-chart analysis buttons: name -> (button label, df/field -> positional indexes).
# Each entry gets its own toggle button (see render_charts); add an entry here to add a button,
# no other wiring needed. The function must take (df, field) and return positions usable to
# index back into df[field] (see data_analysis.where_is_outside_stddev). The label comes from
# the function's own @tag(...) (see decos.py) so the button text lives next to the function it names.
ANALYSIS_FUNCTIONS = {
    'outside_stddev': (where_is_outside_stddev.tag, where_is_outside_stddev),
}


def _contiguous_ranges(positions):
    """Collapses a set of positional indexes into (start, end) runs of consecutive positions,
    so e.g. {2, 3, 4, 9} becomes [(2, 4), (9, 9)] - one shaded band per run instead of one per point."""
    if not positions:
        return []
    ordered = sorted(positions)
    ranges = []
    start = prev = ordered[0]
    for pos in ordered[1:]:
        if pos == prev + 1:
            prev = pos
        else:
            ranges.append((start, prev))
            start = prev = pos
    ranges.append((start, prev))
    return ranges


def make_multi_field_figure(symbol, history, fields, active_highlights=None):
    """Plots every field in `fields` as its own trace with its own y-axis, each axis colored
    to match its trace (first field on the left, second on the right, further ones stacked
    further out on alternating sides) so differently-scaled fields (e.g. Close vs Volume)
    stay individually readable while still being visually comparable on one chart.

    `active_highlights` is a {name: func} subset of ANALYSIS_FUNCTIONS's functions - whichever
    analysis buttons are currently toggled on for this chart. Wherever any of them flags a
    position (across any plotted field), that x-range gets a shaded background band spanning
    the full chart height; with none active, the chart has no shading."""
    fig = go.Figure()

    if not fields:
        fig.update_layout(title=f'{symbol} (no fields selected)', height=280,
                           margin={'t': 30, 'l': 45, 'r': 10, 'b': 30})
        return fig

    left_extra = 0.0
    right_extra = 0.0
    domain_left = 0.0
    domain_right = 1.0

    for i, field in enumerate(fields):
        color = FIELD_COLORS.get(field, '#333333')
        series = history[field]
        suffix = '' if i == 0 else str(i + 1)

        trace_kwargs = {'x': series.index, 'y': series.values, 'name': field, 'mode': 'lines',
                         'line': {'color': color}, 'yaxis': 'y' + suffix}
        fig.add_trace(go.Scatter(**trace_kwargs))

        axis_layout = {
            'title': {'text': field, 'font': {'color': color}},
            'tickfont': {'color': color},
            'linecolor': color,
        }
        if i == 0:
            axis_layout['side'] = 'left'
        elif i == 1:
            axis_layout.update({'overlaying': 'y', 'side': 'right'})
        else:
            side = 'left' if i % 2 == 0 else 'right'
            if side == 'left':
                left_extra += AXIS_STEP
                position = left_extra
                domain_left = max(domain_left, left_extra)
            else:
                right_extra += AXIS_STEP
                position = 1 - right_extra
                domain_right = min(domain_right, 1 - right_extra)
            axis_layout.update({'overlaying': 'y', 'anchor': 'free', 'side': side, 'position': position})

        fig.update_layout(**{f'yaxis{suffix}': axis_layout})

    if active_highlights:
        flagged = set()
        for field in fields:
            for highlight_fn in active_highlights.values():
                flagged.update(highlight_fn(history, field).tolist())

        index = history.index
        step = index[1] - index[0] if len(index) > 1 else pd.Timedelta(days=1)
        for start, end in _contiguous_ranges(flagged):
            fig.add_vrect(x0=index[start] - step / 2, x1=index[end] + step / 2,
                          fillcolor=OUTLIER_MARKER_COLOR, opacity=0.2, line_width=0, layer='below')

    fig.update_layout(
        title=symbol, height=280, showlegend=False,
        xaxis={'domain': [domain_left, domain_right]},
        margin={'t': 30, 'l': 50, 'r': 50, 'b': 30},
    )
    return fig


def make_field_table(record):
    """One row per field selected in the query config's `fields` list, for this symbol's record."""
    rows = [
        html.Tr([
            html.Td(str(field), style={'fontWeight': 'bold', 'paddingRight': '8px', 'verticalAlign': 'top'}),
            html.Td(str(value)),
        ], style={'backgroundColor': '#f2f2f2' if i % 2 == 0 else 'transparent'})
        for i, (field, value) in enumerate(record.items())
    ]
    return html.Table(rows, style={
        'fontSize': '11px', 'width': '100%', 'borderCollapse': 'collapse', 'marginTop': '4px',
    })


def render_charts(order, cache: HistoryContext, period, interval, value_fields, symbol_records=None):
    """Ensures every symbol in `order` has its full history in `cache` (fetching on first
    sight), then returns (list of panels, status message) for whichever symbols have data.

    Each panel plots every field in `value_fields` together by default; if there's more than
    one, a checkbox row lets you turn individual fields off/on for that chart."""
    symbol_records = symbol_records or {}
    panels = []
    fetched_this_update = []

    for symbol in order:
        if symbol not in cache.dataframes:
            if cache.fetch_history_frame(symbol, period, interval) is not None:
                fetched_this_update.append(symbol)

        history = cache.dataframes[symbol]
        if history is None:
            continue

        fig = make_multi_field_figure(symbol, history, value_fields)

        panel_children = []
        if len(value_fields) > 1:
            panel_children.append(dcc.Checklist(
                id={'type': 'field-checklist', 'index': symbol},
                options=[{'label': f' {field}', 'value': field} for field in value_fields],
                value=list(value_fields),
                inline=True,
                labelStyle={'marginRight': '10px', 'fontSize': '11px'},
            ))

        panel_children.append(html.Div([
            html.Button(label, id={'type': 'analysis-button', 'index': symbol, 'name': name}, n_clicks=0,
                        style={'fontSize': '11px'})
            for name, (label, _func) in ANALYSIS_FUNCTIONS.items()
        ], style={'display': 'flex', 'gap': '6px', 'margin': '4px 0'}))

        panel_children.append(dcc.Store(id={'type': 'active-fields', 'index': symbol}, data=list(value_fields)))
        panel_children.extend(
            dcc.Store(id={'type': 'highlight-flag', 'index': symbol, 'name': name}, data=False)
            for name in ANALYSIS_FUNCTIONS
        )
        panel_children.append(dcc.Graph(id={'type': 'panel-graph', 'index': symbol}, figure=fig))

        record = symbol_records.get(symbol)
        if record:
            panel_children.append(make_field_table(record))

        panels.append(html.Div(panel_children, style={
            'border': '1px solid #eee', 'borderRadius': '6px', 'padding': '4px',
        }))

    status = (f'{len(order)} checked, {len(fetched_this_update)} fetched this update, '
              f'{len(cache.dataframes)} cached total')
    logger.info(status)
    return panels, status


def build_app(symbols, period='6mo', interval='1d', value_fields=None, symbol_records=None):
    value_fields = value_fields or ['Close']
    app = Dash(__name__)
    hcontext = HistoryContext()
    groups = _chunk(symbols, CHECKLIST_GROUP_SIZE)

    group_sections = []
    for i, group in enumerate(groups):
        first = i * CHECKLIST_GROUP_SIZE + 1
        last = first + len(group) - 1
        group_sections.append(html.Details([
            html.Summary(f'{first}-{last} ({len(group)})', style={
                'cursor': 'pointer', 'fontWeight': 'bold', 'fontSize': '13px', 'padding': '4px 0',
            }),
            dcc.Checklist(
                id={'type': 'group-checklist', 'index': i},
                options=[{'label': f' {symbol}', 'value': symbol} for symbol in group],
                value=[],
                labelStyle={'display': 'block', 'fontSize': '13px', 'padding': '2px 0'},
            ),
        ], open=(i == 0), style={'marginBottom': '8px'}))

    sidebar = html.Div(group_sections, style={
        'flex': f'0 0 {SIDEBAR_WIDTH}',
        'maxHeight': '85vh',
        'overflowY': 'auto',
        'border': '1px solid #ddd',
        'borderRadius': '6px',
        'padding': '10px',
        'boxSizing': 'border-box',
    })

    main_area = html.Div([
        html.Div(id='status', style={'color': '#666', 'fontSize': '12px', 'margin': '0 0 10px 0'}),
        html.Div(id='chart-grid', style={
            'display': 'grid',
            'gridTemplateColumns': f'repeat({GRID_COLUMNS}, minmax(0, 1fr))',
            'gap': '12px',
        }),
    ], style={'flex': '1 1 auto', 'minWidth': 0})

    app.layout = html.Div([
        html.H2('Ticker time series (live)'),
        html.P('Check a ticker to fetch it and add its chart to the grid. '
               'Fetching only happens the first time a ticker is checked.'),
        dcc.Store(id='checked-order', data=[]),
        html.Div([sidebar, main_area], style={
            'display': 'flex', 'alignItems': 'flex-start', 'gap': '16px', 'maxWidth': '100%',
        }),
    ], style={'fontFamily': 'sans-serif', 'margin': '16px', 'boxSizing': 'border-box'})

    @app.callback(
        Output('checked-order', 'data'),
        Input({'type': 'group-checklist', 'index': ALL}, 'value'),
        State('checked-order', 'data'),
    )
    def on_checklist_change(checked_lists, order):
        checked = [symbol for group_values in checked_lists for symbol in (group_values or [])]
        new_order = compute_check_order(checked, order)
        logger.info('checklist changed -> order=%s', new_order)
        return new_order

    @app.callback(
        Output('chart-grid', 'children'),
        Output('status', 'children'),
        Input('checked-order', 'data'),
    )
    def on_order_change(order):
        return render_charts(order or [], hcontext, period, interval, value_fields, symbol_records)

    if len(value_fields) > 1:
        @app.callback(
            Output({'type': 'active-fields', 'index': MATCH}, 'data'),
            Input({'type': 'field-checklist', 'index': MATCH}, 'value'),
            prevent_initial_call=True,
        )
        def on_field_checklist_change(checked_fields):
            return [field for field in value_fields if field in (checked_fields or [])]

    @app.callback(
        Output({'type': 'highlight-flag', 'index': MATCH, 'name': MATCH}, 'data'),
        Output({'type': 'analysis-button', 'index': MATCH, 'name': MATCH}, 'children'),
        Input({'type': 'analysis-button', 'index': MATCH, 'name': MATCH}, 'n_clicks'),
        State({'type': 'analysis-button', 'index': MATCH, 'name': MATCH}, 'id'),
        prevent_initial_call=True,
    )
    def on_analysis_button_click(n_clicks, button_id):
        name = button_id['name']
        label, _func = ANALYSIS_FUNCTIONS[name]
        active = bool(n_clicks % 2)
        logger.info('%s: %s %s', button_id['index'], label, 'on' if active else 'off')
        return active, (f'Remove: {label}' if active else label)

    @app.callback(
        Output({'type': 'panel-graph', 'index': MATCH}, 'figure'),
        Input({'type': 'active-fields', 'index': MATCH}, 'data'),
        Input({'type': 'highlight-flag', 'index': MATCH, 'name': ALL}, 'data'),
        State({'type': 'highlight-flag', 'index': MATCH, 'name': ALL}, 'id'),
        State({'type': 'active-fields', 'index': MATCH}, 'id'),
        prevent_initial_call=True,
    )
    def on_panel_redraw(active_fields, highlight_flags, highlight_ids, active_fields_id):
        symbol = active_fields_id['index']
        history = hcontext.dataframes[symbol]
        active_highlights = {
            hid['name']: ANALYSIS_FUNCTIONS[hid['name']][1]
            for hid, flag in zip(highlight_ids, highlight_flags) if flag
        }
        return make_multi_field_figure(symbol, history, active_fields or [], active_highlights=active_highlights)

    return app


def run(symbols, period='6mo', interval='1d', value_fields=None,
        host='127.0.0.1', port=8050, debug=True, symbol_records=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    app = build_app(symbols, period=period, interval=interval, value_fields=value_fields,
                     symbol_records=symbol_records)
    print(f'DASHBOARD READY at http://{host}:{port}/', flush=True)
    app.run(host=host, port=port, debug=debug, use_reloader=False)
