import argparse
import json
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

DEFAULT_LIMIT = 10


def load_symbols(results_path, symbol_field='symbol', limit=DEFAULT_LIMIT):
    with open(results_path, 'r', encoding='utf-8') as f:
        records = json.load(f)

    symbols = []
    for record in records:
        symbol = record.get(symbol_field)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        if limit is not None and len(symbols) >= limit:
            break
    return symbols


def fetch_history(symbols, period='6mo', interval='1d', value_field='Close', delay=0.3):
    series = {}
    for symbol in symbols:
        history = yf.Ticker(symbol).history(period=period, interval=interval)
        if history.empty or value_field not in history:
            print(f"skipping {symbol}: no {value_field} data for period={period} interval={interval}")
            continue
        series[symbol] = history[value_field]
        print(f"fetched {symbol}: {len(history)} rows")
        time.sleep(delay)
    return series


def build_dataframe(series, normalize=True):
    df = pd.DataFrame(series)
    df.index = df.index.tz_localize(None)
    if normalize:
        df = df / df.bfill().iloc[0] * 100
    return df


def plot_matplotlib(df, value_field, normalize, output_path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 6))
    for symbol in df.columns:
        ax.plot(df.index, df[symbol], label=symbol)

    ax.set_xlabel('Date')
    ax.set_ylabel(f'{value_field} (indexed to 100)' if normalize else value_field)
    ax.set_title('Ticker time series')
    ax.legend(loc='upper left', ncol=2, fontsize='small')
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path)
        print(f"saved plot to {output_path}")
    else:
        plt.show()


def plot_plotly(df, value_field, normalize, output_path):
    import plotly.graph_objects as go

    fig = go.Figure()
    for symbol in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df[symbol], mode='lines', name=symbol))

    fig.update_layout(
        title='Ticker time series',
        xaxis_title='Date',
        yaxis_title=f'{value_field} (indexed to 100)' if normalize else value_field,
        legend_title='Symbol',
        hovermode='x unified',
        template='plotly_white',
    )
    fig.update_xaxes(rangeslider_visible=True)

    if output_path:
        fig.write_html(output_path, include_plotlyjs='cdn')
        print(f"saved dashboard to {output_path}")
    else:
        fig.show()


def main():
    parser = argparse.ArgumentParser(description='Plot historical time series for tickers found in a results JSON.')
    parser.add_argument('results_path', nargs='?', default=str(Path(__file__).parent / 'output/results.json'),
                         help='Path to a results JSON produced by query_machine.py.')
    parser.add_argument('--symbol-field', default='symbol', help='Key holding the ticker symbol in each record.')
    parser.add_argument('--symbols', help='Comma-separated symbols to plot instead of reading the results JSON.')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, help='Max number of tickers to plot.')
    parser.add_argument('--period', default='6mo', help='yfinance history period (e.g. 1mo, 6mo, 1y, 5y, max).')
    parser.add_argument('--interval', default='1d', help='yfinance history interval (e.g. 1d, 1wk, 1mo).')
    parser.add_argument('--value-field', default='Close', choices=['Open', 'High', 'Low', 'Close', 'Volume'])
    parser.add_argument('--no-normalize', action='store_true',
                         help='Plot raw values instead of indexing each series to 100 at its start.')
    parser.add_argument('--engine', choices=['matplotlib', 'plotly'], default='matplotlib',
                         help='matplotlib for a quick static plot, plotly for an interactive dashboard.')
    parser.add_argument('--output', help='Save to this file instead of opening a window/browser '
                                          '(.png for matplotlib, .html for plotly).')
    parser.add_argument('--request-delay-seconds', type=float, default=0.3)
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    else:
        symbols = load_symbols(args.results_path, args.symbol_field, args.limit)

    if not symbols:
        raise ValueError('No symbols to plot.')
    print(f"tickers: {', '.join(symbols)}")

    series = fetch_history(symbols, period=args.period, interval=args.interval,
                            value_field=args.value_field, delay=args.request_delay_seconds)
    if not series:
        raise ValueError('No historical data fetched for any symbol.')

    df = build_dataframe(series, normalize=not args.no_normalize)

    if args.engine == 'matplotlib':
        plot_matplotlib(df, args.value_field, not args.no_normalize, args.output)
    else:
        plot_plotly(df, args.value_field, not args.no_normalize, args.output)


if __name__ == '__main__':
    main()
