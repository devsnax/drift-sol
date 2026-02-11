import requests
import time


TELEGRAM_BOT_TOKEN = "8478994630:AAEcHWH87pXg92XzKFYMsKz0rJonHeS332M"
TELEGRAM_CHAT_ID = "5889182403"

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

def main():
    start_time = time.time()
    send_telegram_message("Delay test")
    end_time = time.time()
    print("Message sent!")
    print(f"Ran in: {end_time - start_time:.2f}s\n")

if __name__ == "__main__":
    main()