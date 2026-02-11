import requests
import time
from datetime import datetime

print("="*70)
print("DEXSCREENER DIAGNOSTIC - Checking what tokens are available")
print("="*70)

def fetch_tokens():
    try:
        url = "https://api.dexscreener.com/token-boosts/latest/v1"
        response = requests.get(url, timeout=20, verify=False)
        
        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code}")
            return
        
        tokens = response.json()
        
        if not tokens:
            print("\n❌ No tokens returned from API")
            return
        
        print(f"\n✅ Total tokens returned: {len(tokens)}")
        
        # Filter Solana tokens
        solana_tokens = [t for t in tokens if t.get("chainId") == "solana"]
        print(f"✅ Solana tokens: {len(solana_tokens)}")
        
        if not solana_tokens:
            print("\n❌ No Solana tokens found!")
            print("\nShowing first 5 tokens (any chain):")
            for i, token in enumerate(tokens[:5]):
                print(f"\n  Token {i+1}:")
                print(f"    Chain: {token.get('chainId')}")
                print(f"    Address: {token.get('tokenAddress')}")
            return
        
        print(f"\n{'='*70}")
        print("CHECKING FIRST 10 SOLANA TOKENS AGAINST YOUR FILTERS")
        print(f"{'='*70}")
        
        for idx, token_data in enumerate(solana_tokens[:10]):
            token_address = token_data.get("tokenAddress")
            
            print(f"\n--- Token {idx + 1}: {token_address} ---")
            
            # Get pair details
            pair_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            pair_response = requests.get(pair_url, timeout=20, verify=False)
            
            if pair_response.status_code != 200:
                print(f"  ❌ Failed to fetch pair data")
                continue
            
            pair_data = pair_response.json()
            pairs = pair_data.get("pairs", [])
            
            if not pairs:
                print(f"  ❌ No pairs found")
                continue
            
            pair = pairs[0]
            
            # Extract metrics
            token_symbol = pair.get("baseToken", {}).get("symbol", "???")
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
            
            print(f"  Symbol: {token_symbol}")
            print(f"  Age: {age_minutes:.1f} min {'✅' if 2 <= age_minutes <= 60 else '❌ FAIL'} (need: 2-60)")
            print(f"  Liquidity: ${liquidity_usd:,.0f} {'✅' if 1000 <= liquidity_usd <= 100000 else '❌ FAIL'} (need: $1K-$100K)")
            print(f"  Market Cap: ${market_cap:,.0f} {'✅' if 5000 <= market_cap <= 1000000 else '❌ FAIL'} (need: $5K-$1M)")
            print(f"  Volume (5m): ${volume_5m:,.0f} {'✅' if volume_5m >= 2000 else '❌ FAIL'} (need: >$2K)")
            print(f"  Buys (5m): {buys_5m} {'✅' if buys_5m >= 10 else '❌ FAIL'} (need: >10)")
            print(f"  Sell/Buy: {sell_buy_ratio:.2f} {'✅' if sell_buy_ratio <= 0.8 else '❌ FAIL'} (need: <0.8)")
            print(f"  Price Δ (5m): {price_change_5m:+.1f}% {'✅' if 5 <= price_change_5m <= 300 else '❌ FAIL'} (need: +5% to +300%)")
            
            # Check if passes all filters
            passes = all([
                2 <= age_minutes <= 60,
                1000 <= liquidity_usd <= 100000,
                5000 <= market_cap <= 1000000,
                volume_5m >= 2000,
                buys_5m >= 10,
                sell_buy_ratio <= 0.8,
                5 <= price_change_5m <= 300
            ])
            
            if passes:
                print(f"\n  🎯 THIS TOKEN PASSES ALL FILTERS!")
            else:
                print(f"\n  ❌ Failed filters")
            
            time.sleep(0.5)  # Small delay between requests
    
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    fetch_tokens()
    print(f"\n{'='*70}")
    print("Diagnostic complete")
    print(f"{'='*70}\n")