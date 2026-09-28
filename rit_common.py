"""
rit_common.py

Shared code for all AT1 strategy variants (VWAP schedule, immediate buy,
limit orders, TWAP, etc). 

"""

import requests
import signal
import csv
import os
import time

# Shared config 
BASE_URL = "http://localhost:9999/v1"
TICKER = "TNX"

try:
    from local_config import RIT_API_KEY
except ImportError:
    raise SystemExit("Create local_config.py next to rit_common.py containing: RIT_API_KEY = 'your key' (from the RIT Client's API tab).")
API_KEY = {'X-API-Key': RIT_API_KEY}

# Stores the shutdown state so all strategy scripts can respond to Ctrl+C.
shutdown = False


# Define custom exception for API-related errors
class ApiException(Exception):
    pass

# Handle system shutdown requests
def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True


# --- RIT API helpers -------------------------------------------------------

# Retrieve the current case status, tick, and trading period
def get_case(session):
    resp = session.get(BASE_URL + "/case")
    if resp.ok:
        return resp.json()
    raise ApiException('Authorisation error, please check API key.')

# Submit a market order for the specified ticker and quantity
def submit_order(session, ticker, quantity, action):
    payload = {
        'ticker': ticker,
        'type': 'MARKET',
        'quantity': quantity,
        'action': action
    }
    resp = session.post(BASE_URL + '/orders', params=payload)
    if resp.ok:
        return resp.json()
    raise ApiException(f'Order submission failed: {resp.json()}')

# Submit a limit order for the specified ticker, quantity, and price
def submit_limit_order(session, ticker, quantity, action, price):
    payload = {
        'ticker': ticker,
        'type': 'LIMIT',
        'quantity': quantity,
        'action': action,
        'price': price
    }
    resp = session.post(BASE_URL + '/orders', params=payload)
    if resp.ok:
        return resp.json()
    raise ApiException(f'Order submission failed: {resp.json()}')

# Retrieve the current position for the specified ticker
def get_position(session, ticker):
    resp = session.get(BASE_URL + '/securities', params={'ticker': ticker})
    if resp.ok:
        securities = resp.json()
        return securities[0]['position']
    raise ApiException('Failed to fetch position, please check API key.')

# Retrieve our average execution price (VWAP) for the current position
def get_own_vwap(session, ticker):
    resp = session.get(BASE_URL + '/securities', params={'ticker': ticker})
    if resp.ok:
        securities = resp.json()
        return securities[0]['vwap']
    raise ApiException('Failed to fetch own vwap, please check API key.')

# Retrieve and update the running market VWAP using new time and sales records
def get_market_vwap(session, ticker, state):
    resp = session.get(BASE_URL + '/securities/tas', params={'ticker': ticker, 'after': state['last_id']})
    if not resp.ok:
        raise ApiException('Failed to fetch time and sales, please check API key.')

    trades = resp.json()
    if trades:
        state['total_value'] += sum(t['price'] * t['quantity'] for t in trades)
        state['total_quantity'] += sum(t['quantity'] for t in trades)
        state['last_id'] = max(t['id'] for t in trades)

    if state['total_quantity'] == 0:
        return 0.0
    return state['total_value'] / state['total_quantity']


# Retrieve the best available bid and ask prices from the order book
def get_best_bid_ask(session, ticker):
    resp = session.get(BASE_URL + '/securities/book', params={'ticker': ticker})
    if resp.ok:
        book = resp.json()
        bids = [o['price'] for o in book.get('bids', [])]
        asks = [o['price'] for o in book.get('asks', [])]
        best_bid = max(bids) if bids else None
        best_ask = min(asks) if asks else None
        return best_bid, best_ask
    raise ApiException('Failed to fetch order book, please check API key.')

# Retrieve the most recent traded price for the specified ticker
def get_last_price(session, ticker):
    resp = session.get(BASE_URL + '/securities', params={'ticker': ticker})
    if resp.ok:
        securities = resp.json()
        return securities[0]['last']
    raise ApiException('Failed to fetch last price, please check API key.')

# Retrieve the current status and fill information for an order
def get_order(session, order_id):
    resp = session.get(BASE_URL + f'/orders/{order_id}')
    if resp.ok:
        return resp.json()
    raise ApiException(f'Failed to fetch order {order_id}.')

# Cancel a single order and return whether the cancellation succeeded
def cancel_order(session, order_id):
    resp = session.delete(BASE_URL + f'/orders/{order_id}')
    return resp.ok

# Cancel all orders specified by their order IDs
def cancel_orders(session, order_ids):
    for order_id in order_ids:
        cancel_order(session, order_id)

# Submit a limit order in chunks up to the specified maximum size
def submit_limit_orders_chunked(session, ticker, quantity, action, price, max_size):
    order_ids = []
    remaining = quantity
    while remaining > 0:
        chunk = min(max_size, remaining)
        order = submit_limit_order(session, ticker, chunk, action, price)
        order_ids.append(order['order_id'])
        remaining -= chunk
    return order_ids


# --- Schedule loading -------------------------------------------------------

# Load the purchase and cumulative holdings schedules from a CSV file
def load_purchase_schedule(csv_path):
    purchase_schedule = {}
    cumulative_holdings_schedule = {}

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tick_start = int(row['Tick Start'])
            tick_end = int(row['Tick End'])
            shares = int(row['Shares to Purchase'])
            cumulative = int(row['Cumulative Shares'])

            purchase_schedule[tick_start] = shares
            cumulative_holdings_schedule[tick_end] = cumulative

    return purchase_schedule, cumulative_holdings_schedule


# --- CSV logging ------------------------------------------------------------

# Log VWAP and slippage at each trading checkpoint
def log_vwap_point(csv_path, session_number, tick, own_vwap, market_vwap):
    is_new = not os.path.exists(csv_path)
    own_vwap_r = round(own_vwap, 2)
    market_vwap_r = round(market_vwap, 2)
    slippage = round(own_vwap_r - market_vwap_r, 2)
    with open(csv_path, 'a', newline='') as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(['Session', 'Tick', 'Own VWAP', 'Market VWAP', 'Slippage'])
        writer.writerow([session_number, tick, own_vwap_r, market_vwap_r, slippage])

# Log final session results, including VWAP, slippage, and any additional results
def log_session_result(csv_path, session_number, final_position, own_vwap, market_vwap, extras=None):
    extras = extras or {}
    is_new = not os.path.exists(csv_path)
    slippage = round(own_vwap - market_vwap, 2)
    with open(csv_path, 'a', newline='') as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(['Session', 'Final Position', 'Own VWAP', 'Market VWAP', 'Slippage'] + list(extras.keys()))
        writer.writerow([session_number, round(final_position, 2), own_vwap, market_vwap, slippage] + list(extras.values()))


# --- Session lifecycle helper ------------------------------------------------

# Wait until the trading session becomes active, checking once per second
def wait_for_active_session(session):
    case = get_case(session)
    while case['status'] != 'ACTIVE' and not shutdown:
        time.sleep(1)
        case = get_case(session)
    return None if shutdown else case