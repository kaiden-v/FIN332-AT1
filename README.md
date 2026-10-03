# VWAP Execution Strategies for Rotman Interactive Trader

Python trading algorithms for the Rotman Interactive Trader (RIT) Agency Trading
case. Each strategy buys a large block of shares over a trading session, and its
execution cost is measured against the market VWAP for that session.

## Strategies

| Script | Strategy |
|---|---|
| `VWAPStrategy/vwap.py` | Market orders following a volume-weighted schedule built from historical volume |
| `ImmediateBuy/immediate_buy.py` | The whole order bought with market orders at the start of the session |
| `LimitOrders/limit_orders.py` | The VWAP schedule placed as limit orders at best bid + offset; unfilled shares roll into the next window, with a market-order sweep at the end |
| `TWAPStrategy/twap.py` | Equal-sized market orders at even intervals |

`rit_common.py` holds the shared code (API helpers, market VWAP tracking, CSV
logging and the session loop), so each strategy script only contains its trading
logic. `analyse_results.py` builds the summary tables and plots.

## Setup

1. Install Python 3 and the libraries: `pip install requests pandas matplotlib scipy`
2. Create `local_config.py` in the repo folder containing your RIT API key
   (from the RIT Client's API tab): `RIT_API_KEY = "YOURKEY"`
3. Open the RIT Client and load the case before running a script.

## Running

From the repo folder, for example:

    python VWAPStrategy/vwap.py

Each script waits for the case to become active, trades it, logs the results,
then waits for the next session. Press Ctrl+C to stop. To carry on numbering
from an earlier run, pass `--start-session N`.

Settings are at the top of each script:
- `VWAPStrategy`, `LimitOrders`: `SCHEDULE_NAME` (which schedule in `InputData/` to follow)
- `LimitOrders`: `OFFSET` (dollars added to the best bid) and `FINAL_SWEEP_TICK`
- `TWAPStrategy`: `INTERVAL_TICKS`
- All strategies: `MAX_ORDER_SIZE`

## Output

Each strategy writes CSVs to its own `Results/` folder:
- `*_session_results.csv`: one row per session (final position, execution VWAP,
  market VWAP, implementation shortfall)
- `*_vwap_timeseries.csv`: execution vs market VWAP and implementation shortfall
  at each checkpoint tick

Implementation shortfall = execution VWAP − market VWAP, so a positive value
means paying more than the market. Market VWAP is computed from time-and-sales
data.

## Analysis

    python analyse_results.py

Reads every strategy's results (never modifies them) and writes:
- per strategy, in `<Strategy>/Results/Plots/`: shortfall histogram, shortfall by
  session, execution vs market VWAP, running shortfall over the session, and
  sweep sizes for the limit orders
- summary CSVs in each `Results/` folder
- `Comparison/`: shortfall by strategy (box plot), mean shortfall with 95% CIs,
  cost vs risk, mean running shortfall per strategy, and `strategy_comparison.csv`
  (mean, standard deviation and 95% confidence interval per strategy)

## Purchase schedules

Schedules in `InputData/` list, for each window, the tick range, the shares to buy
and the cumulative target. The 4-tick schedule spreads each 10-minute window of
historical volume evenly across its ticks.
