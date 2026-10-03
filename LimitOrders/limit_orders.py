"""Limit orders: VWAP schedule placed as limit orders at best bid + offset.

Unfilled shares roll into the next window, and whatever is left at the final
sweep tick is bought with market orders.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common

# --- Config ---------------------------------------------------------------------
SCHEDULE_NAME = "4_tick"
MAX_ORDER_SIZE = 10000
OFFSET = 0.02            # added to the best bid: 0.00 is fully passive, larger is more aggressive
FINAL_SWEEP_TICK = 299   # buy any remaining shares with market orders from this tick

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_NAME = f"{SCHEDULE_NAME}_offset_{OFFSET:.2f}"
SCHEDULE_CSV = os.path.join(SCRIPT_DIR, "InputData", f"{SCHEDULE_NAME}_purchase_schedule.csv")
SESSION_RESULTS_CSV = os.path.join(SCRIPT_DIR, "Results", f"{RUN_NAME}_session_results.csv")
VWAP_TIMESERIES_CSV = os.path.join(SCRIPT_DIR, "Results", f"{RUN_NAME}_vwap_timeseries.csv")


# Best bid plus the offset, falling back to the last price if the bid side is empty
def buy_limit_price(api):
    best_bid = common.get_best_bid(api)
    if best_bid is None:
        best_bid = common.get_last_price(api)
    return round(best_bid + OFFSET, 2)


def trade(api, case, run):
    purchases, checkpoints = common.load_purchase_schedule(SCHEDULE_CSV)
    scheduled_total = 0   # shares the schedule says we should hold by now
    open_order_ids = []   # this window's resting limit orders
    sweep_shares = 0
    swept = False

    for tick in run.ticks(case):
        # New window: replace unfilled orders with one order for the full shortfall to schedule
        due = common.pop_due(purchases, tick)
        if due:
            scheduled_total += sum(shares for _, shares in due)
            common.cancel_orders(api, open_order_ids)
            open_order_ids = []

            position = int(common.get_position(api))
            quantity = min(scheduled_total, common.TOTAL_SHARES) - position
            if quantity > 0:
                price = buy_limit_price(api)
                open_order_ids = common.submit_orders(api, quantity, MAX_ORDER_SIZE, price)
                print(f"tick {tick} (scheduled {[t for t, _ in due]}): limit BUY {quantity} @ {price:.2f} "
                      f"(scheduled total {scheduled_total}, held {position})")

        # Final sweep: cancel what is resting and buy the rest at market
        if tick >= FINAL_SWEEP_TICK and not swept:
            common.cancel_orders(api, open_order_ids)
            open_order_ids = []
            sweep_shares = max(common.TOTAL_SHARES - int(common.get_position(api)), 0)
            common.submit_orders(api, sweep_shares, MAX_ORDER_SIZE)
            if sweep_shares:
                print(f"tick {tick}: SWEEP market BUY {sweep_shares}")
            swept = True

        for scheduled_tick, target in common.pop_due(checkpoints, tick):
            run.checkpoint(tick, scheduled_tick, target)

    return {'Offset': OFFSET, 'Sweep Shares': sweep_shares}


if __name__ == "__main__":
    common.run_strategy(trade, f"limit orders at best bid + {OFFSET:.2f}",
                        SESSION_RESULTS_CSV, VWAP_TIMESERIES_CSV)
