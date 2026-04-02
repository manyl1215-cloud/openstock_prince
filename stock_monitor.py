import os
import json
import requests
import pandas as pd
import gspread
import datetime
import yfinance as yf
import time
import random
from google.oauth2.service_account import Credentials
from datetime import timedelta

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
    res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    if res.status_code != 200:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

def get_today_sheet():
    creds_dict = json.loads(GCP_KEY)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    for attempt in range(3):
        try:
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
        except:
            time.sleep(5)
            continue

def run_after_hours_report():
    sheet = get_today_sheet()
    # 模擬更真實的瀏覽器標頭
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    twse_df, tpex_df = None, None
    
    # --- 抓取上市資料 (最多試 3 次) ---
    for i in range(3):
        try:
            twse_res = requests.get("https://www.twse.com.tw/rwd/zh/fund/T86W?response=json&selectType=ALL", headers=headers, timeout=20)
            twse_data = twse_res.json()
            if 'data' in twse_data:
                twse_df = pd.DataFrame(twse_data['data'])
                break
        except:
            time.sleep(random.randint(5, 10))
    
    time.sleep(random.randint(3, 6)) # 兩次抓取間隔

    # --- 抓取上櫃資料 (最多試 3 次) ---
    for i in range(3):
        try:
            tpex_res = requests.get("https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D", headers=headers, timeout=20)
            tpex_data = tpex_res.json()
            if 'aaData' in tpex_data:
                tpex_df = pd.DataFrame(tpex_data['aaData'])
                break
        except:
            time.sleep(random.randint(5, 10))

    if twse_df is None and tpex_df is None:
        return "⚠️ 證交所伺服器拒絕連線，請 10 分鐘後手動重試。"

    chip_data, msg_list = [], []
    for sym, name in stock_dict.items():
        sid, f, t = sym.split('.')[0], 0, 0
        try:
            if sym.endswith('.TW') and twse_df is not None:
                row = twse_df[twse_df[0].str.strip() == sid]
                if not row.empty:
                    f = int(row.iloc[0][2].replace(',','')) // 1000
                    t = int(row.iloc[0][12].replace(',','')) // 1000
            elif sym.endswith('.TWO') and tpex_df is not None:
                row = tpex_df[tpex_df[0].str.strip() == sid]
                if not row.empty:
                    f = int(str(row.iloc[0][8]).replace(',','')) // 1000
                    t = int(str(row.iloc[0][10]).replace(',','')) // 1000
            
            total = f + t
            chip_data.append([total, f, t])
            if abs(total) >= 200:
                icon = "💎" if total > 0 else "💀"
                msg_list.append(f"{icon} `{sid}` {name}: `{total:+d}張`")
        except:
            chip_data.append([0, 0, 0])

    sheet.update('H2:J' + str(len(chip_data) + 1), chip_data)
    msg = "📊 *今日法人籌碼重點 (門檻200張)*\n----------------------------\n"
    msg += "\n".join(msg_list) if msg_list else "今日無大動作標的。"
    return msg

# (run_morning_report 邏輯與之前相同，僅確保呼叫 get_today_sheet)
def run_morning_report():
    sheet = get_today_sheet()
    tickers = list(stock_dict.keys())
    try:
        df_all = yf.download(tickers, period="5d", interval="1d", group_by='ticker', progress=False)
    except: return "❌ Yahoo Finance 連線失敗"

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
    try:
        now = datetime.datetime.utcnow() + timedelta(hours=8)
        if now.weekday() < 5:
            report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
            send_telegram_msg(report)
    except Exception as e:
        send_telegram_msg(f"🆘 程式崩潰: {str(e)}")
