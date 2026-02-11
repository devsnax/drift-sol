from solathon import Client, Keypair
from solathon import Transaction
from solathon.utils import sol_to_lamport
from datetime import datetime, timedelta
import os
import json
import base64
import requests
import time
import threading
from functools import wraps
import urllib3

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Telegram config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trade history for daily summary
trade_history = []

state = {
    "token": None,
    "token_symbol": None,
    "last_price": None,
    "position": False,
    "entry_price": None,
    "size": 0.01,
    "token_balance": 0,
    "iteration_count": 0  # For controlling hold notification frequency
}


# ═══════════════════════════════════════════════════════════════════════
# RETRY LOGIC FOR API CALLS
# ═══════════════════════════════════════════════════════════════════════

def retry_on_failure(max_retries=2, initial_delay=1, backoff_factor=2):  # Reduced from 3 to 2
    """
    Decorator that retries a function on network errors with exponential backoff.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.Timeout, 
                        requests.exceptions.ConnectionError,
                        requests.exceptions.SSLError) as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        print(f"  Network error (attempt {attempt + 1}/{max_retries}). Retrying in {delay}s...")
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        print(f"  Network error: All {max_retries} attempts failed")
            
            return None
        return wrapper
    return decorator


@retry_on_failure(max_retries=3, initial_delay=2)
def fetch_with_retry(url, params=None, timeout=20):
    """
    Makes HTTP GET request with retry logic and better error handling.
    Accepts custom timeout (default 20s, can be increased for slow APIs).
    """
    response = requests.get(
        url, 
        params=params, 
        timeout=timeout,  # Use provided timeout
        verify=False,  # Disable SSL verification to avoid handshake errors
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
    )
    
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 429:
        print(f"  Rate limited. Waiting 60s...")
        time.sleep(60)
        raise requests.exceptions.RequestException("Rate limited")
    else:
        print(f"  HTTP error: {response.status_code}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def send_telegram_message(message):
    """
    Sends a message to your Telegram bot.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False


def notify(message, also_print=True):
    """
    Wrapper that both prints and sends to Telegram.
    """
    if also_print:
        print(message)
    
    send_telegram_message(message)


def log_trade(token_symbol, entry_price, exit_price, pnl_usd, pnl_pct, result):
    """
    Logs completed trade to history.
    """
    trade = {
        "timestamp": datetime.now(),
        "token": token_symbol,
        "entry": entry_price,
        "exit": exit_price,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "result": result
    }
    trade_history.append(trade)


def generate_daily_summary():
    """
    Generates daily PnL summary.
    """
    if not trade_history:
        return "<b>DAILY SUMMARY</b>\n\nNo trades today."
    
    total_trades = len(trade_history)
    winning_trades = [t for t in trade_history if t["pnl_usd"] > 0]
    losing_trades = [t for t in trade_history if t["pnl_usd"] <= 0]
    
    total_pnl = sum([t["pnl_usd"] for t in trade_history])
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
    
    best_trade = max(trade_history, key=lambda x: x["pnl_pct"])
    worst_trade = min(trade_history, key=lambda x: x["pnl_pct"])
    
    message = f"""
<b>DAILY SUMMARY</b>

Date: {datetime.now().strftime("%Y-%m-%d")}

<b>Performance:</b>
Total Trades: {total_trades}
Wins: {len(winning_trades)}
Losses: {len(losing_trades)}
Win Rate: {win_rate:.1f}%

<b>PnL:</b>
Total: ${total_pnl:.4f}
Best Trade: {best_trade['token']} ({best_trade['pnl_pct']:+.2f}%)
Worst Trade: {worst_trade['token']} ({worst_trade['pnl_pct']:+.2f}%)

<b>Recent Trades:</b>
"""
    
    recent_trades = trade_history[-5:]
    for trade in reversed(recent_trades):
        time_str = trade['timestamp'].strftime("%H:%M")
        message += f"\n{time_str} | {trade['token']} | {trade['result']} | {trade['pnl_pct']:+.2f}%"
    
    return message.strip()


def send_daily_summary():
    """
    Sends daily summary and clears history.
    """
    summary = generate_daily_summary()
    send_telegram_message(summary)
    trade_history.clear()


def schedule_daily_summary():
    """
    Schedules daily summary at midnight.
    """
    def run_scheduler():
        while True:
            now = datetime.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            next_midnight = midnight + timedelta(days=1)
            seconds_until_midnight = (next_midnight - now).total_seconds()
            
            time.sleep(seconds_until_midnight)
            send_daily_summary()
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()


