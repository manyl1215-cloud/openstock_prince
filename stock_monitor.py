import os
import json
import requests
import pandas as pd
import gspread
import datetime
import yfinance as yf
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
    # 嘗試用 Markdown，失敗則用純文字（避免名稱中有特殊字元）
    res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    if res.status_code != 200:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

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
        headers = [['日期', '代號', '名稱', '早:溢價', '早:走勢', '早:量', '', '晚:合計', '晚:外資', '晚:投信']]
        sheet.update('A1:J1', headers)
    
    # 強制檢查並初始化 A、B、C 欄
    vals = sheet.col_values(1)
    if len(vals) < 2:
        init_rows = [[today_str, sym.split('.')[0], name] for sym, name in stock_dict.items()]
        sheet.update('A2:C' + str(len(init_rows) + 1), init_rows)
    return sheet

def run_morning_report():
    sheet = get_today_sheet()
    tickers = list(stock_dict.keys())
    # 整批下載，設定 period="5d" 確保一定有資料
    try:
        df_all = yf.download(tickers, period="5d", interval="1d", group_by='ticker', progress=False)
    except Exception as e:
        return f"❌ Yahoo Finance 抓取失敗: {str(e)}"

    morning_data, positive_gaps = [], []
    for symbol in tickers:
        try:
            name = stock_dict[symbol]
            df = df_all[symbol]
            # 取得最後兩個交易日
            if len(df) >= 2:
                prev_c = df['Close'].iloc[-2]
                op = df['Open'].iloc[-1]
                now = df['Close'].iloc[-1]
                vol = int(df['Volume'].iloc[-2] / 1000)
                
                gap = ((op - prev_c) / prev_c) * 100
                trend = ((now - op) / op) * 100
                
                morning_data.append([f"{gap:.2f}%", f"{trend:.2f}%", vol])
                # 只要溢價 > 0 就列出
                if gap > 0:
                    positive_gaps.append(f"`{symbol.split('.')[0]}` {name}: `{gap:+.2f}%`")
            else:
                morning_data.append(["無資料", "-", 0])
        except:
            morning_data.append(["錯誤", "-", 0])

    # 批量更新 D 到 F 欄
    sheet.update('D2:F' + str(len(morning_data) + 1), morning_data)
    
    msg = f"🌅 *今日早盤溢價名單* (正溢價)\n----------------------------\n"
    msg += "\n".join(positive_gaps) if positive_gaps else "今日無正溢價標的。"
    return msg

def run_after_hours_report():
    sheet = get_today_sheet()
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        twse = pd.DataFrame(requests.get("https://www.twse.com.tw/rwd/zh/fund/T86W?response=json&selectType=ALL", headers=headers).json()['data'])
        tpex = pd.DataFrame(requests.get("https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D", headers=headers).json()['aaData'])
    except: return "⚠️ 籌碼資料抓取失敗"

    chip_data, msg_list = [], []
    for sym, name in stock_dict.items():
        sid, f, t = sym.split('.')[0], 0, 0
        try:
            if sym.endswith('.TW'):
                row = twse[twse[0].str.strip() == sid]
                if not row.empty:
                    f = int(row.iloc[0][2].replace(',','')) // 1000
                    t = int(row.iloc[0][12].replace(',','')) // 1000
            else:
                row = tpex[tpex[0].str.strip() == sid]
                if not row.empty:
                    f = int(str(row.iloc[0][8]).replace(',','')) // 1000
                    t = int(str(row.iloc[0][10]).replace(',','')) // 1000
            chip_data.append([f+t, f, t])
            if abs(f+t) >= 200: msg_list.append(f"`{sid}` {name}: `{f+t:+d}張`")
        except: chip_data.append([0, 0, 0])

    sheet.update('H2:J' + str(len(chip_data) + 1), chip_data)
    msg = "📊 *盤後籌碼重點 (門檻200張)*\n----------------------------\n"
    msg += "\n".join(msg_list) if msg_list else "今日無大動作標的。"
    return msg

if __name__ == "__main__":
    try:
        now = datetime.datetime.utcnow() + timedelta(hours=8)
        if now.weekday() < 5:
            report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
            send_telegram_msg(report)
    except Exception as e:
        send_telegram_msg(f"🆘 程式崩潰紀錄: {str(e)}")
