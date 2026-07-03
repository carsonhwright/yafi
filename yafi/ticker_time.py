import argparse
import json
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

DEFAULT_LIMIT = None


def load_symbol_records(results_path, symbol_field='symbol', limit=DEFAULT_LIMIT):
    """Maps each symbol to its full record from the results JSON (every field that was
    selected in the query config's `fields` list), preserving first-seen order."""
    with open(results_path, 'r', encoding='utf-8') as f:
        records = json.load(f)

    symbol_records = {}
    for record in records:
        symbol = record.get(symbol_field)
        if symbol and symbol not in symbol_records:
            symbol_records[symbol] = record
        if limit is not None and len(symbol_records) >= limit:
            break
    return symbol_records


def load_symbols(results_path, symbol_field='symbol', limit=DEFAULT_LIMIT):
    return list(load_symbol_records(results_path, symbol_field, limit))

# TODO is the period value configurable?
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


def build_dataframe(series):
    df = pd.DataFrame(series)
    df.index = df.index.tz_localize(None)
    return df


def plot_matplotlib(df, value_field, output_path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 6))
    for symbol in df.columns:
        ax.plot(df.index, df[symbol], label=symbol)

    ax.set_xlabel('Date')
    ax.set_ylabel(value_field)
    ax.set_title('Ticker time series')
    ax.legend(loc='upper left', ncol=2, fontsize='small')
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path)
        print(f"saved plot to {output_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(description='Plot historical time series for tickers found in a results JSON.')
    parser.add_argument('results_path', nargs='?', default=str(Path(__file__).parent / 'output/results.json'),
                         help='Path to a results JSON produced by query_machine.py.')
    parser.add_argument('--symbol-field', default='symbol', help='Key holding the ticker symbol in each record.')
    parser.add_argument('--symbols', help='Comma-separated symbols to plot instead of reading the results JSON.')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT,
                         help='Max number of tickers to plot (default: no limit, plot every symbol found).')
    parser.add_argument('--period', default='6mo', help='yfinance history period (e.g. 1mo, 6mo, 1y, 5y, max).')
    parser.add_argument('--interval', default='1d', help='yfinance history interval (e.g. 1d, 1wk, 1mo).')
    parser.add_argument('--value-field', default='Close', choices=['Open', 'High', 'Low', 'Close', 'Volume'])
    parser.add_argument('--engine', choices=['matplotlib', 'dash'], default='matplotlib',
                         help='matplotlib for a quick static plot, dash for a live dashboard that '
                              'fetches each ticker only when you check it.')
    parser.add_argument('--output', help='matplotlib only: save to this .png instead of opening a window. '
                                          'Ignored for --engine dash, which always serves live.')
    parser.add_argument('--request-delay-seconds', type=float, default=0.3,
                         help='matplotlib only: delay between eager per-ticker fetches.')
    parser.add_argument('--port', type=int, default=8050, help='dash only: port to serve the dashboard on.')
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
        symbol_records = {}
    else:
        symbol_records = load_symbol_records(args.results_path, args.symbol_field, args.limit)
        symbols = list(symbol_records)

    if not symbols:
        raise ValueError('No symbols to plot.')
    print(f"tickers: {', '.join(symbols)}")

    if args.engine == 'dash':
        import dashboard

        if args.output:
            print("note: --output is ignored for --engine dash (there's no file, just a live server)")
        dashboard.run(symbols, period=args.period, interval=args.interval, value_field=args.value_field,
                      port=args.port, symbol_records=symbol_records)
        return

    series = fetch_history(symbols, period=args.period, interval=args.interval,
                            value_field=args.value_field, delay=args.request_delay_seconds)
    if not series:
        raise ValueError('No historical data fetched for any symbol.')

    df = build_dataframe(series)
    plot_matplotlib(df, args.value_field, args.output)


if __name__ == '__main__':
    main()
