import os
import json
import requests
import pandas as pd
import gspread
import datetime
import yfinance as yf
from google.oauth2.service_account import Credentials
from datetime import timedelta

# 1. 安全資訊
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GCP_KEY = os.getenv('GCP_SERVICE_ACCOUNT_KEY')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')

# 2. 監控清單
stock_dict = {
    '2454.TW': ['聯發科', 'IC設計'], '2330.TW': ['台積電', '半導體'], '2317.TW': ['鴻海', 'EMS'],
    '2382.TW': ['廣達', 'AI伺服器'], '3711.TW': ['日月光', '封測'], '2308.TW': ['台達電', '電源'],
    '2376.TW': ['技嘉', 'AI伺服器'], '8069.TWO': ['元太', '電子紙'], '3293.TWO': ['鈊象', '遊戲'],
    '2618.TW': ['長榮航', '航運'], '6919.TW': ['康霈', '生技'], '0050.TW': ['元大台灣50', 'ETF']
    # ... 其他標的請自行保留 ...
}

def get_today_sheet():
    """取得或創建今天日期的工作表"""
    creds_dict = json.loads(GCP_KEY)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    
    today_str = (datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
    
    try:
        # 嘗試開啟今天日期的分頁
        return spreadsheet.worksheet(today_str)
    except gspread.exceptions.WorksheetNotFound:
        # 如果找不到，就新建一個，並初始化標題
        new_sheet = spreadsheet.add_worksheet(title=today_str, rows="100", cols="15")
        headers = [['日期', '代號', '名稱', '早:溢價', '早:走勢', '早:量', '', '晚:合計', '晚:外資', '晚:投信']]
        new_sheet.update('A1:J1', headers)
        return new_sheet

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

# --- 早盤模式：填入 A-F 欄 ---
def run_morning_report():
    log_rows = []
    today_str = (datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
    date_only = today_str.split(' ')[0]
    
    for symbol, info in stock_dict.items():
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="2d")
            if len(df) < 2: continue
            prev_c, op, now = df['Close'].iloc[-2], df['Open'].iloc[-1], df['Close'].iloc[-1]
            gap, trend = ((op - prev_c)/prev_c)*100, ((now - op)/op)*100
            vol = int(df['Volume'].iloc[-2]/1000)
            log_rows.append([date_only, symbol.split('.')[0], info[0], f"{gap:.2f}%", f"{trend:.2f}%", vol])
        except: continue
    
    sheet = get_today_sheet()
    sheet.append_rows(log_rows)
    return f"🌅 {date_only} 早盤數據已建立分頁並寫入。"

# --- 盤後模式：更新 H-J 欄 ---
def run_after_hours_report():
    try:
        twse = pd.DataFrame(requests.get("https://www.twse.com.tw/rwd/zh/fund/T86W?response=json&selectType=ALL").json()['data'])
        tpex = pd.DataFrame(requests.get("https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D").json()['aaData'])
    except: return "⚠️ 法人資料抓取失敗"

    sheet = get_today_sheet()
    all_values = sheet.get_all_values() # 讀取今天這張表的所有內容
    
    msg = "📊 今日籌碼強弱對比\n----------------------------\n"
    
    for sym, info in stock_dict.items():
        sid, f, t = sym.split('.')[0], 0, 0
        # 抓取法人數據邏輯
        if sym.endswith('.TW'):
            row_data = twse[twse[0].str.strip() == sid]
            if not row_data.empty:
                f, t = int(row_data.iloc[0][2].replace(',',''))//1000, int(row_data.iloc[0][12].replace(',',''))//1000
        else:
            row_data = tpex[tpex[0].str.strip() == sid]
            if not row_data.empty:
                f, t = int(str(row_data.iloc[0][8]).replace(',',''))//1000, int(str(row_data.iloc[0][10]).replace(',',''))//1000
        
        total = f + t
        # 在今天的表中尋找該股票在哪一列
        row_idx = -1
        for i, row in enumerate(all_values):
            if len(row) > 1 and row[1] == sid:
                row_idx = i + 1
                break
        
        if row_idx != -1:
            # 找到列，更新 H, I, J (第 8, 9, 10 欄)
            sheet.update(f"H{row_idx}:J{row_idx}", [[total, f, t]])
            if abs(total) >= 200:
                icon = "💎" if total > 0 else "💀"
                msg += f"{icon} `[{sid}]` {info[0]}: `{total:+d}張` (外`{f:+}`/投`{t:+}`)\n"
        else:
            # 萬一早盤沒跑，就在最後補一列
            sheet.append_row([(datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d'), sid, info[0], "", "", "", "", total, f, t])

    return msg

if __name__ == "__main__":
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    if now.weekday() < 5:
        report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
        send_telegram_msg(report)
