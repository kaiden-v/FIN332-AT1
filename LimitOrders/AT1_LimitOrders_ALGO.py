from time import sleep
import sys
import os

# Add the parent directory so rit_common.py can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common
import requests
import signal

# --- Strategy-specific config -----------------------------------------------
SCHEDULE_NAME = "4_tick"
TOTAL_SHARES = 100000
MAX_ORDER_SIZE = 10000

# Limit price offset from the current best bid
# 0.00 is fully passive, while larger values are more aggressive
OFFSET = 0.02

# Tick at which remaining shares are purchased using market orders
FINAL_SWEEP_TICK = 299

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "InputData") + os.sep
RESULTS_PATH = os.path.join(SCRIPT_DIR, "Results") + os.sep
RUN_NAME = f"{SCHEDULE_NAME}_offset_{OFFSET:.2f}"
VWAP_Schedule_CSV = INPUT_PATH + f"{SCHEDULE_NAME}_purchase_schedule.csv"
SESSION_RESULTS_CSV = RESULTS_PATH + f"{RUN_NAME}_session_results.csv"
VWAP_TIMESERIES_CSV = RESULTS_PATH + f"{RUN_NAME}_vwap_timeseries.csv"


# Calculate the limit price using the best bid and configured offset
def get_buy_limit_price(session):
    best_bid, _ = common.get_best_bid_ask(session, common.TICKER)
    if best_bid is None:
        best_bid = common.get_last_price(session, common.TICKER)
    return round(best_bid + OFFSET, 2)

# Main system function
def main():
    with requests.Session() as s:
        s.headers.update(common.API_KEY)
        session_number = 1

        while not common.shutdown:
            # Wait until the trading session becomes active
            case = common.wait_for_active_session(s)
            if case is None:
                break

            print(f"--- Starting session {session_number} (offset {OFFSET:.2f}) ---")

            # Load a fresh purchase schedule and reset market VWAP state
            purchase_schedule, cumulative_holdings_schedule = common.load_purchase_schedule(VWAP_Schedule_CSV)
            market_vwap_state = {'total_value': 0.0, 'total_quantity': 0.0, 'last_id': 0}
            tick = case['tick']

            scheduled_total = 0     # cumulative shares the schedule says we should have by now
            open_order_ids = []     # limit orders from the current window still resting
            sweep_shares = 0        # shares bought by the final sweep
            sweep_done = False

            # Execute the limit-order strategy while the session is active
            while case['status'] == 'ACTIVE' and not common.shutdown:

                # Start a new purchase window for every scheduled tick that has been
                # reached, in case a poll ever jumps past one and would otherwise
                # silently miss it (replace any unfilled orders once, after folding
                # in all due windows, rather than cancelling/resubmitting per window)
                due_ticks = sorted(t for t in purchase_schedule if t <= tick)
                if due_ticks:
                    for scheduled_tick in due_ticks:
                        scheduled_total += purchase_schedule.pop(scheduled_tick)

                    common.cancel_orders(s, open_order_ids)
                    open_order_ids = []

                    position = int(common.get_position(s, common.TICKER))
                    quantity = min(scheduled_total, TOTAL_SHARES) - position
                    if quantity > 0:
                        price = get_buy_limit_price(s)
                        open_order_ids = common.submit_limit_orders_chunked(
                            s, common.TICKER, quantity, 'BUY', price, MAX_ORDER_SIZE
                        )
                        print(f"tick {tick} (scheduled {due_ticks}): limit BUY {quantity} @ {price:.2f} "
                              f"(scheduled total {scheduled_total}, held {position})")

                # Complete any remaining purchase using market orders at the final sweep tick
                if tick >= FINAL_SWEEP_TICK and not sweep_done:
                    common.cancel_orders(s, open_order_ids)
                    open_order_ids = []

                    position = int(common.get_position(s, common.TICKER))
                    remaining = TOTAL_SHARES - position
                    if remaining > 0:
                        to_send = remaining
                        while to_send > 0:
                            chunk = min(MAX_ORDER_SIZE, to_send)
                            common.submit_order(s, common.TICKER, chunk, 'BUY')
                            to_send -= chunk
                        sweep_shares = remaining
                        print(f"tick {tick}: SWEEP market BUY {remaining}")
                    sweep_done = True

                # Check actual holdings against every cumulative checkpoint that has
                # been reached, so one is never silently skipped by a tick jump
                for scheduled_tick in sorted(t for t in cumulative_holdings_schedule if t <= tick):
                    target = cumulative_holdings_schedule.pop(scheduled_tick)
                    actual = common.get_position(s, common.TICKER)
                    diff = target - actual

                    # Report whether the strategy is ahead of, behind, or on schedule
                    if diff > 0:
                        print(f"tick {tick} (scheduled {scheduled_tick}): BEHIND schedule — target {target:.2f}, actual {actual:.2f} (short {diff:.2f})")
                    elif diff < 0:
                        print(f"tick {tick} (scheduled {scheduled_tick}): AHEAD of schedule — target {target:.2f}, actual {actual:.2f} (over {-diff:.2f})")
                    else:
                        print(f"tick {tick} (scheduled {scheduled_tick}): on schedule — {actual:.2f} shares")

                    # Record VWAP and slippage at each checkpoint
                    running_own_vwap = common.get_own_vwap(s, common.TICKER)
                    running_market_vwap = common.get_market_vwap(s, common.TICKER, market_vwap_state)
                    common.log_vwap_point(VWAP_TIMESERIES_CSV, session_number, scheduled_tick, running_own_vwap, running_market_vwap)

                # Update the session status and current tick before the next iteration
                sleep(0.1)
                case = common.get_case(s)
                tick = case['tick']

            if common.shutdown:
                break

            # Retrieve final position and VWAP results after the session ends
            final_position = common.get_position(s, common.TICKER)
            own_vwap = common.get_own_vwap(s, common.TICKER)
            market_vwap = common.get_market_vwap(s, common.TICKER, market_vwap_state)

            # Calculate final VWAPs and execution slippage
            own_vwap_r = round(own_vwap, 2)
            market_vwap_r = round(market_vwap, 2)
            slippage = round(own_vwap_r - market_vwap_r, 2)

            # Display the final session results
            print("--- FINAL RESULTS ---")
            print(f"Final position: {final_position:.2f} (target: {TOTAL_SHARES})")
            print(f"Sweep shares:   {sweep_shares}")
            print(f"Your VWAP:   {own_vwap_r:.2f}")
            print(f"Market VWAP: {market_vwap_r:.2f}")
            print(f"Slippage:    {slippage:+.2f}")

            # Save final VWAP and session results to the output files
            common.log_vwap_point(VWAP_TIMESERIES_CSV, session_number, 300, own_vwap_r, market_vwap_r)
            common.log_session_result(
                SESSION_RESULTS_CSV,
                session_number,
                final_position,
                own_vwap_r,
                market_vwap_r,
                extras={'Offset': OFFSET, 'Sweep Shares': sweep_shares}
            )

            # Increment the session counter and wait for the next session
            print("Waiting for next session...")
            session_number += 1


# Start the strategy and enable graceful shutdown on interrupt
if __name__ == "__main__":
    signal.signal(signal.SIGINT, common.signal_handler)
    main()  