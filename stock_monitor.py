import os
import yfinance as yf
import pandas as pd
import requests

# 1. 從環境變數讀取 Token (安全考量，不直接寫在程式碼)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 2. 你的自選股清單 (依據圖片整理)
stock_list = [
    '2454.TW', '2330.TW', '2317.TW', '2382.TW', '3711.TW', '2308.TW', 
    '2376.TW', '2347.TW', '9933.TW', '8069.TWO', '3037.TW', '4958.TW',
    '2313.TW', '3653.TWO', '2505.TW', '6217.TWO', '8261.TWO', '1513.TW', '5009.TWO'
]

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def get_report():
    results = []
    for symbol in stock_list:
        try:
            ticker = yf.Ticker(symbol)
            # 抓取兩天資料來計算昨日收盤
            df = ticker.history(period="2d")
            if len(df) < 2: continue
            
            prev_close = df['Close'].iloc[-2]
            open_price = df['Open'].iloc[-1]
            
            # 計算開盤溢價率
            premium_rate = ((open_price - prev_close) / prev_close) * 100
            
            results.append({
                'id': symbol.split('.')[0],
                'rate': premium_rate,
                'price': open_price
            })
        except: continue

    # 按溢價率排序
    sorted_res = sorted(results, key=lambda x: x['rate'], reverse=True)

    # 格式化訊息
    msg = "🚀 *今日台股開盤溢價監控* 🚀\n"
    msg += f"日期: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n"
    msg += "----------------------------\n"
    
    for item in sorted_res:
        icon = "🔥" if item['rate'] >= 3 else "📈" if item['rate'] > 0 else "📉"
        if item['rate'] < -2: icon = "⛈️"
        msg += f"{icon} `{item['id']}`: *{item['rate']:+.2f}%* (開 {item['price']})\n"
    
    msg += "----------------------------\n"
    msg += "_公式：(今日開盤 - 昨日收盤) / 昨日收盤_"
    return msg

if __name__ == "__main__":
    report = get_report()
    send_telegram_msg(report)
