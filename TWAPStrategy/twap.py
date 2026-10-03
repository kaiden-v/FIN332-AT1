"""TWAP strategy: equal-sized market orders at even intervals."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common

# --- Config ---------------------------------------------------------------------
INTERVAL_TICKS = 4
MAX_ORDER_SIZE = 10000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_NAME = f"twap_{INTERVAL_TICKS}_tick"
SESSION_RESULTS_CSV = os.path.join(SCRIPT_DIR, "Results", f"{RUN_NAME}_session_results.csv")
VWAP_TIMESERIES_CSV = os.path.join(SCRIPT_DIR, "Results", f"{RUN_NAME}_vwap_timeseries.csv")


# Same shares every interval; any remainder goes in the last order
def build_twap_schedule():
    order_ticks = range(1, common.CASE_LENGTH_TICKS + 1, INTERVAL_TICKS)
    base, remainder = divmod(common.TOTAL_SHARES, len(order_ticks))

    purchases, checkpoints = {}, {}
    cumulative = 0
    for i, tick_start in enumerate(order_ticks):
        shares = base + (remainder if i == len(order_ticks) - 1 else 0)
        cumulative += shares
        purchases[tick_start] = shares
        checkpoints[min(tick_start + INTERVAL_TICKS - 1, common.CASE_LENGTH_TICKS)] = cumulative
    return purchases, checkpoints


def trade(api, case, run):
    purchases, checkpoints = build_twap_schedule()

    for tick in run.ticks(case):
        for scheduled_tick, shares in common.pop_due(purchases, tick):
            common.submit_orders(api, shares, MAX_ORDER_SIZE)
            print(f"tick {tick} (scheduled {scheduled_tick}): bought {shares} shares")

        for scheduled_tick, target in common.pop_due(checkpoints, tick):
            run.checkpoint(tick, scheduled_tick, target)

    return {'Interval Ticks': INTERVAL_TICKS}


if __name__ == "__main__":
    common.run_strategy(trade, f"TWAP every {INTERVAL_TICKS} ticks",
                        SESSION_RESULTS_CSV, VWAP_TIMESERIES_CSV)
