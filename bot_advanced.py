import os
import time
import json
import requests
import ccxt
from datetime import datetime, timedelta
import pytz

# === ENV VARIABLES ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === BINANCE CONNECTION ===
BINANCE = ccxt.binance()
BINANCE.load_markets()

# === FILE TO TRACK TRADES ===
TRADES_FILE = "trades.json"

# === SETTINGS ===
LEVERAGE = 20
SIGNALS_PER_DAY = 4
SCAN_INTERVAL = 900  # 15 minutes
SUMMARY_HOUR_IST = 0  # Midnight IST

# === HELPER FUNCTIONS ===

def send_telegram_message(text):
    """Send a message to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def load_trades():
    """Load trade log from file"""
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE, "r") as f:
        return json.load(f)

def save_trades(trades):
    """Save trade log to file"""
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f)

def get_top_50_pairs():
    """Fetch top 50 USDT futures pairs by volume"""
    markets = BINANCE.load_markets()
    usdt_pairs = [m for m in markets if m.endswith("/USDT")]
    tickers = BINANCE.fetch_tickers(usdt_pairs)
    sorted_pairs = sorted(tickers.items(), key=lambda x: x[1]['quoteVolume'], reverse=True)
    top_pairs = [pair for pair, _ in sorted_pairs[:50]]
    return top_pairs

def fetch_price(pair):
    """Fetch current price"""
    return BINANCE.fetch_ticker(pair)['last']

def generate_signals():
    """Scan markets and return up to 4 good signals"""
    signals = []
    pairs = get_top_50_pairs()

    for pair in pairs:
        try:
            ohlcv = BINANCE.fetch_ohlcv(pair, timeframe="15m", limit=50)
        except:
            continue

        closes = [c[4] for c in ohlcv]
        volumes = [c[5] for c in ohlcv]

        # EMA filters
        ema20 = sum(closes[-20:]) / 20
        ema50 = sum(closes[-50:]) / 50
        last_price = closes[-1]

        # RSI calc (simplified)
        gains = [closes[i+1] - closes[i] for i in range(13) if closes[i+1] > closes[i]]
        losses = [closes[i] - closes[i+1] for i in range(13) if closes[i+1] < closes[i]]
        avg_gain = sum(gains) / 14 if gains else 0.01
        avg_loss = sum(losses) / 14 if losses else 0.01
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Conditions for breakout
        if last_price > ema20 > ema50 and rsi > 55:
            direction = "LONG"
            entry = round(last_price, 2)
            tp = round(entry * 1.007, 2)
            sl = round(entry * 0.993, 2)
        elif last_price < ema20 < ema50 and rsi < 45:
            direction = "SHORT"
            entry = round(last_price, 2)
            tp = round(entry * 0.993, 2)
            sl = round(entry * 1.007, 2)
        else:
            continue

        signal = {
            "pair": pair,
            "direction": direction,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "status": "OPEN"
        }
        signals.append(signal)

        if len(signals) >= SIGNALS_PER_DAY:
            break

    return signals

def check_trades(trades):
    """Check each trade to see if TP or SL hit"""
    for trade in trades:
        if trade["status"] != "OPEN":
            continue

        price = fetch_price(trade["pair"])
        if trade["direction"] == "LONG":
            if price >= trade["tp"]:
                trade["status"] = "TP"
                trade["pnl"] = round(((trade["tp"] - trade["entry"]) / trade["entry"]) * LEVERAGE * 100, 2)
                send_telegram_message(f"✅ TP Hit: {trade['pair']} +{trade['pnl']}%")
            elif price <= trade["sl"]:
                trade["status"] = "SL"
                trade["pnl"] = round(((trade["sl"] - trade["entry"]) / trade["entry"]) * LEVERAGE * 100, 2)
                send_telegram_message(f"❌ SL Hit: {trade['pair']} {trade['pnl']}%")
        elif trade["direction"] == "SHORT":
            if price <= trade["tp"]:
                trade["status"] = "TP"
                trade["pnl"] = round(((trade["entry"] - trade["tp"]) / trade["entry"]) * LEVERAGE * 100, 2)
                send_telegram_message(f"✅ TP Hit: {trade['pair']} +{trade['pnl']}%")
            elif price >= trade["sl"]:
                trade["status"] = "SL"
                trade["pnl"] = round(((trade["entry"] - trade["sl"]) / trade["entry"]) * LEVERAGE * 100, 2)
                send_telegram_message(f"❌ SL Hit: {trade['pair']} {trade['pnl']}%")

    return trades

def send_daily_summary():
    """Send full PnL report and reset trades"""
    trades = load_trades()
    if not trades:
        send_telegram_message("📊 No trades today.")
        return

    msg = "📊 Daily PnL Summary – CryptoChampsBot\n\n"
    tp_count = sl_count = 0
    total_pnl = 0.0

    for trade in trades:
        if trade["status"] == "TP":
            msg += f"✅ {trade['pair']} +{trade['pnl']}%\n"
            tp_count += 1
            total_pnl += trade["pnl"]
        elif trade["status"] == "SL":
            msg += f"❌ {trade['pair']} {trade['pnl']}%\n"
            sl_count += 1
            total_pnl += trade["pnl"]
        else:
            msg += f"🔄 {trade['pair']} Still Open\n"

    msg += "\n─────────────\n"
    msg += f"✅ TP Hits: {tp_count} | ❌ SL Hits: {sl_count}\n"
    msg += f"💰 Total PnL: {round(total_pnl, 2)}%"

    send_telegram_message(msg)

    # Reset file for next day
    save_trades([])

# === MAIN LOOP ===
def main():
    print("🚀 Starting CryptoChamps Advanced Bot...")
    last_summary_date = None

    while True:
        trades = load_trades()

        # 1. Check & close trades
        trades = check_trades(trades)
        save_trades(trades)

        # 2. Time for daily summary?
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist)
        if now_ist.hour == SUMMARY_HOUR_IST and (last_summary_date != now_ist.date()):
            send_daily_summary()
            last_summary_date = now_ist.date()

        # 3. Generate new signals only if under daily limit
        open_trades = [t for t in trades if t["status"] == "OPEN"]
        if len(trades) < SIGNALS_PER_DAY:
            new_signals = generate_signals()
            for sig in new_signals:
                trades.append(sig)
                send_telegram_message(
                    f"🔔 {sig['pair']} Futures\n"
                    f"📤 {sig['direction']} Trade\n"
                    f"🎯 Entry: {sig['entry']}\n"
                    f"❌ SL: {sig['sl']} | 🎯 TP: {sig['tp']}\n"
                    f"💥 Leverage: 20x | 📊 RR: 1.5"
                )
            save_trades(trades)

        # 4. Wait before next scan
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()
