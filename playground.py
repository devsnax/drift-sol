from solathon import Client, PublicKey, Keypair

# connecting to the devnet
client = Client("https://api.devnet.solana.com")

### creating a new wallet
# new_wallet = Keypair()
# print(f"Public key: {new_wallet.public_key}")

## requesting test SOL (1) for the devnet
public_key = "ALiSvsgjL6FUmCHPWFuQAH18veEr4hETXEUCLrefKiZr"
# client.request_airdrop(public_key, 1_000_000_000)
bal = client.get_balance(public_key) /  1_000_000_000
print(bal)

## backup ltrading logic if i screw things up
if last_price is not None:
        # sell and hold to return args to pass into the trade execution logic later when refactoring
        if price < last_price:
            pnl = f"{(price - last_price) / last_price * 100:.2f}"
            print(f"\tHOLD!\n\tCurrent PnL: {pnl}%\n") 
            state["position"] = f"{pnl}%"
            state["last_price"] = price

        elif price >= last_price and price < (last_price * 1.5):
                pnl = f"{(price - last_price) / last_price * 100:.2f}"
                print(f"\tTarget not met.\n\tCurrent PnL: +{pnl}%\n")
                state["position"] = f"+{pnl}%"
                state["last_price"] = price



def main():
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\nBOT STARTED [{now}]\n")
    while True:  
        # wait for token signal
        if state["token"] is None:
            token = get_token_signal()
            print(f"\nNEW TOKEN: {token}")
            state["token"] = token              
            time.sleep(1)
            continue
        
        # trade active token
        try:
            price = get_price(state["token"])
        except StopIteration:
            print("price feed ended\n")
            reset_trade_state()
            state["token"] = None
            continue

        logic(price)
        time.sleep(2)