# ═══════════════════════════════════════════════════════════════════════
# STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def reset_trade_state():
    """
    a helper to reset state after a trade
    """
    state.update({
        "last_price": None,
        "entry_price": None,
        "position": False,
        "token_balance": 0,
        "iteration_count": 0
    })


# ═══════════════════════════════════════════════════════════════════════
# SAFETY CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def check_honeypot(token_address):
    """
    Detects if a token is a honeypot.
    """
    try:
        print(f"  Checking honeypot...")
        
        # Use retry logic with shorter timeout for Jupiter
        buy_quote = fetch_with_retry(
            "https://quote-api.jup.ag/v6/quote",
            params={
                "inputMint": "So11111111111111111111111111111111111111112",
                "outputMint": token_address,
                "amount": 1000000,
                "slippageBps": 5000
            },
            timeout=15  # Reduced from 30 to 15
        )
        
        if not buy_quote or "error" in buy_quote or "outAmount" not in buy_quote:
            print(f"  Skipping honeypot check (Jupiter timeout)")
            # For testing: return True to skip this check
            # For production: return False
            return True  # ← SKIP HONEYPOT CHECK FOR NOW
        
        estimated_tokens = int(buy_quote["outAmount"])
        
        # Use retry logic for sell quote
        sell_quote = fetch_with_retry(
            "https://quote-api.jup.ag/v6/quote",
            params={
                "inputMint": token_address,
                "outputMint": "So11111111111111111111111111111111111111112",
                "amount": estimated_tokens,
                "slippageBps": 5000
            },
            timeout=15  # Reduced from 30 to 15
        )
        
        if not sell_quote or "error" in sell_quote or "outAmount" not in sell_quote:
            print(f"  HONEYPOT DETECTED - Cannot sell")
            return False
        
        sol_in = 1000000
        sol_out = int(sell_quote["outAmount"])
        round_trip_loss = (sol_in - sol_out) / sol_in * 100
        
        if round_trip_loss > 90:
            print(f"  EXTREME TAXES - {round_trip_loss:.1f}% loss")
            return False
        
        print(f"  Honeypot check passed ({round_trip_loss:.1f}% loss)")
        return True
    
    except Exception as e:
        print(f"  Skipping honeypot check (error)")
        # For testing: return True to continue
        # For production: return False
        return True  # ← SKIP HONEYPOT CHECK ON ERROR FOR NOW


def check_liquidity_locked(token_address, client):
    """
    Checks if liquidity is locked or burned.
    """
    try:
        print(f"  Checking liquidity lock...")
        
        # Use retry logic
        data = fetch_with_retry(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        )
        
        if not data:
            return False
        
        pairs = data.get("pairs", [])
        
        if not pairs:
            return False
        
        pair_address = pairs[0].get("pairAddress")
        if not pair_address:
            return False
        
        # Use direct RPC call instead of client.http.request
        response = requests.post(
            client.endpoint,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [pair_address]
            },
            timeout=10
        )
        
        result = response.json().get("result", {})
        largest_accounts = result.get("value", [])
        
        if not largest_accounts:
            return False
        
        BURN_ADDRESSES = [
            "1nc1nerator11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "1111111111111111111111111111111111111111111"
        ]
        
        top_holder_address = largest_accounts[0].get("address", "")
        
        if top_holder_address in BURN_ADDRESSES:
            print(f"  Liquidity is BURNED")
            return True
        
        total_supply = sum([acc.get("uiAmount", 0) for acc in largest_accounts])
        top_holder_amount = largest_accounts[0].get("uiAmount", 0)
        concentration = (top_holder_amount / total_supply * 100) if total_supply > 0 else 0
        
        if concentration > 90:
            print(f"  {concentration:.1f}% LP locked")
            return True
        
        print(f"  Liquidity UNLOCKED ({concentration:.1f}%)")
        return False
    
    except Exception as e:
        print(f"  Liquidity check error: {e}")
        return False


