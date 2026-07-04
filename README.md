# yafi

JSON-configurable [yfinance](https://github.com/ranaroussi/yfinance) screener. Point it at a config file describing a query tree, and it paginates through all matching results and writes them to JSON/CSV.

## Setup

Requires Python 3.10+.

### Option 1: local dev environment (recommended for working on this repo)

Run the setup script for your shell. Both create a `.yafi-venv` virtual environment at the repo root and install everything from `requirements.txt`.

**Windows (PowerShell):**
```powershell
.\scripts\setup.ps1
```

**macOS/Linux/Git Bash:**
```bash
./scripts/setup.sh
```

Then activate it:
```powershell
.\.yafi-venv\Scripts\Activate.ps1   # PowerShell
```
```bash
source .yafi-venv/Scripts/activate  # Git Bash on Windows
source .yafi-venv/bin/activate      # macOS/Linux
```

Override the venv location or Python interpreter with the `VENV_DIR` / `PYTHON_BIN` environment variables if needed.

### Option 2: install as a package

```bash
pip install .          # regular install
pip install -e .       # editable/dev install
```

This installs `yafi` and its one runtime dependency (`yfinance`), and exposes a `yafi` console command (`yafi.query_machine:main`).

## Usage

```bash
python yafi/query_machine.py                       # uses yafi/configs/query_config.json
python yafi/query_machine.py path/to/other.json     # uses a custom config
yafi path/to/other.json                             # same, if installed as a package
```

**Note:** `output.path` in the config (see below) is resolved relative to the current working directory, not the script location. Run from the `yafi/` directory (as the VS Code launch configs do) so `output/results.json` lands in `yafi/output/`.

## Config file reference

```json
{
  "quote_type": "equity",
  "query": {
    "operator": "and",
    "operands": [
      {"operator": "lt", "operands": ["peratio.lasttwelvemonths", 20]},
      {"operator": "is-in", "operands": ["exchange", "NMS", "NYQ"]},
      {"operator": "gt", "operands": ["intradaymarketcap", 15000000000]}
    ]
  },
  "sort_field": "peratio.lasttwelvemonths",
  "sort_asc": true,
  "page_size": 250,
  "max_results": null,
  "request_delay_seconds": 0.5,
  "fields": ["symbol", "trailingPE", "forwardPE", "exchange", "marketCap", "longName"],
  "output": {
    "format": "json",
    "path": "output/results.json"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `quote_type` | string | One of `equity`, `fund`, `etf`. Selects the query/field universe (see below). |
| `query` | object | The filter tree. See **Query operators**. |
| `sort_field` | string \| null | Field to sort results by. |
| `sort_asc` | bool | Sort ascending if `true`, descending if `false` (default `false`). |
| `page_size` | int | Results requested per page. Clamped to Yahoo's max of 250. |
| `max_results` | int \| null | Stop after this many results. `null` fetches everything matching the query. |
| `request_delay_seconds` | float | Delay between paginated requests, to avoid rate limiting. |
| `fields` | array \| null | Keys to keep from each raw quote. `null`/omitted keeps every field Yahoo returns. |
| `output.format` | string | `json`, `csv`, or `both`. |
| `output.path` | string | Output file path (relative to cwd). With `format: "both"`, `.json`/`.csv` extensions are applied automatically. |

Note the two "vocabularies" at play: fields inside `query` use Yahoo's internal **query field names** (e.g. `intradaymarketcap`, `peratio.lasttwelvemonths`) — see **`quote_type` values and their query fields** below. Fields listed in the top-level `fields` array are **response keys** from the returned quote object (e.g. `marketCap`, `trailingPE`) — a different vocabulary, documented in **Output fields** below.

## Output fields (what goes in `results.json`)

The `fields` array picks keys out of Yahoo's raw quote object — the same object you'd get back with `fields` omitted entirely. Unlike the query fields above, **this is not a fixed schema**: Yahoo only includes a key when it has data for it, so the exact set varies by ticker and by `quote_type` (e.g. a foreign-listed stock may lack `forwardPE`; a mutual fund has no `bid`/`ask`). Treat the tables below as "commonly present, sampled from real responses," not a guarantee.

To see the full, ungapped set of fields available for your specific query, run it once with `"fields": null` and inspect the keys of the resulting objects in `results.json`.

### `equity` — commonly available fields (sampled from 50 quotes)

| Field | Type | Example |
|---|---|---|
| `symbol`, `shortName`, `longName`, `exchange`, `fullExchangeName`, `region`, `currency`, `financialCurrency` | str | `'NVDA'`, `'NVIDIA Corporation'`, `'NMS'` |
| `quoteType`, `typeDisp`, `market`, `marketState`, `quoteSourceName` | str | `'EQUITY'`, `'REGULAR'` |
| `regularMarketPrice`, `regularMarketOpen`, `regularMarketDayHigh`, `regularMarketDayLow`, `regularMarketPreviousClose` | float | `651000.0` |
| `regularMarketChange`, `regularMarketChangePercent`, `regularMarketVolume`, `regularMarketTime` | float/int | `-23000.0` |
| `regularMarketDayRange`, `fiftyTwoWeekRange` | str | `'651000.0 - 668000.0'` |
| `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`, `fiftyTwoWeekChangePercent`, `fiftyTwoWeekHighChange`, `fiftyTwoWeekLowChange`, `fiftyTwoWeekHighChangePercent`, `fiftyTwoWeekLowChangePercent` | float | `894740.0` |
| `fiftyDayAverage`, `fiftyDayAverageChange`, `fiftyDayAverageChangePercent`, `twoHundredDayAverage`, `twoHundredDayAverageChange`, `twoHundredDayAverageChangePercent` | float | `757424.8` |
| `marketCap`, `sharesOutstanding`, `impliedSharesOutstanding`, `bookValue`, `priceToBook` | int/float | `41229283328` |
| `trailingPE`, `forwardPE`, `epsTrailingTwelveMonths`, `epsForward`, `epsCurrentYear`, `priceEpsCurrentYear` | float | `17.327188` |
| `dividendRate`, `dividendYield`, `trailingAnnualDividendRate`, `trailingAnnualDividendYield` | float | `1.1` |
| `averageAnalystRating` | str | `'1.4 - Strong Buy'` |
| `bid`, `ask`, `bidSize`, `askSize` | float/int | `37.6` |
| `averageDailyVolume10Day`, `averageDailyVolume3Month` | int | `214` |
| `earningsTimestamp`, `earningsTimestampStart`, `earningsTimestampEnd`, `earningsCallTimestampStart`, `earningsCallTimestampEnd`, `isEarningsDateEstimate` | int/bool | `1779307200` |
| `firstTradeDateMilliseconds`, `sourceInterval`, `exchangeDataDelayedBy`, `priceHint`, `gmtOffSetMilliseconds` | int | `1305525600000` |
| `exchangeTimezoneName`, `exchangeTimezoneShortName`, `messageBoardId` | str | `'America/New_York'` |
| `esgPopulated`, `tradeable`, `cryptoTradeable`, `hasPrePostMarketData`, `triggerable` | bool | `False` |
| `customPriceAlertConfidence`, `corporateActions` | str/list | `'LOW'`, `[]` |

### `fund` — commonly available fields (sampled from 5 quotes)

Mostly overlaps with the equity list above (`symbol`, `longName`, `exchange`, `regularMarket*`, `fiftyTwoWeek*`, `fiftyDayAverage*`, `twoHundredDayAverage*`, `trailingPE`, `dividendRate`/`dividendYield`), plus fund-specific fields:

| Field | Type | Example |
|---|---|---|
| `netAssets` | float | `123196336.0` |
| `netExpenseRatio` | float | `1.0` |
| `ytdReturn` | float | `6.43178` |
| `trailingThreeMonthReturns` | float | `16.33497` |
| `quoteType` | str | `'MUTUALFUND'` |

### `etf` — commonly available fields (sampled from 5 quotes)

Also mostly overlaps with the equity list (including `bid`/`ask` and `trailingPE`, unlike funds), plus:

| Field | Type | Example |
|---|---|---|
| `netAssets` | float | `142385936.0` |
| `ytdReturn` | float | `10.08174` |
| `trailingThreeMonthReturns`, `trailingThreeMonthNavReturns` | float | `3.2812` |
| `dividendDate` | int | `1617580800` |
| `quoteType` | str | `'ETF'` |

## Query operators

Each query node is `{"operator": "...", "operands": [...]}`.

| Operator | Operand shape | Meaning |
|---|---|---|
| `and` | `[query, query, ...]` (2+ nested query nodes) | All subqueries must match. |
| `or` | `[query, query, ...]` (2+ nested query nodes) | Any subquery must match. |
| `eq` | `[field, value]` | Field equals value. |
| `gt` | `[field, number]` | Field greater than value. |
| `lt` | `[field, number]` | Field less than value. |
| `gte` | `[field, number]` | Field greater than or equal to value. |
| `lte` | `[field, number]` | Field less than or equal to value. |
| `btwn` | `[field, low, high]` | Field between low and high (inclusive), both numeric. |
| `is-in` | `[field, value1, value2, ...]` | Field equals any of the given values (expands to an `or` of `eq`). |

`and`/`or` operands are nested query objects; every other operator's operands are `[field_name, ...values]`.

## `quote_type` values and their query fields

### `equity`

| Category | Fields |
|---|---|
| eq_fields (constrained values — see below) | `exchange`, `industry`, `peer_group`, `region`, `sector` |
| price | `eodprice`, `fiftytwowkpercentchange`, `intradaymarketcap`, `intradayprice`, `intradaypricechange`, `lastclose52weekhigh.lasttwelvemonths`, `lastclose52weeklow.lasttwelvemonths`, `lastclosemarketcap.lasttwelvemonths`, `percentchange` |
| trading | `avgdailyvol3m`, `beta`, `dayvolume`, `eodvolume`, `pctheldinsider`, `pctheldinst` |
| short_interest | `days_to_cover_short.value`, `short_interest.value`, `short_interest_percentage_change.value`, `short_percentage_of_float.value`, `short_percentage_of_shares_outstanding.value` |
| valuation | `bookvalueshare.lasttwelvemonths`, `lastclosemarketcaptotalrevenue.lasttwelvemonths`, `lastclosepriceearnings.lasttwelvemonths`, `lastclosepricetangiblebookvalue.lasttwelvemonths`, `lastclosetevtotalrevenue.lasttwelvemonths`, `pegratio_5y`, `peratio.lasttwelvemonths`, `pricebookratio.quarterly` |
| profitability | `consecutive_years_of_dividend_growth_count`, `forward_dividend_per_share`, `forward_dividend_yield`, `returnonassets.lasttwelvemonths`, `returnonequity.lasttwelvemonths`, `returnontotalcapital.lasttwelvemonths` |
| leverage | `ebitdainterestexpense.lasttwelvemonths`, `ebitinterestexpense.lasttwelvemonths`, `lastclosetevebit.lasttwelvemonths`, `lastclosetevebitda.lasttwelvemonths`, `ltdebtequity.lasttwelvemonths`, `netdebtebitda.lasttwelvemonths`, `totaldebtebitda.lasttwelvemonths`, `totaldebtequity.lasttwelvemonths` |
| liquidity | `altmanzscoreusingtheaveragestockinformationforaperiod.lasttwelvemonths`, `currentratio.lasttwelvemonths`, `operatingcashflowtocurrentliabilities.lasttwelvemonths`, `quickratio.lasttwelvemonths` |
| income_statement | `basicepscontinuingoperations.lasttwelvemonths`, `dilutedeps1yrgrowth.lasttwelvemonths`, `dilutedepscontinuingoperations.lasttwelvemonths`, `ebit.lasttwelvemonths`, `ebitda.lasttwelvemonths`, `ebitda1yrgrowth.lasttwelvemonths`, `ebitdamargin.lasttwelvemonths`, `epsgrowth.lasttwelvemonths`, `grossprofit.lasttwelvemonths`, `grossprofitmargin.lasttwelvemonths`, `netepsbasic.lasttwelvemonths`, `netepsdiluted.lasttwelvemonths`, `netincome1yrgrowth.lasttwelvemonths`, `netincomeis.lasttwelvemonths`, `netincomemargin.lasttwelvemonths`, `operatingincome.lasttwelvemonths`, `quarterlyrevenuegrowth.quarterly`, `totalrevenues.lasttwelvemonths`, `totalrevenues1yrgrowth.lasttwelvemonths` |
| balance_sheet | `totalassets.lasttwelvemonths`, `totalcashandshortterminvestments.lasttwelvemonths`, `totalcommonequity.lasttwelvemonths`, `totalcommonsharesoutstanding.lasttwelvemonths`, `totalcurrentassets.lasttwelvemonths`, `totalcurrentliabilities.lasttwelvemonths`, `totaldebt.lasttwelvemonths`, `totalequity.lasttwelvemonths`, `totalsharesoutstanding` |
| cash_flow | `capitalexpenditure.lasttwelvemonths`, `cashfromoperations.lasttwelvemonths`, `cashfromoperations1yrgrowth.lasttwelvemonths`, `forward_dividend_yield`, `leveredfreecashflow.lasttwelvemonths`, `leveredfreecashflow1yrgrowth.lasttwelvemonths`, `unleveredfreecashflow.lasttwelvemonths` |
| esg | `environmental_score`, `esg_score`, `governance_score`, `highest_controversy`, `social_score` |

### `fund`

| Category | Fields |
|---|---|
| eq_fields (constrained values) | `annualreturnnavy1categoryrank`, `categoryname`, `exchange`, `initialinvestment`, `performanceratingoverall`, `riskratingoverall` |
| price | `eodprice`, `intradayprice`, `intradaypricechange` |

### `etf`

| Category | Fields |
|---|---|
| eq_fields (constrained values) | `categoryname`, `exchange`, `fundfamilyname`, `morningstar_economic_moat`, `morningstar_moat_trend`, `morningstar_rating_change`, `morningstar_stewardship`, `morningstar_uncertainty`, `primary_sector`, `region` |
| fundamentals | `fundnetassets`, `ticker` |
| feesandexpenses | `annualreportgrossexpenseratio`, `annualreportnetexpenseratio`, `turnoverratio` |
| historicalperformance | `annualreturnnavy1`, `annualreturnnavy1categoryrank`, `annualreturnnavy3`, `annualreturnnavy5` |
| keystats | `avgdailyvol3m`, `dayvolume`, `eodvolume`, `fiftytwowkpercentchange`, `percentchange` |
| morningstar_rating | `morningstar_last_close_price_to_fair_value`, `morningstar_rating`, `morningstar_rating_updated_time` |
| portfoliostatistics | `marketcapitalvaluelong` |
| purchasedetails | `initialinvestment` |
| trailingperformance | `performanceratingoverall`, `quarterendtrailingreturnytd`, `riskratingoverall`, `trailing_3m_return`, `trailing_ytd_return` |
| price | `eodprice`, `intradayprice`, `intradaypricechange` |

## Constrained field values (for `eq` / `is-in`)

Some fields only accept a fixed set of values. The small, stable ones are listed here in full:

- **`sector`** (equity): `Basic Materials`, `Communication Services`, `Consumer Cyclical`, `Consumer Defensive`, `Energy`, `Financial Services`, `Healthcare`, `Industrials`, `Real Estate`, `Technology`, `Utilities`
- **`region`** (equity/etf): `ae`, `ar`, `at`, `au`, `be`, `br`, `ca`, `ch`, `cl`, `cn`, `co`, `cz`, `de`, `dk`, `ee`, `eg`, `es`, `fi`, `fr`, `gb`, `gr`, `hk`, `hu`, `id`, `ie`, `il`, `in`, `is`, `it`, `jp`, `kr`, `kw`, `lk`, `lt`, `lv`, `mx`, `my`, `nl`, `no`, `nz`, `pe`, `ph`, `pk`, `pl`, `pt`, `qa`, `ro`, `ru`, `sa`, `se`, `sg`, `sr`, `th`, `tr`, `tw`, `us`, `ve`, `vn`, `za`

The rest are large and/or hierarchical (nested per region or per sector), so they aren't reproduced here to avoid this file going stale — look them up live instead:

- **`exchange`** (equity/fund/etf) — ~98 codes, grouped by region (e.g. `us` → `NMS`, `NYQ`, ...)
- **`industry`** (equity) — ~145 values, grouped by sector
- **`peer_group`** (equity) — 103 values
- **`categoryname`**, **`fundfamilyname`**, **`morningstar_*`** (fund/etf)

```python
import yfinance as yf
q = yf.EquityQuery('gt', ['intradaymarketcap', 1])  # any valid query works as a handle
q.valid_values['exchange']    # dict of region -> [exchange codes]
q.valid_values['industry']    # dict of sector -> [industry names]
q.valid_values['peer_group']  # flat list

fq = yf.FundQuery('gt', ['initialinvestment', 1])
etf = yf.ETFQuery('gt', ['initialinvestment', 1])
etf.valid_values['fundfamilyname']
```

## GUI config builder

`yafi/interface.py` is a Tkinter app for building/editing config files without hand-writing JSON:

```bash
python yafi/interface.py
```

Pick a `quote_type`, add conditions (field/operator/value — constrained fields like `exchange` or `sector` get a picker populated from yfinance's own valid-value lists instead of free text), set sort/pagination/output settings, then **Save** to `yafi/configs/<name>.json`. **Load** reads an existing config back into the form — it handles the flat AND/OR-of-conditions shape every config in this repo uses; nested and/or groups aren't supported by the UI and it'll tell you to edit the JSON directly rather than silently mangling it.

**Save & run query_machine.py** (below the preview panel) writes the current form to the filename you entered and immediately runs `query_machine.py` against it in a background subprocess, streaming its console output (page-by-page fetch progress, final result count) into a read-only log box so you don't have to switch to a terminal.

**Launch live dashboard (ticker_time.py, dash)**, next to it, runs `ticker_time.py --engine dash` against the JSON results file named in the **Output** section above (`output.path`, adjusted for `.json`/`.both` — if `output.format` is `csv` it'll tell you to switch to `json`/`both` and run query_machine.py first). Unlike the query_machine button, this starts a server that keeps running — the button watches the subprocess's log for a "ready" line, opens your browser to it as soon as it's up, and turns into a **Stop live dashboard** button while the server is alive. Closing the GUI window terminates it too, so it can't be left running as an orphaned background process.

## Plotting ticker time series

`yafi/ticker_time.py` takes the `symbol` field out of a results JSON (the output of `query_machine.py`) and plots historical price history for those tickers via `yfinance.Ticker(...).history(...)`. It has two engines with genuinely different tradeoffs, not just different looks:

```bash
python yafi/ticker_time.py                                          # uses output/results.json, matplotlib, every symbol found
python yafi/ticker_time.py output/industry_results.json --limit 5   # a different results file, capped to 5 tickers
python yafi/ticker_time.py --symbols NVDA,AMD,INTC --period 1y      # explicit symbols instead of a results file
python yafi/ticker_time.py --engine dash                            # live dashboard at http://127.0.0.1:8050/
python yafi/ticker_time.py --engine dash --value-field Close Volume  # plot both together, color-matched axes
```

**`--engine matplotlib`** (default): eager and static. Fetches every symbol up front (respecting `--request-delay-seconds` between calls) into one overlaid line chart of raw `--value-field` values. Opens a window, or saves a `.png` with `--output`.

**`--engine dash`**: a live local server (`yafi/dashboard.py`), not a static file.

- **Sidebar (left)**: tickers are grouped into collapsible sections of up to 100 (`html.Details`/`Summary`, only the first section open by default), each a plain vertical checkbox list. The sidebar has a fixed width and scrolls independently (`maxHeight: 85vh`) so it doesn't grow the whole page.
- **Charts (right)**: nothing is fetched until you check a box. Checking one fetches that ticker's *entire* OHLCV history in one call (only once — logged server-side, e.g. `fetching NVDA (period=6mo interval=1d)` / `fetched NVDA: 124 rows in 0.42s`) and drops its chart into a 4-column grid, filling left-to-right/top-to-bottom in the order you check things (not each ticker's position in the results file). Unchecking hides a chart without discarding it — re-checking re-shows it instantly and moves it to the end of the current order. The chart/sidebar split uses `minWidth: 0` on the chart side specifically so the grid shrinks to fit next to the sidebar instead of forcing the page wider than the window.
- **Multiple `--value-field`s**: pass more than one (e.g. `--value-field Close Volume`, or check 2+ boxes in the GUI's "plot value_field(s)" row) and every chart gets a checkbox row of its own, letting you plot any combination of them *together* on one chart instead of picking just one. Each field gets its own y-axis rather than being forced onto a shared scale (Close in dollars and Volume in shares would be meaningless squashed onto one axis) — the axis is colored to match its line (`yafi.dashboard.FIELD_COLORS`) so it's clear which axis belongs to which trace even with 3+ overlaid. Since the full history is already cached, checking/unchecking fields re-plots instantly with no refetch.
- **Field table**: if the results JSON had a `fields` list (i.e. it wasn't every raw field Yahoo returns), every field from that ticker's record is shown as a table directly under its chart — the same data that ended up in `results.json`, not just price history. Explicit `--symbols` (bypassing a results file) has no record to show, so those charts just don't get a table.
- Runs with Dash's debug mode on (in-browser callback graph and error overlays) and its own `logging` output on the console, for exactly the kind of "what is this dashboard doing" debugging this was built for; `use_reloader` is off so it stays a single supervisable process. `--port` picks the port (default 8050); `--output` doesn't apply here — there's no file, just a running server you stop with Ctrl-C (or the GUI's Stop button).

The core logic behind the dash engine (`compute_check_order`, `render_charts` in `yafi/dashboard.py`) is deliberately kept as plain functions the Dash callbacks just call, rather than logic buried inside the callback closures — you can import and call them directly (see `yafi/tests/test_dashboard.py`) to inspect/debug behavior without a browser or running server at all.

**Dependencies**: `matplotlib` and `dash` are separate optional extras (`pip install ".[plot]"` / `".[dashboard]"`, both included if you used `requirements.txt`/`scripts/setup.*`) because they're not close in weight — `dash` pulls in Flask, `plotly`, and about 60 other packages transitively. If you only need static charts, you don't need to install `dash` at all.

**No disk cache**: everything the dash engine fetches is cached in memory only, for the lifetime of that server process. Restarting the dashboard re-fetches everything you check again from scratch. That's intentional for now, not an oversight — ask if you want on-disk caching added.

## VS Code

`.vscode/launch.json` includes two debug configurations that use the `.yafi-venv` interpreter: "Run query_machine.py" (default config) and "Run query_machine.py (custom config)" (prompts for a config path).
