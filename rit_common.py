"""
rit_common.py

Shared code for the AT1 strategy scripts: RIT API helpers, schedule handling,
CSV logging and the session loop that every strategy runs inside.
"""

import argparse
import csv
import os
import signal
import time

import requests

# --- Case config --------------------------------------------------------------
BASE_URL = "http://localhost:9999/v1"
TICKER = "TNX"
TOTAL_SHARES = 100000
CASE_LENGTH_TICKS = 300
POLL_SECONDS = 0.1

try:
    from local_config import RIT_API_KEY
except ImportError:
    raise SystemExit("Create local_config.py next to rit_common.py containing: RIT_API_KEY = 'your key' (from the RIT Client's API tab).")

# Set by Ctrl+C so every loop can stop cleanly
shutdown = False


class ApiException(Exception):
    pass


def _signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # a second Ctrl+C kills immediately
    shutdown = True


# --- RIT API helpers -----------------------------------------------------------

def _request(api, method, path, what, **params):
    resp = api.request(method, BASE_URL + path, params=params or None)
    if resp.ok:
        return resp.json()
    raise ApiException(f"{what} failed ({resp.status_code}): {resp.text}")

def get_case(api):
    return _request(api, "GET", "/case", "Fetching case (check API key)")

def _get_security(api):
    return _request(api, "GET", "/securities", "Fetching security", ticker=TICKER)[0]

def get_position(api):
    return _get_security(api)['position']

# Our own average execution price
def get_own_vwap(api):
    return _get_security(api)['vwap']

def get_last_price(api):
    return _get_security(api)['last']

def get_best_bid(api):
    book = _request(api, "GET", "/securities/book", "Fetching order book", ticker=TICKER)
    bids = [o['price'] for o in book.get('bids', [])]
    return max(bids) if bids else None

# Market order if no price is given, otherwise a limit order
def submit_order(api, quantity, price=None, action='BUY'):
    params = {'ticker': TICKER, 'quantity': quantity, 'action': action,
              'type': 'MARKET' if price is None else 'LIMIT'}
    if price is not None:
        params['price'] = price
    return _request(api, "POST", "/orders", "Order submission", **params)

# Split a quantity into orders no larger than max_size; returns the order ids
def submit_orders(api, quantity, max_size, price=None):
    order_ids = []
    while quantity > 0:
        chunk = min(max_size, quantity)
        order_ids.append(submit_order(api, chunk, price)['order_id'])
        quantity -= chunk
    return order_ids

def cancel_orders(api, order_ids):
    for order_id in order_ids:
        api.delete(BASE_URL + f"/orders/{order_id}")


# Running market VWAP built from time-and-sales, fetching only new trades each call
class MarketVWAP:
    def __init__(self):
        self.value = 0.0
        self.quantity = 0.0
        self.last_id = 0

    def update(self, api):
        trades = _request(api, "GET", "/securities/tas", "Fetching time and sales",
                          ticker=TICKER, after=self.last_id)
        if trades:
            self.value += sum(t['price'] * t['quantity'] for t in trades)
            self.quantity += sum(t['quantity'] for t in trades)
            self.last_id = max(t['id'] for t in trades)
        return self.value / self.quantity if self.quantity else 0.0


# --- Schedules -----------------------------------------------------------------

# Returns {tick start: shares to buy} and {tick end: cumulative shares target}
def load_purchase_schedule(csv_path):
    purchases, checkpoints = {}, {}
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            purchases[int(row['Tick Start'])] = int(row['Shares to Purchase'])
            checkpoints[int(row['Tick End'])] = int(row['Cumulative Shares'])
    return purchases, checkpoints

# Remove and return every (tick, value) entry that is due, so a skipped tick is never missed
def pop_due(schedule, tick):
    return [(t, schedule.pop(t)) for t in sorted(t for t in schedule if t <= tick)]


# --- CSV logging ---------------------------------------------------------------

def _append_row(csv_path, header, row):
    is_new = not os.path.exists(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'a', newline='') as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(header)
        writer.writerow(row)

