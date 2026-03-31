import os
import json
import yfinance as yf
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials

# 1. 讀取安全資訊 (Secrets)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GCP_KEY = os.getenv('GCP_SERVICE_ACCOUNT_KEY')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')

# 2. 自選股資料庫
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
        
        today = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
        # 寫入格式：日期, 代號, 名稱, 族群, 開盤溢價, 開盤後走勢, 現價, 昨日量
        rows = [[today, i['id'], i['name'], i['sector'], f"{i['gap']:.2f}%", f"{i['trend']:.2f}%", i['now'], i['vol']] for i in data_list]
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
            # 抓取今日與昨日資料
            df = ticker.history(period="2d")
            if len(df) < 2: continue
            
            prev_close = df['Close'].iloc[-2]
            prev_vol = int(df['Volume'].iloc[-2]/1000) # 昨日量(張)
            open_price = df['Open'].iloc[-1]
            current_price = df['Close'].iloc[-1] # 目前價格 (約 09:15)
            
            # 1. 計算開盤溢價 (開盤 vs 昨日收盤)
            gap_rate = ((open_price - prev_close) / prev_close) * 100
            # 2. 計算開盤後走勢 (現價 vs 開盤價)
            trend_rate = ((current_price - open_price) / open_price) * 100
            
            data = {
                'id': symbol.split('.')[0], 'name': name, 'sector': sector, 
                'gap': gap_rate, 'trend': trend_rate, 'now': current_price, 'vol': prev_vol
            }
            
            # 篩選邏輯：量大(>3K) 且 開盤強勢(>2%)
            if prev_vol >= 3000 and gap_rate >= 2.0:
                star_picks.append(data)
            else:
                others.append(data)
        except: continue

    update_google_sheet(star_picks + others) # 將所有追蹤資料寫入紀錄

    msg = "🎯 *09:15 台股量價監控報告* 🎯\n"
    msg += "----------------------------\n"
    
    if star_picks:
        msg += "🔥 *主力強勢股 (量大且高開)*\n"
        for i in star_picks:
            # 根據 15 分鐘走勢給予箭頭
            trend_icon = "🚀" if i['trend'] > 0 else "⚠️" 
            msg += f"`[{i['id']}]` *{i['name']}* ({i['sector']})\n"
            msg += f" ├ 開盤溢價: `{i['gap']:+.2f}%` \n"
            msg += f" └ 15min走勢: *{i['trend']:+.2f}%* {trend_icon}\n"
    
    msg += "\n📊 *其餘監控名單*\n"
    for i in sorted(others, key=lambda x: x['gap'], reverse=True)[:8]:
        t_icon = "⤴️" if i['trend'] > 0 else "⤵️"
        msg += f"`{i['id']}` {i['name']}: Gap `{i['gap']:+.2f}%` | Trend `{i['trend']:+.2f}%` {t_icon}\n"
    
    return msg

if __name__ == "__main__":
    send_telegram_msg(get_report())
