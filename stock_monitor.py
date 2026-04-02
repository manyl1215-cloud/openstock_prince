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
GCP_KEY_JSON = os.getenv('GCP_SERVICE_ACCOUNT_KEY')
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

def fetch_chips_with_ultimate_fallback():
    """修正版抓取：加入精確日期參數"""
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    today_dash = now.strftime('%Y-%m-%d')
    today_nodash = now.strftime('%Y%m%d')
    
    # 策略 1: FinMind
    dl = DataLoader()
    try:
        df = dl.taiwan_stock_institutional_investors(dataset="TaiwanStockInstitutionalInvestorsBuySell", start_date=today_dash)
        if not df.empty: return "finmind", df
    except: pass
    
    # 策略 2: 直連證交所 (修正 404 問題)
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Referer': 'https://www.twse.com.tw/'
    }
    
    try:
        # 強制指定日期參數，解決 404
        twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86W?date={today_nodash}&selectType=ALL&response=json"
        tpex_url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D"
        
        twse_res = session.get(twse_url, headers=headers, timeout=15)
        tpex_res = session.get(tpex_url, headers=headers, timeout=15)
        
        if twse_res.status_code == 200 and tpex_res.status_code == 200:
            return "direct", (pd.DataFrame(twse_res.json()['data']), pd.DataFrame(tpex_res.json()['aaData']))
        else:
            return "fail", f"TWSE:{twse_res.status_code} TPEx:{tpex_res.status_code}"
    except Exception as e:
        return "error", str(e)

def run_after_hours_report():
    # 初始化 Sheets
    creds_dict = json.loads(GCP_KEY_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    client = gspread.authorize(creds)
    ss = client.open_by_key(SHEET_ID)
    today_str = (datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
    
    try:
        sheet = ss.worksheet(today_str)
    except gspread.exceptions.WorksheetNotFound:
        sheet = ss.add_worksheet(title=today_str, rows="100", cols="15")
        sheet.update('A1:J1', [['日期', '代號', '名稱', '早:溢價', '早:走勢', '早:量', '', '晚:合計', '晚:外資', '晚:投信']])
    
    if not sheet.acell('A2').value:
        init_rows = [[today_str, sym.split('.')[0], name] for sym, name in stock_dict.items()]
        sheet.update('A2:C' + str(len(init_rows) + 1), init_rows)

    mode, raw_data = fetch_chips_with_ultimate_fallback()
    if mode in ["fail", "error"]:
        return f"⚠️ 抓取失敗！原因: {raw_data}"
    
    chip_data, msg_list = [], []
    for sym, name in stock_dict.items():
        sid, f, t = sym.split('.')[0], 0, 0
        try:
            if mode == "finmind":
                stock_df = raw_data[raw_data['stock_id'] == sid]
                f = stock_df[stock_df['name'] == 'Foreign_Investor_Buy_Sell']['buy_sell'].sum() // 1000
                t = stock_df[stock_df['name'] == 'Investment_Trust_Buy_Sell']['buy_sell'].sum() // 1000
            else:
                twse, tpex = raw_data
                if sym.endswith('.TW'):
                    row = twse[twse[0].str.strip() == sid]
                    if not row.empty:
                        f, t = int(row.iloc[0][2].replace(',',''))//1000, int(row.iloc[0][12].replace(',',''))//1000
                else:
                    row = tpex[tpex[0].str.strip() == sid]
                    if not row.empty:
                        f, t = int(str(row.iloc[0][8]).replace(',',''))//1000, int(str(row.iloc[0][10]).replace(',',''))//1000
            
            chip_data.append([f+t, f, t])
            if abs(f+t) >= 200:
                icon = "💎" if f+t > 0 else "💀"
                msg_list.append(f"{icon} `{sid}` {name}: `{f+t:+d}張`")
        except:
            chip_data.append([0, 0, 0])

    sheet.update('H2:J' + str(len(chip_data) + 1), chip_data)
    return f"📊 *今日籌碼重點 (模式: {mode})*\n----------------------------\n" + "\n".join(msg_list)

if __name__ == "__main__":
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    if now.weekday() < 5:
        report = run_after_hours_report() if now.hour >= 14 else "目前為早盤監控時段..."
        send_telegram_msg(report)
