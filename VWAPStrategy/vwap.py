"""VWAP strategy: market orders following the historical volume schedule."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common

# --- Config ---------------------------------------------------------------------
SCHEDULE_NAME = "4_tick"    # "4_tick" or "8_tick"
MAX_ORDER_SIZE = 10000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_CSV = os.path.join(SCRIPT_DIR, "InputData", f"{SCHEDULE_NAME}_purchase_schedule.csv")
SESSION_RESULTS_CSV = os.path.join(SCRIPT_DIR, "Results", f"{SCHEDULE_NAME}_session_results.csv")
VWAP_TIMESERIES_CSV = os.path.join(SCRIPT_DIR, "Results", f"{SCHEDULE_NAME}_vwap_timeseries.csv")


def trade(api, case, run):
    purchases, checkpoints = common.load_purchase_schedule(SCHEDULE_CSV)

    for tick in run.ticks(case):
        # Buy each window's scheduled shares as soon as the window starts
        for scheduled_tick, shares in common.pop_due(purchases, tick):
            common.submit_orders(api, shares, MAX_ORDER_SIZE)
            print(f"tick {tick} (scheduled {scheduled_tick}): bought {shares} shares")

        for scheduled_tick, target in common.pop_due(checkpoints, tick):
            run.checkpoint(tick, scheduled_tick, target)

    return {}


if __name__ == "__main__":
    common.run_strategy(trade, f"VWAP market orders ({SCHEDULE_NAME} schedule)",
                        SESSION_RESULTS_CSV, VWAP_TIMESERIES_CSV)
