from time import sleep
import sys
import os

# Add the parent directory so rit_common.py can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rit_common as common
import requests
import signal

# --- Strategy-specific config -----------------------------------------------
# Select the purchase schedule interval
SCHEDULE_NAME = "4_tick"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "InputData") + os.sep
RESULTS_PATH = os.path.join(SCRIPT_DIR, "Results") + os.sep
VWAP_Schedule_CSV = INPUT_PATH + f"{SCHEDULE_NAME}_purchase_schedule.csv"
SESSION_RESULTS_CSV = RESULTS_PATH + f"{SCHEDULE_NAME}_session_results.csv"
VWAP_TIMESERIES_CSV = RESULTS_PATH + f"{SCHEDULE_NAME}_vwap_timeseries.csv"


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

            print(f"--- Starting session {session_number} ---")

            # Load the purchase schedule and reset market VWAP state
            purchase_schedule, cumulative_holdings_schedule = common.load_purchase_schedule(VWAP_Schedule_CSV)
            market_vwap_state = {'total_value': 0.0, 'total_quantity': 0.0, 'last_id': 0}
            tick = case['tick']

            # Execute the scheduled purchases while the session is active
            while case['status'] == 'ACTIVE' and not common.shutdown:

                # Submit the scheduled purchase for the current tick
                if tick in purchase_schedule:
                    shares = purchase_schedule.pop(tick)
                    order = common.submit_order(s, common.TICKER, shares, 'BUY')
                    print(f"tick {tick}: bought {shares} shares -> order id {order.get('order_id')}")

                # Check actual holdings against the cumulative target schedule
                if tick in cumulative_holdings_schedule:
                    target = cumulative_holdings_schedule.pop(tick)
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
                    common.log_vwap_point(VWAP_TIMESERIES_CSV, session_number, tick, running_own_vwap, running_market_vwap)

                # Update the session status and current tick before the next iteration
                sleep(0.2)
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
            print(f"Final position: {final_position:.2f} (target: 100000)")
            print(f"Your VWAP:   {own_vwap_r:.2f}")
            print(f"Market VWAP: {market_vwap_r:.2f}")
            print(f"Slippage:    {slippage:+.2f}")

            # Save final VWAP and session results to the output files
            common.log_vwap_point(VWAP_TIMESERIES_CSV, session_number, 300, own_vwap_r, market_vwap_r)
            common.log_session_result(SESSION_RESULTS_CSV, session_number, final_position, own_vwap_r, market_vwap_r)

            # Increment the session counter and wait for the next session
            print("Waiting for next session...")
            session_number += 1


# Start the strategy and enable graceful shutdown on interrupt
if __name__ == "__main__":
    signal.signal(signal.SIGINT, common.signal_handler)
    main()