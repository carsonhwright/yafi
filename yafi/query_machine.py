import argparse
import csv
import json
import time
from pathlib import Path

import yfinance as yf

QUOTE_TYPE_MAP = {
    'equity': yf.EquityQuery,
    'fund': yf.FundQuery,
    'etf': yf.ETFQuery,
}

YAHOO_MAX_PAGE_SIZE = 250


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_query(node, query_cls):
    operator = node['operator']
    operands = node['operands']
    if all(isinstance(o, dict) for o in operands):
        operands = [build_query(o, query_cls) for o in operands]
    return query_cls(operator, operands)


def fetch_all(query, sort_field=None, sort_asc=False, page_size=YAHOO_MAX_PAGE_SIZE,
              max_results=None, delay=0.5):
    page_size = min(page_size, YAHOO_MAX_PAGE_SIZE)
    offset = 0
    quotes = []
    total = None

    while True:
        size = page_size
        if max_results is not None:
            size = min(size, max_results - len(quotes))
            if size <= 0:
                break

        resp = yf.screen(query, offset=offset, size=size, sortField=sort_field, sortAsc=sort_asc)
        page = resp.get('quotes', [])
        total = resp.get('total', total)
        if not page:
            break

        quotes.extend(page)
        offset += len(page)
        print(f"fetched {len(page)} (offset={offset}, {len(quotes)}/{total} total)")

        if total is not None and offset >= total:
            break
        if max_results is not None and len(quotes) >= max_results:
            break
        time.sleep(delay)

    return quotes


def extract_fields(quotes, fields):
    if not fields:
        return quotes
    return [{field: quote.get(field) for field in fields} for quote in quotes]


def write_json(records, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, default=str)


def write_csv(records, path, fields):
    fieldnames = fields or (list(records[0].keys()) if records else [])
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore', restval='')
        writer.writeheader()
        writer.writerows(records)


def write_output(records, output_config, fields):
    fmt = output_config.get('format', 'json').lower()
    path = Path(output_config.get('path', 'results.json'))

    if fmt in ('json', 'both'):
        write_json(records, path.with_suffix('.json') if fmt == 'both' else path)
    if fmt in ('csv', 'both'):
        write_csv(records, path.with_suffix('.csv') if fmt == 'both' else path, fields)


def main():
    parser = argparse.ArgumentParser(description='Run a JSON-configured yfinance screener query.')
    parser.add_argument('config', nargs='?', default='query_config.json',
                         help='Path to the JSON query config file.')
    args = parser.parse_args()

    config = load_config(Path("configs") / args.config)

    quote_type = config.get('quote_type', 'equity').lower()
    query_cls = QUOTE_TYPE_MAP.get(quote_type)
    if query_cls is None:
        raise ValueError(f"Unsupported quote_type '{quote_type}', expected one of {list(QUOTE_TYPE_MAP)}")

    query = build_query(config['query'], query_cls)

    quotes = fetch_all(
        query,
        sort_field=config.get('sort_field'),
        sort_asc=config.get('sort_asc', False),
        page_size=config.get('page_size', YAHOO_MAX_PAGE_SIZE),
        max_results=config.get('max_results'),
        delay=config.get('request_delay_seconds', 0.5),
    )

    fields = config.get('fields')
    records = extract_fields(quotes, fields)

    output_config = config.get('output', {})
    write_output(records, output_config, fields)

    print(f"done: {len(records)} results written to {output_config.get('path', 'results.json')}")


if __name__ == '__main__':
    main()
