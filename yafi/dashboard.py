import logging
import time

import plotly.graph_objects as go
import yfinance as yf
from dash import ALL, MATCH, Dash, Input, Output, State, dcc, html

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


def fetch_history_frame(symbol, period, interval):
    """Fetches the full OHLCV history once, so any combination of Open/High/Low/Close/Volume
    can be plotted from cache afterward without refetching when checkboxes are toggled."""
    logger.info('fetching %s (period=%s interval=%s)', symbol, period, interval)
    start = time.monotonic()
    history = yf.Ticker(symbol).history(period=period, interval=interval)
    elapsed = time.monotonic() - start

    if history.empty:
        logger.warning('no data for %s (%.2fs)', symbol, elapsed)
        return None

    logger.info('fetched %s: %d rows in %.2fs', symbol, len(history), elapsed)
    return history


def make_multi_field_figure(symbol, history, fields):
    """Plots every field in `fields` as its own trace with its own y-axis, each axis colored
    to match its trace (first field on the left, second on the right, further ones stacked
    further out on alternating sides) so differently-scaled fields (e.g. Close vs Volume)
    stay individually readable while still being visually comparable on one chart."""
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

        fig.add_trace(go.Scatter(
            x=series.index, y=series.values, mode='lines', name=field,
            line={'color': color}, yaxis='y' + suffix,
        ))

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


def render_charts(order, cache, period, interval, value_fields, symbol_records=None):
    """Ensures every symbol in `order` has its full history in `cache` (fetching on first
    sight), then returns (list of panels, status message) for whichever symbols have data.

    Each panel plots every field in `value_fields` together by default; if there's more than
    one, a checkbox row lets you turn individual fields off/on for that chart."""
    symbol_records = symbol_records or {}
    panels = []
    fetched_this_update = []

    for symbol in order:
        if symbol not in cache:
            cache[symbol] = fetch_history_frame(symbol, period, interval)
            if cache[symbol] is not None:
                fetched_this_update.append(symbol)

        history = cache[symbol]
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
        panel_children.append(dcc.Graph(id={'type': 'panel-graph', 'index': symbol}, figure=fig))

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


def build_app(symbols, period='6mo', interval='1d', value_fields=None, symbol_records=None):
    value_fields = value_fields or ['Close']
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
        return render_charts(order or [], history_cache, period, interval, value_fields, symbol_records)

    if len(value_fields) > 1:
        @app.callback(
            Output({'type': 'panel-graph', 'index': MATCH}, 'figure'),
            Input({'type': 'field-checklist', 'index': MATCH}, 'value'),
            State({'type': 'field-checklist', 'index': MATCH}, 'id'),
            prevent_initial_call=True,
        )
        def on_field_checklist_change(checked_fields, checklist_id):
            symbol = checklist_id['index']
            history = history_cache[symbol]
            ordered_fields = [field for field in value_fields if field in (checked_fields or [])]
            logger.info('%s: now plotting %s', symbol, ordered_fields)
            return make_multi_field_figure(symbol, history, ordered_fields)

    return app


def run(symbols, period='6mo', interval='1d', value_fields=None,
        host='127.0.0.1', port=8050, debug=True, symbol_records=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    app = build_app(symbols, period=period, interval=interval, value_fields=value_fields,
                     symbol_records=symbol_records)
    print(f'DASHBOARD READY at http://{host}:{port}/', flush=True)
    app.run(host=host, port=port, debug=debug, use_reloader=False)
