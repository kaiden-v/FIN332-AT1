"""Immediate buy (Q2): buy all shares with market orders at the start of the session."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common

# --- Config ---------------------------------------------------------------------
MAX_ORDER_SIZE = 100000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_RESULTS_CSV = os.path.join(SCRIPT_DIR, "Results", "immediate_buy_session_results.csv")


def trade(api, case, run):
    order_ids = common.submit_orders(api, common.TOTAL_SHARES, MAX_ORDER_SIZE)
    print(f"Submitted {len(order_ids)} market order(s) for {common.TOTAL_SHARES} shares, waiting for session to end...")

    # Keep tracking the market VWAP until the session ends
    for _ in run.ticks(case):
        pass

    return {}


if __name__ == "__main__":
    common.run_strategy(trade, "immediate buy", SESSION_RESULTS_CSV)