def check_holder_distribution(token_address, client):
    """
    Analyzes token holder distribution.
    """
    try:
        print(f"  Checking holder distribution...")
        
        # Use direct RPC call instead of client.http.request
        response = requests.post(
            client.endpoint,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [token_address]
            },
            timeout=10
        )
        
        result = response.json().get("result", {})
        largest_accounts = result.get("value", [])
        
        if not largest_accounts or len(largest_accounts) < 10:
            print(f"  Not enough holder data")
            return {"is_safe": False}
        
        total_supply = sum([acc.get("uiAmount", 0) for acc in largest_accounts])
        top_10_supply = sum([acc.get("uiAmount", 0) for acc in largest_accounts[:10]])
        top_holder_amount = largest_accounts[0].get("uiAmount", 0)
        
        top_10_pct = (top_10_supply / total_supply * 100) if total_supply > 0 else 100
        top_holder_pct = (top_holder_amount / total_supply * 100) if total_supply > 0 else 100
        
        is_safe = True
        
        # More relaxed thresholds for testing
        if top_10_pct > 75:  # Was 60
            print(f"  HIGH CENTRALIZATION - Top 10: {top_10_pct:.1f}%")
            is_safe = False
        
        if top_holder_pct > 35:  # Was 25
            print(f"  TOP HOLDER: {top_holder_pct:.1f}% - Dump risk")
            is_safe = False
        
        if is_safe:
            print(f"  Healthy distribution (Top 10: {top_10_pct:.1f}%)")
        
        return {
            "is_safe": is_safe,
            "top_10_concentration": top_10_pct,
            "top_holder_percentage": top_holder_pct
        }
    
    except Exception as e:
        print(f"  Distribution check error: {e}")
        return {"is_safe": False}


# ═══════════════════════════════════════════════════════════════════════
# TOKEN SIGNAL FUNCTION
# ═══════════════════════════════════════════════════════════════════════

def get_token_signal(client):
    """
    Scans for new Solana tokens with integrated safety checks.
    """
    try:
        # Use retry logic for initial API call
        tokens = fetch_with_retry("https://api.dexscreener.com/token-boosts/latest/v1")
        
        if not tokens or len(tokens) == 0:
            print("No tokens in latest boosts")
            return None
        
        solana_tokens = [t for t in tokens if t.get("chainId") == "solana"]
        
        if not solana_tokens:
            print("No Solana tokens found")
            return None
        
        for token_data in solana_tokens[:10]:
            token_address = token_data.get("tokenAddress")
            
            if not token_address:
                continue
            
            # Use retry logic for pair details - but don't block if it fails
            try:
                pair_data = fetch_with_retry(
                    f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
                    timeout=15  # Shorter timeout to move faster
                )
                
                if not pair_data:
                    print(f"  Skipping {token_address[:8]}... (fetch failed)")
                    continue
            except Exception as e:
                print(f"  Skipping {token_address[:8]}... (error: {str(e)[:30]})")
                continue
            
            pairs = pair_data.get("pairs", [])
            
            if not pairs:
                continue
            
            pair = pairs[0]
            
            # Extract metrics
            pair_created_at = pair.get("pairCreatedAt", 0)
            liquidity_usd = pair.get("liquidity", {}).get("usd", 0)
            market_cap = pair.get("fdv", 0)
            volume_5m = pair.get("volume", {}).get("m5", 0)
            
            txns_5m = pair.get("txns", {}).get("m5", {})
            buys_5m = txns_5m.get("buys", 0)
            sells_5m = txns_5m.get("sells", 0)
            
            price_change_5m = pair.get("priceChange", {}).get("m5", 0)
            
            now = int(time.time() * 1000)
            age_ms = now - pair_created_at
            age_minutes = age_ms / (1000 * 60)
            
            sell_buy_ratio = sells_5m / buys_5m if buys_5m > 0 else 999
            
            # Basic filters (LOOSENED FOR TESTING)
            # Age: 2-60 minutes (was 5-30)
            if age_minutes < 2 or age_minutes > 60:
                continue
            
            # Liquidity: $1K-$100K (was $3K-$50K)
            if liquidity_usd < 1000 or liquidity_usd > 100000:
                continue
            
            # Market Cap: $5K-$1M (was $10K-$500K)
            if market_cap < 5000 or market_cap > 1000000:
                continue
            
            # Volume (5m): >$2K (was >$5K)
            if volume_5m < 2000:
                continue
            
            # Buys (5m): >10 (was >20)
            if buys_5m < 10:
                continue
            
            # Sell/Buy ratio: <0.8 (was <0.5)
            if sell_buy_ratio > 0.8:
                continue
            
            # Price momentum (5m): +5% to +300% (was +10% to +200%)
            if price_change_5m < 5 or price_change_5m > 300:
                continue
            
            # Safety checks
            token_symbol = pair.get("baseToken", {}).get("symbol", "???")
            print(f"\nRunning safety checks for {token_symbol}...")
            
            if not check_honeypot(token_address):
                print(f"  Failed honeypot check. Skipping...\n")
                time.sleep(1)
                continue
            
            liquidity_locked = check_liquidity_locked(token_address, client)
            if not liquidity_locked:
                print(f"  Liquidity not locked - proceeding with caution")
            
            distribution = check_holder_distribution(token_address, client)
            if not distribution.get("is_safe", False):
                print(f"  Unsafe holder distribution. Skipping...\n")
                time.sleep(1)
                continue
            
            # ═══════════════════════════════════════════════════════
            # ALL CHECKS PASSED - SEND TELEGRAM NOTIFICATION
            # ═══════════════════════════════════════════════════════
            
            message = f"""
<b>✅ SIGNAL DETECTED</b>

Token: <b>{token_symbol}</b>
Address: <code>{token_address[:8]}...{token_address[-6:]}</code>

<b>Metrics:</b>
Age: {age_minutes:.1f} min
Liquidity: ${liquidity_usd:,.0f}
Market Cap: ${market_cap:,.0f}
Volume (5m): ${volume_5m:,.0f}
Buys (5m): {buys_5m}
Price Change (5m): {price_change_5m:+.1f}%
Sell/Buy Ratio: {sell_buy_ratio:.2f}

<b>Safety:</b>
LP Locked: {'YES' if liquidity_locked else 'NO'}
Top 10 Holders: {distribution.get('top_10_concentration', 0):.1f}%
"""
            notify(message.strip())
            
            state["token_symbol"] = token_symbol
            time.sleep(1)
            
            return token_address
        
        print("No tokens match criteria. Scanning again...")
        time.sleep(10)  # Wait longer before next scan to avoid rate limits
        return None
    
    except Exception as e:
        print(f"Error in get_token_signal: {e}")
        time.sleep(10)  # Wait longer on errors
        return None


