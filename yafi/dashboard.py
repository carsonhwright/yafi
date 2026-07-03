import logging
import time

import plotly.graph_objects as go
import yfinance as yf
from dash import ALL, Dash, Input, Output, State, dcc, html

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


def fetch_series(symbol, period, interval, value_field):
    logger.info('fetching %s (period=%s interval=%s)', symbol, period, interval)
    start = time.monotonic()
    history = yf.Ticker(symbol).history(period=period, interval=interval)
    elapsed = time.monotonic() - start

    if history.empty or value_field not in history:
        logger.warning('no %s data for %s (%.2fs)', value_field, symbol, elapsed)
        return None

    logger.info('fetched %s: %d rows in %.2fs', symbol, len(history), elapsed)
    return history[value_field]


def make_figure(symbol, series, value_field):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode='lines', name=symbol))
    fig.update_layout(
        title=symbol, height=260, showlegend=False,
        margin={'t': 30, 'l': 45, 'r': 10, 'b': 30},
        yaxis_title=value_field,
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


def render_charts(order, cache, period, interval, value_field, symbol_records=None):
    """Ensures every symbol in `order` is in `cache` (fetching on first sight), then
    returns (list of graph+table panels, status message) for whichever symbols have data."""
    symbol_records = symbol_records or {}
    panels = []
    fetched_this_update = []

    for symbol in order:
        if symbol not in cache:
            cache[symbol] = fetch_series(symbol, period, interval, value_field)
            if cache[symbol] is not None:
                fetched_this_update.append(symbol)

        series = cache[symbol]
        if series is None:
            continue

        fig = make_figure(symbol, series, value_field)
        panel_children = [dcc.Graph(figure=fig)]
        record = symbol_records.get(symbol)
        if record:
            panel_children.append(make_field_table(record))
        panels.append(html.Div(panel_children, style={
            'border': '1px solid #eee', 'borderRadius': '6px', 'padding': '4px',
        }))

    status = (f'{len(order)} checked, {len(fetched_this_update)} fetched this update, '
              f'{len(cache)} cached total')
    logger.info(status)
    return panels, status


def build_app(symbols, period='6mo', interval='1d', value_field='Close', symbol_records=None):
    app = Dash(__name__)
    history_cache = {}
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
        return render_charts(order or [], history_cache, period, interval, value_field, symbol_records)

    return app


def run(symbols, period='6mo', interval='1d', value_field='Close',
        host='127.0.0.1', port=8050, debug=True, symbol_records=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    app = build_app(symbols, period=period, interval=interval, value_field=value_field,
                     symbol_records=symbol_records)
    print(f'DASHBOARD READY at http://{host}:{port}/', flush=True)
    app.run(host=host, port=port, debug=debug, use_reloader=False)
