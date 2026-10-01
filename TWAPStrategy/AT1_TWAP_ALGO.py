from time import sleep
import sys
import os

# Add the parent directory so rit_common.py can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common
import requests
import signal

# --- Strategy-specific config -----------------------------------------------
TOTAL_SHARES = 100000
CASE_LENGTH_TICKS = 300
INTERVAL_TICKS = 4      
MAX_ORDER_SIZE = 10000     

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(SCRIPT_DIR, "Results") + os.sep
RUN_NAME = f"twap_{INTERVAL_TICKS}_tick"
SESSION_RESULTS_CSV = RESULTS_PATH + f"{RUN_NAME}_session_results.csv"
VWAP_TIMESERIES_CSV = RESULTS_PATH + f"{RUN_NAME}_vwap_timeseries.csv"


# Build the TWAP purchase schedule and cumulative holdings checkpoints
def build_twap_schedule():
    order_ticks = list(range(1, CASE_LENGTH_TICKS + 1, INTERVAL_TICKS))
    base = TOTAL_SHARES // len(order_ticks)
    remainder = TOTAL_SHARES - base * len(order_ticks)

    purchase_schedule = {}
    cumulative_holdings_schedule = {}
    cumulative = 0
    for i, tick_start in enumerate(order_ticks):
        shares = base + (remainder if i == len(order_ticks) - 1 else 0)
        cumulative += shares
        tick_end = min(tick_start + INTERVAL_TICKS - 1, CASE_LENGTH_TICKS)
        purchase_schedule[tick_start] = shares
        cumulative_holdings_schedule[tick_end] = cumulative
    return purchase_schedule, cumulative_holdings_schedule


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

            print(f"--- Starting session {session_number} (TWAP every {INTERVAL_TICKS} ticks) ---")

            # Build a fresh purchase schedule and reset market VWAP state
            purchase_schedule, cumulative_holdings_schedule = build_twap_schedule()
            market_vwap_state = {'total_value': 0.0, 'total_quantity': 0.0, 'last_id': 0}
            tick = case['tick']

            # Execute the TWAP strategy while the session is active
            while case['status'] == 'ACTIVE' and not common.shutdown:

                # Submit the scheduled purchase for the current tick
                for scheduled_tick in sorted(t for t in purchase_schedule if t <= tick):
                    shares = purchase_schedule.pop(scheduled_tick)
                    remaining = shares
                    while remaining > 0:
                        chunk = min(MAX_ORDER_SIZE, remaining)
                        order = common.submit_order(s, common.TICKER, chunk, 'BUY')
                        remaining -= chunk
                    print(f"tick {tick} (scheduled {scheduled_tick}): bought {shares} shares")

                # Check actual holdings against the cumulative target schedule
                for scheduled_tick in sorted(t for t in cumulative_holdings_schedule if t <= tick):
                    target = cumulative_holdings_schedule.pop(scheduled_tick)
                    actual = common.get_position(s, common.TICKER)
                    diff = target - actual

                    # Report whether the strategy is ahead of, behind, or on schedule
                    if diff > 0:
                        print(f"tick {tick}: BEHIND schedule — target {target:.2f}, actual {actual:.2f} (short {diff:.2f})")
                    elif diff < 0:
                        print(f"tick {tick}: AHEAD of schedule — target {target:.2f}, actual {actual:.2f} (over {-diff:.2f})")
                    else:
                        print(f"tick {tick}: on schedule — {actual:.2f} shares")

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
            print(f"Your VWAP:   {own_vwap_r:.2f}")
            print(f"Market VWAP: {market_vwap_r:.2f}")
            print(f"Slippage:    {slippage:+.2f}")

            # Save final VWAP and session results to the output files
            common.log_vwap_point(VWAP_TIMESERIES_CSV, session_number, CASE_LENGTH_TICKS, own_vwap_r, market_vwap_r)
            common.log_session_result(
                SESSION_RESULTS_CSV,
                session_number,
                final_position,
                own_vwap_r,
                market_vwap_r,
                extras={'Interval Ticks': INTERVAL_TICKS}
            )

            # Increment the session counter and wait for the next session
            print("Waiting for next session...")
            session_number += 1


# Start the strategy and enable graceful shutdown on interrupt
if __name__ == "__main__":
    signal.signal(signal.SIGINT, common.signal_handler)
    main()