def log_vwap_point(csv_path, session_number, tick, own_vwap, market_vwap):
    own, market = round(own_vwap, 2), round(market_vwap, 2)
    _append_row(csv_path,
                ['Session', 'Tick', 'Own VWAP', 'Market VWAP', 'Implementation Shortfall'],
                [session_number, tick, own, market, round(own - market, 2)])

def log_session_result(csv_path, session_number, final_position, own_vwap, market_vwap, extras):
    _append_row(csv_path,
                ['Session', 'Final Position', 'Own VWAP', 'Market VWAP', 'Implementation Shortfall'] + list(extras),
                [session_number, round(final_position, 2), own_vwap, market_vwap,
                 round(own_vwap - market_vwap, 2)] + list(extras.values()))


# --- Session loop --------------------------------------------------------------

# Everything a strategy needs during one session: its number, the market VWAP and the checkpoint log
class SessionRun:
    def __init__(self, api, number, timeseries_csv):
        self.api = api
        self.number = number
        self.timeseries_csv = timeseries_csv
        self.market_vwap = MarketVWAP()

    # Yield the current tick on every poll until the session ends
    def ticks(self, case):
        while case['status'] == 'ACTIVE' and not shutdown:
            self.market_vwap.update(self.api)
            yield case['tick']
            time.sleep(POLL_SECONDS)
            case = get_case(self.api)

    # Compare holdings with the cumulative target and log the running VWAPs
    def checkpoint(self, tick, scheduled_tick, target):
        actual = get_position(self.api)
        diff = target - actual
        if diff > 0:
            status = f"BEHIND schedule - target {target:.0f}, actual {actual:.0f} (short {diff:.0f})"
        elif diff < 0:
            status = f"AHEAD of schedule - target {target:.0f}, actual {actual:.0f} (over {-diff:.0f})"
        else:
            status = f"on schedule - {actual:.0f} shares"
        print(f"tick {tick} (scheduled {scheduled_tick}): {status}")
        log_vwap_point(self.timeseries_csv, self.number, scheduled_tick,
                       get_own_vwap(self.api), self.market_vwap.update(self.api))

    # Print and log the final position, VWAPs and implementation shortfall
    def finish(self, session_csv, extras):
        final_position = get_position(self.api)
        own_vwap = round(get_own_vwap(self.api), 2)
        market_vwap = round(self.market_vwap.update(self.api), 2)

        print("--- FINAL RESULTS ---")
        print(f"Final position:  {final_position:.0f} (target {TOTAL_SHARES})")
        for name, value in extras.items():
            print(f"{name + ':':<16} {value}")
        print(f"Own VWAP:        {own_vwap:.2f}")
        print(f"Market VWAP:     {market_vwap:.2f}")
        print(f"Impl. shortfall: {own_vwap - market_vwap:+.2f}")

        if self.timeseries_csv:
            log_vwap_point(self.timeseries_csv, self.number, CASE_LENGTH_TICKS, own_vwap, market_vwap)
        log_session_result(session_csv, self.number, final_position, own_vwap, market_vwap, extras)


# Run trade(api, case, run) for every session until Ctrl+C. trade returns the extra
# columns for the session results CSV (an empty dict if there are none).
def run_strategy(trade, description, session_csv, timeseries_csv=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--start-session", type=int, default=1,
                        help="session number to start counting from (to continue an earlier run)")
    session_number = parser.parse_args().start_session

    signal.signal(signal.SIGINT, _signal_handler)
    with requests.Session() as api:
        api.headers.update({'X-API-Key': RIT_API_KEY})
        while not shutdown:
            # Wait for the case to start
            case = get_case(api)
            while case['status'] != 'ACTIVE' and not shutdown:
                time.sleep(1)
                case = get_case(api)
            if shutdown:
                break

            print(f"--- Starting session {session_number}: {description} ---")
            run = SessionRun(api, session_number, timeseries_csv)
            extras = trade(api, case, run)
            if shutdown:
                break

            run.finish(session_csv, extras)
            print("Waiting for next session...")
            session_number += 1
