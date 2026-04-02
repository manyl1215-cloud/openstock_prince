import os
import json
import requests
import pandas as pd
import gspread
import datetime
import yfinance as yf
import time
from google.oauth2.service_account import Credentials
from datetime import timedelta
from FinMind.data import DataLoader

# 1. 基礎設定
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GCP_KEY = os.getenv('GCP_SERVICE_ACCOUNT_KEY')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')

stock_dict = {
    '2454.TW': '聯發科', '2330.TW': '台積電', '2317.TW': '鴻海', '2382.TW': '廣達',
    '3711.TW': '日月光', '2308.TW': '台達電', '2376.TW': '技嘉', '2347.TW': '聯強',
    '9933.TW': '中鼎', '3037.TW': '欣興', '4958.TW': '臻鼎-KY', '2313.TW': '華通',
    '2356.TW': '英業達', '2891.TW': '中信金', '2881.TW': '富邦金', '2882.TW': '國泰金',
    '2834.TW': '臺企銀', '2451.TW': '創見', '6166.TW': '凌華', '2009.TW': '第一銅',
    '0050.TW': '元大台灣50', '006208.TW': '富邦台50', '6803.TW': '崑鼎', '00885.TW': '富邦越南',
    '6005.TW': '群益證', '4104.TW': '佳醫', '1476.TW': '儒鴻', '1101.TW': '台泥',
    '6919.TW': '康霈', '2618.TW': '長榮航', '2409.TW': '友達', '8462.TW': '柏文',
    '00679B.TW': '元大美債20', '3293.TWO': '鈊象', '8069.TWO': '元太', '3653.TWO': '健策',
    '6217.TWO': '中探針', '8261.TWO': '富鼎', '5009.TWO': '榮剛', '6237.TWO': '驊訊'
}

def send_telegram_msg(message):
    if not message: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_today_sheet():
    creds_dict = json.loads(GCP_KEY)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    client = gspread.authorize(creds)
    ss = client.open_by_key(SHEET_ID)
    today_str = (datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
    try:
        sheet = ss.worksheet(today_str)
    except gspread.exceptions.WorksheetNotFound:
        sheet = ss.add_worksheet(title=today_str, rows="100", cols="12")
        sheet.update('A1:J1', [['日期', '代號', '名稱', '早:溢價', '早:走勢', '早:量', '', '晚:合計', '晚:外資', '晚:投信']])
    if not sheet.acell('A2').value:
        init_rows = [[today_str, sym.split('.')[0], name] for sym, name in stock_dict.items()]
        sheet.update('A2:C' + str(len(init_rows) + 1), init_rows)
    return sheet

def run_after_hours_report():
    sheet = get_today_sheet()
    dl = DataLoader()
    today_str = (datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
    
    try:
        # 使用 FinMind 抓取今日法人買賣超資料
        df = dl.taiwan_stock_institutional_investors(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            start_date=today_str
        )
    except Exception as e:
        return f"⚠️ FinMind 連線異常: {str(e)}"

    if df.empty:
        return f"📊 {today_str} 法人資料尚未更新，請 16:30 後再試。"

    chip_data, msg_list = [], []
    for sym, name in stock_dict.items():
        sid = sym.split('.')[0]
        try:
            # 篩選該股票今日的數據
            stock_df = df[df['stock_id'] == sid]
            # 外資 = Foreign_Investor_Buy_Sell, 投信 = Investment_Trust_Buy_Sell
            f = stock_df[stock_df['name'] == 'Foreign_Investor_Buy_Sell']['buy_sell'].sum() // 1000
            t = stock_df[stock_df['name'] == 'Investment_Trust_Buy_Sell']['buy_sell'].sum() // 1000
            
            total = f + t
            chip_data.append([total, f, t])
            if abs(total) >= 200:
                icon = "💎" if total > 0 else "💀"
                msg_list.append(f"{icon} `{sid}` {name}: `{total:+d}張`")
        except:
            chip_data.append([0, 0, 0])

    sheet.update('H2:J' + str(len(chip_data) + 1), chip_data)
    msg = f"📊 *{today_str} 法人籌碼動態*\n----------------------------\n"
    msg += "\n".join(msg_list) if msg_list else "今日無大動作標的。"
    return msg

def run_morning_report():
    sheet = get_today_sheet()
    tickers = list(stock_dict.keys())
    df_all = yf.download(tickers, period="5d", interval="1d", group_by='ticker', progress=False)
    
    morning_data, positive_gaps = [], []
    for symbol in tickers:
        try:
            df = df_all[symbol]
            if not df.empty and len(df) >= 2:
                prev_c, op, now = df['Close'].iloc[-2], df['Open'].iloc[-1], df['Close'].iloc[-1]
                gap, trend = ((op - prev_c) / prev_c) * 100, ((now - op) / op) * 100
                vol = int(df['Volume'].iloc[-2] / 1000)
                morning_data.append([f"{gap:.2f}%", f"{trend:.2f}%", vol])
                if gap > 0: positive_gaps.append(f"`{symbol.split('.')[0]}` {stock_dict[symbol]}: `{gap:+.2f}%`")
            else: morning_data.append(["-", "-", 0])
        except: morning_data.append(["err", "-", 0])

    sheet.update('D2:F' + str(len(morning_data) + 1), morning_data)
    msg = f"🌅 *今日早盤溢價名單*\n----------------------------\n"
    msg += "\n".join(positive_gaps) if positive_gaps else "今日無正溢價標的。"
    return msg

if __name__ == "__main__":
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    if now.weekday() < 5:
        report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
        send_telegram_msg(report)