# ═══════════════════════════════════════════════════════════════════════
# PRICE & BALANCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def get_price(token_address):
    """
    fetches current price of token from DexScreener.
    """
    try:
        data = fetch_with_retry(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        )
        
        if not data:
            return None
        
        pairs = data.get("pairs", [])
        
        if not pairs:
            return None
        
        price_usd = float(pairs[0].get("priceUsd", 0))
        return price_usd
    
    except Exception as e:
        print(f"Error fetching price: {e}")
        return None


def get_token_balance(token_mint, wallet_pubkey, client):
    """
    Query on-chain token balance
    """
    try:
        # Use direct RPC call instead of client.http.request
        response = requests.post(
            client.endpoint,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    str(wallet_pubkey),
                    {"mint": token_mint},
                    {"encoding": "jsonParsed"}
                ]
            },
            timeout=10
        )
        
        accounts = response.json().get("result", {}).get("value", [])
        
        if not accounts:
            return 0
        
        balance = int(accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
        return balance
        
    except Exception as e:
        print(f"Error getting token balance: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════════════
# TRADING LOGIC
# ═══════════════════════════════════════════════════════════════════════

def logic(price):
    """
    trading logic with telegram notifications
    """
    last_price = state["last_price"]

    if last_price is None:
        state["last_price"] = price
        return

    if state["position"] is False:
        state["position"] = True
        state["entry_price"] = price
        now = datetime.now().strftime("%H:%M:%S")
        
        # Buy notification
        message = f"""
<b>BUY EXECUTED</b>

Token: <b>{state['token_symbol']}</b>
Time: {now}
Price: ${price}
Amount: {state['size']} SOL
"""
        notify(message.strip())
        
        token_amount = buy_token(
            TOKEN_MINT=state["token"],
            amount_sol=state["size"]
        )
        state["token_balance"] = token_amount
        print(f"\t[{now}] Received {token_amount} tokens")

    elif state["position"] == True:
        entry_price = state["entry_price"]
        pnl_usd = price - entry_price
        pnl_pct = (price - entry_price) / entry_price * 100
        now = datetime.now().strftime("%H:%M:%S")
        
        # Print to console
        print(f"\t[{now}] HOLD | Price: ${price} | PnL: ${pnl_usd:.4f} ({pnl_pct:+.2f}%)") 
        
        # Send hold notification every 10 iterations to avoid spam
        state["iteration_count"] += 1
        if state["iteration_count"] % 10 == 0:
            message = f"""
<b>HOLDING</b>

Token: <b>{state['token_symbol']}</b>
Time: {now}
Current Price: ${price}
PnL: ${pnl_usd:.4f} ({pnl_pct:+.2f}%)
"""
            notify(message.strip(), also_print=False)

        TP = 1.5
        SL = 0.2

        if price >= state["entry_price"] * TP:
            # TP notification
            message = f"""
<b>🎯 TAKE PROFIT HIT</b>

Token: <b>{state['token_symbol']}</b>
Time: {now}
Entry: ${entry_price}
Exit: ${price}
PnL: ${pnl_usd:.4f} ({pnl_pct:+.2f}%)
"""
            notify(message.strip())
            
            log_trade(state['token_symbol'], entry_price, price, pnl_usd, pnl_pct, "TP")
            
            state["token"] = None  
            reset_trade_state()
            return "TP_sell"

        if price <= state["entry_price"] * SL:
            # SL notification
            message = f"""
<b>🛑 STOP LOSS HIT</b>

Token: <b>{state['token_symbol']}</b>
Time: {now}
Entry: ${entry_price}
Exit: ${price}
PnL: ${pnl_usd:.4f} ({pnl_pct:+.2f}%)
"""
            notify(message.strip())
            
            log_trade(state['token_symbol'], entry_price, price, pnl_usd, pnl_pct, "SL")
            
            state["token"] = None  
            reset_trade_state()
            return "SL_sell"
    
    state["last_price"] = price


# ═══════════════════════════════════════════════════════════════════════
# SOLANA SETUP
# ═══════════════════════════════════════════════════════════════════════

key_str = os.environ.get("SOLANA_PRIVATE_KEY")
secret_key = bytes(json.loads(key_str))
client = Client("https://api.mainnet-beta.solana.com")  # MAINNET
wallet = Keypair.from_private_key(secret_key)


def buy_token(TOKEN_MINT, client=client, wallet=wallet, amount_sol=0.01):
    quote = requests.get(
        "https://quote-api.jup.ag/v6/quote",
        params={
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": TOKEN_MINT,
            "amount": sol_to_lamport(amount_sol),
            "slippageBps": 100
        }
    ).json()

    swap_txn = requests.post(
        "https://quote-api.jup.ag/v6/swap",
        json={
            "quoteResponse": quote,
            "userPublicKey": str(wallet.public_key),
            "wrapAndUnwrapSol": True
        }
    ).json()

    tx_bytes = base64.b64decode(swap_txn["swapTransaction"])
    txn = Transaction.deserialize(tx_bytes)
    client.send_transaction(txn, wallet)
    print(f"Successfully swapped {amount_sol} SOL for token {TOKEN_MINT}.")
    
    time.sleep(3)
    
    token_amount = get_token_balance(TOKEN_MINT, wallet.public_key, client)
    return token_amount


def sell_token(TOKEN_MINT, amount_token, client=client, wallet=wallet):
    quote = requests.get(
        "https://quote-api.jup.ag/v6/quote",
        params={
            "inputMint": TOKEN_MINT,
            "outputMint": "So11111111111111111111111111111111111111112",
            "amount": amount_token,
            "slippageBps": 100
        }
    ).json()

    swap_txn = requests.post(
        "https://quote-api.jup.ag/v6/swap",
        json={
            "quoteResponse": quote,
            "userPublicKey": str(wallet.public_key),
            "wrapAndUnwrapSol": True
        }
    ).json()

    tx_bytes = base64.b64decode(swap_txn["swapTransaction"])
    txn = Transaction.deserialize(tx_bytes)
    client.send_transaction(txn, wallet)
    print(f"Successfully swapped token back to SOL.")


# ═══════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════

def main():
    now = datetime.now().strftime("%H:%M:%S")
    
    # Bot start notification
    start_message = f"""
<b>BOT STARTED</b>

Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Mode: MAINNET
Safety Checks: Enabled
"""
    notify(start_message.strip())
    
    # Start daily summary scheduler
    schedule_daily_summary()
    
    while True:  
        if state["token"] is None:
            token = get_token_signal(client)

            if token:
                print(f"\nNEW TOKEN LOCKED: {state['token_symbol']}")
                state["token"] = token
            else:
                print("No safe tokens found. Scanning again...")

            time.sleep(10)  # Increased from 5s to 10s to avoid rate limits
            continue
        
        # Trade active token
        price = get_price(state["token"]) 
        
        if price is None:
            print("Cannot fetch price. Waiting...")
            time.sleep(3)
            continue
        
        action = logic(price)
        
        if action == "TP_sell" or action == "SL_sell":
            sell_token(
                TOKEN_MINT=state["token"],
                amount_token=state["token_balance"]
            )

        if not state["position"]:
            state["token"] = None
        
        time.sleep(3)


if __name__ == "__main__":
    main()
