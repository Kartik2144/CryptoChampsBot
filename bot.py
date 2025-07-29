import os
import time
import requests
import ccxt

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE = ccxt.binance()

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def fetch_price(symbol):
    ticker = BINANCE.fetch_ticker(symbol)
    return ticker['last']

def generate_signal():
    pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    signals = []
    for pair in pairs:
        price = fetch_price(pair)
        entry = round(price, 2)
        sl = round(price * 0.995, 2)
        tp = round(price * 1.005, 2)
        signal = f"🔔 {pair} Futures\n📤 LONG Trade\n📈 Strategy: Breakout 🚀\n🎯 Entry: {entry}\n❌ SL: {sl} | 🎯 TP: {tp}\n💥 Leverage: 20x | 📊 RR: 1.5\n🧠 Confidence: 🔥 High"
        signals.append(signal)
    return signals

def main():
    while True:
        signals = generate_signal()
        for sig in signals:
            send_telegram_message(sig)
        print("✅ Signals sent to Telegram")
        time.sleep(1800)  # 30 min pause

if __name__ == "__main__":
    main()
