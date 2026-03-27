import os
import json
import yfinance as yf
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials

# 1. 讀取環境變數
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GCP_KEY = os.getenv('GCP_SERVICE_ACCOUNT_KEY')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')

# 2. 自選股資料
stock_dict = {
    '2454.TW': ['聯發科', 'IC設計'], '2330.TW': ['台積電', '晶圓代工'],
    '2317.TW': ['鴻海', 'EMS/伺服器'], '2382.TW': ['廣達', 'AI伺服器'],
    '3711.TW': ['日月光', '封測'], '2308.TW': ['台達電', '電源供應'],
    '2376.TW': ['技嘉', 'AI伺服器/板卡'], '2347.TW': ['聯強', '通路'],
    '9933.TW': ['中鼎', '工程'], '8069.TWO': ['元太', '電子紙'],
    '3037.TW': ['欣興', 'ABF/PCB'], '4958.TW': ['臻鼎-KY', 'PCB'],
    '2313.TW': ['華通', 'PCB/低軌衛星'], '3653.TWO': ['健策', '散熱/均熱片'],
    '2505.TW': ['國揚', '營建'], '6217.TWO': ['中探針', '探針卡/測試'],
    '8261.TWO': ['富鼎', 'MOSFET'], '1513.TW': ['中興電', '重電/能源'],
    '5009.TWO': ['榮剛', '特殊鋼']
}

def update_google_sheet(data_list):
    if not data_list: return
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds_dict = json.loads(GCP_KEY)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        
        today = pd.Timestamp.now().strftime('%Y-%m-%d')
        rows = [[today, i['id'], i['name'], i['sector'], f"{i['rate']:.2f}%", i['price'], i['vol']] for i in data_list]
        sheet.append_rows(rows)
    except Exception as e: print(f"Google Sheet 更新失敗: {e}")

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_report():
    star_picks, others = [], []
    for symbol, info in stock_dict.items():
        name, sector = info[0], info[1]
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d")
            if len(df) < 2: continue
            prev_close, prev_vol = df['Close'].iloc[-2], int(df['Volume'].iloc[-2]/1000)
            open_price = df['Open'].iloc[-1]
            rate = ((open_price - prev_close) / prev_close) * 100
            data = {'id': symbol.split('.')[0], 'name': name, 'sector': sector, 'rate': rate, 'price': open_price, 'vol': prev_vol}
            if prev_vol >= 3000 and rate >= 2.0: star_picks.append(data)
            else: others.append(data)
        except: continue

    update_google_sheet(star_picks) # 自動存檔

    msg = "🚀 *今日開盤主力強勢股* 🚀\n"
    if not star_picks: msg += "今日無符合條件標的。\n"
    else:
        for i in star_picks:
            msg += f"🔥 `[{i['id']}]` *{i['name']}* ({i['sector']})\n ├ 溢價: `{i['rate']:+.2f}%` (開 {i['price']})\n └ 昨日量: `{i['vol']:,} 張` \n"
    
    msg += "\n📈 *其餘波動* \n"
    for i in sorted(others, key=lambda x: x['rate'], reverse=True)[:10]: # 只取前10名縮短長度
        msg += f"`{i['id']}` {i['name']}: `{i['rate']:+.2f}%`\n"
    return msg

if __name__ == "__main__":
    send_telegram_msg(get_report())
