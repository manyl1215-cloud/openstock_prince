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

# 2. 完整監控清單 (順序固定，表單也會依照這個順序排列)
stock_dict = {
    '2454.TW': ['聯發科', 'IC設計'], '2330.TW': ['台積電', '半導體'], '2317.TW': ['鴻海', 'EMS'],
    '2382.TW': ['廣達', 'AI伺服器'], '3711.TW': ['日月光', '封測'], '2308.TW': ['台達電', '電源'],
    '2376.TW': ['技嘉', 'AI伺服器'], '2347.TW': ['聯強', '通路'], '9933.TW': ['中鼎', '工程'],
    '3037.TW': ['欣興', 'PCB'], '4958.TW': ['臻鼎-KY', 'PCB'], '2313.TW': ['華通', 'PCB'],
    '2356.TW': ['英業達', '代工'], '2891.TW': ['中信金', '金融'], '2881.TW': ['富邦金', '金融'],
    '2882.TW': ['國泰金', '金融'], '2834.TW': ['臺企銀', '金融'], '2451.TW': ['創見', '記憶體'],
    '6166.TW': ['凌華', 'IPC'], '2009.TW': ['第一銅', '銅業'], '0050.TW': ['元大台灣50', 'ETF'],
    '006208.TW': ['富邦台50', 'ETF'], '6803.TW': ['崑鼎', '綠能'], '00885.TW': ['富邦越南', 'ETF'],
    '6005.TW': ['群益證', '證券'], '4104.TW': ['佳醫', '生技'], '1476.TW': ['儒鴻', '紡織'],
    '1101.TW': ['台泥', '水泥'], '6919.TW': ['康霈', '生技'], '2618.TW': ['長榮航', '航運'],
    '2409.TW': ['友達', '面板'], '8462.TW': ['柏文', '健身'], '00679B.TW': ['元大美債20', 'ETF'],
    '3293.TWO': ['鈊象', '遊戲'], '8069.TWO': ['元太', '電子紙'], '3653.TWO': ['健策', '散熱'],
    '6217.TWO': ['中探針', '測試'], '8261.TWO': ['富鼎', 'MOSFET'], '5009.TWO': ['榮剛', '鋼鐵'],
    '6237.TWO': ['驊訊', 'IC設計']
}

def get_today_sheet():
    creds_dict = json.loads(GCP_KEY)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    client = gspread.authorize(creds)
    ss = client.open_by_key(SHEET_ID)
    today_str = (datetime.datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
    
    try:
        return ss.worksheet(today_str)
    except gspread.exceptions.WorksheetNotFound:
        # 1. 建立分頁
        new_sheet = ss.add_worksheet(title=today_str, rows="100", cols="12")
        # 2. 寫入標題
        headers = [['日期', '代號', '名稱', '早:溢價', '早:走勢', '早:量', '', '晚:合計', '晚:外資', '晚:投信']]
        new_sheet.update('A1:J1', headers)
        # 3. 預填所有股票名單 (確保每一支都在列)
        init_rows = []
        for sym, info in stock_dict.items():
            init_rows.append([today_str, sym.split('.')[0], info[0]])
        new_sheet.update('A2:C' + str(len(init_rows) + 1), init_rows)
        return new_sheet

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

# --- 模式 A：早盤 (09:15) 更新 D, E, F 欄 ---
def run_morning_report():
    sheet = get_today_sheet()
    morning_data = []
    star_picks = []
    
    for symbol, info in stock_dict.items():
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="2d")
            if len(df) >= 2:
                prev_c, op, now = df['Close'].iloc[-2], df['Open'].iloc[-1], df['Close'].iloc[-1]
                gap, trend = ((op - prev_c)/prev_c)*100, ((now - op)/op)*100
                vol = int(df['Volume'].iloc[-2]/1000)
                morning_data.append([f"{gap:.2f}%", f"{trend:.2f}%", vol])
                if vol >= 3000 and gap >= 2.0:
                    star_picks.append(f"`[{symbol.split('.')[0]}]` {info[0]} (Gap:{gap:.1f}%)")
            else:
                morning_data.append(["無資料", "無資料", 0])
        except:
            morning_data.append(["錯誤", "錯誤", 0])
            
    # 批量更新 D2:F
    sheet.update('D2:F' + str(len(morning_data) + 1), morning_data)
    
    msg = "🌅 *09:15 開盤報告*\n清單已全數列出至 Sheets\n"
    if star_picks:
        msg += "\n🔥 *強勢跳空標的:*\n" + "\n".join(star_picks)
    return msg

# --- 模式 B：盤後 (16:00) 更新 H, I, J 欄 ---
def run_after_hours_report():
    sheet = get_today_sheet()
    try:
        twse = pd.DataFrame(requests.get("https://www.twse.com.tw/rwd/zh/fund/T86W?response=json&selectType=ALL").json()['data'])
        tpex = pd.DataFrame(requests.get("https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D").json()['aaData'])
    except: return "⚠️ 法人資料獲取失敗"

    chip_data = []
    msg_list = []
    for sym, info in stock_dict.items():
        sid, f, t = sym.split('.')[0], 0, 0
        try:
            if sym.endswith('.TW'):
                row = twse[twse[0].str.strip() == sid]
                if not row.empty:
                    f = int(row.iloc[0][2].replace(',',''))//1000
                    t = int(row.iloc[0][12].replace(',',''))//1000
            else:
                row = tpex[tpex[0].str.strip() == sid]
                if not row.empty:
                    f = int(str(row.iloc[0][8]).replace(',',''))//1000
                    t = int(str(row.iloc[0][10]).replace(',',''))//1000
            
            total = f + t
            chip_data.append([total, f, t])
            if abs(total) >= 200:
                msg_list.append(f"`[{sid}]` {info[0]}: {total:+d}")
        except:
            chip_data.append([0, 0, 0])

    # 批量更新 H2:J
    sheet.update('H2:J' + str(len(chip_data) + 1), chip_data)
    
    msg = "📊 *16:00 盤後籌碼*\n清單數據已對齊更新\n"
    if msg_list:
        msg += "\n💎 *法人重點動向:*\n" + "\n".join(msg_list)
    return msg

if __name__ == "__main__":
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    if now.weekday() < 5:
        report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
        send_telegram_msg(report)
