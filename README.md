# FIN332 – AT1 Agency Trading (VWAP Execution Strategies)

Python algorithms for the Rotman Interactive Trader (RIT) "Agency Trading 1"
case: accumulate 100,000 shares of TNX using different execution strategies and
compare each against the market VWAP.

## Strategies

| Folder | Strategy | Discussion question |
|---|---|---|
| `VWAPStrategy/` | Market orders following a historical volume-weighted schedule (4-tick or 8-tick windows) | Q1 |
| `ImmediateBuy/` | Buy all 100,000 shares at the start | Q2 |
| `LimitOrders/` | VWAP schedule using limit orders at best bid + offset; unfilled shares roll into the next window, with a market-order sweep at the end | Q4 |
| `TWAPStrategy/` | Equal-sized orders at even intervals | Q5 |

`rit_common.py` holds the shared code (API helpers, VWAP calculation, CSV logging).

## Setup

1. Install Python 3 and the requests library: `pip install requests`
2. Create `local_config.py` and put your RIT API key in it as RIT_API_KEY = "YOURKEY" (found on the RIT Client's API tab).
3. Open the RIT Client and load the AT1 case before running a script.

## Running

From the repo folder:

    python VWAPStrategy/AT1_VWAP_Market_ALGO.py

Each script waits for the case to become active, trades it, logs the results,
then waits for the next session. Press Ctrl+C to stop.

Settings to change are at the top of each script:
- `VWAPStrategy`: `SCHEDULE_NAME` ("4_tick" or "8_tick")
- `LimitOrders`: `OFFSET` (dollars added to the best bid)
- `TWAPStrategy`: `INTERVAL_TICKS`
- All variants except `VWAPStrategy`: `MAX_ORDER_SIZE`

## Output

Each variant writes CSVs to its own `Results/` folder (create the folder if it
does not exist):
- `*_session_results.csv`: one row per session (final position, own VWAP, market VWAP, slippage)
- `*_vwap_timeseries.csv`: own vs market VWAP and slippage at each checkpoint tick

Slippage = own VWAP − market VWAP. Market VWAP is computed from time-and-sales data.
Session numbers restart at 1 each time a script is launched.

## Notes

- The 4-tick schedule was derived from the 10-minute historical volume data by
  spreading each window's shares evenly across its ticks.
- Case materials are not included in this repo.
