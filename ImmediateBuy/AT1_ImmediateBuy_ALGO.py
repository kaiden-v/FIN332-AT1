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
MAX_ORDER_SIZE = 100000 

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(SCRIPT_DIR, "Results") + os.sep
SESSION_RESULTS_CSV = RESULTS_PATH + "immediate_buy_session_results.csv"


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

            # Reset the running market VWAP state for the new session
            market_vwap_state = {'total_value': 0.0, 'total_quantity': 0.0, 'last_id': 0}

            # Submit the full purchase as a series of maximum-size market orders
            remaining = TOTAL_SHARES
            while remaining > 0:
                chunk = min(MAX_ORDER_SIZE, remaining)
                order = common.submit_order(s, common.TICKER, chunk, 'BUY')
                print(f"submitted BUY {chunk} shares -> order id {order.get('order_id')}")
                remaining -= chunk

            print("All orders submitted, waiting for session to end...")

            # Track market VWAP while waiting for the session to end
            while case['status'] == 'ACTIVE' and not common.shutdown:
                common.get_market_vwap(s, common.TICKER, market_vwap_state)
                sleep(0.2)
                case = common.get_case(s)

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

            # Save the final session results to the output file
            common.log_session_result(SESSION_RESULTS_CSV, session_number, final_position, own_vwap_r, market_vwap_r)

            # Increment the session counter and wait for the next session
            print("Waiting for next session...")
            session_number += 1


# Start the strategy and enable graceful shutdown on interrupt
if __name__ == "__main__":
    signal.signal(signal.SIGINT, common.signal_handler)
    main()