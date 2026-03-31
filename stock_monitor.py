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
    '2376.TW': ['技嘉', 'AI伺服器'], '2347.TW': ['聯強', '通路'], '9933.TW': ['中鼎', '工程'],
    '3037.TW': ['欣興', 'PCB'], '4958.TW': ['臻鼎-KY', 'PCB'], '2313.TW': ['華通', 'PCB'],
    '2356.TW': ['英業達', '代工'], '2891.TW': ['中信金', '金融'], '2881.TW': ['富邦金', '金融'],
    '2882.TW': ['國泰金', '金融'], '2834.TW': ['臺企銀', '金融'], '2451.TW': ['創見', '記憶體'],
    '6166.TW': ['凌華', 'IPC'], '2009.TW': ['第一銅', '銅業'], '0050.TW': ['元大台灣50', 'ETF'],
    '006208.TW': ['富邦台50', 'ETF'], '6803.TW': ['崑鼎', '綠能'], '00885.TW': ['富邦越南', 'ETF'],
    '6005.TW': ['群益證', '證券'], '4104.TW': ['佳醫', '生技'], '1476.TW': ['儒鴻', '紡織'],
    '1101.TW': ['台泥', '水泥'], '6919.TW': ['康霈', '生技'], '2618.TW': ['長榮航', '航運'],
    '2409.TW': ['友達', '面板'], '8462.TW': ['柏文', '健身'], '00679B.TW': ['元大美債20', 'ETF'],
    '00720B.TW': ['元大公司債', 'ETF'], '00933B.TW': ['國泰金融債', 'ETF'], '1513.TW': ['中興電', '能源'],
    '3293.TWO': ['鈊象', '遊戲'], '8069.TWO': ['元太', '電子紙'], '3653.TWO': ['健策', '散熱'],
    '6217.TWO': ['中探針', '測試'], '8261.TWO': ['富鼎', 'MOSFET'], '5009.TWO': ['榮剛', '鋼鐵'],
    '6237.TWO': ['驊訊', 'IC設計']
}

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    if res.status_code != 200: # Markdown 失敗改用純文字
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

def write_to_sheet(rows):
    try:
        creds_dict = json.loads(GCP_KEY)
        creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        sheet.append_rows(rows)
        return True
    except Exception as e:
        send_telegram_msg(f"❌ Sheets 寫入失敗: {str(e)}")
        return False

# --- 早上 09:15 邏輯 ---
def run_morning_report():
    star_picks, log_rows = [], []
    today_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    for symbol, info in stock_dict.items():
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="2d")
            if len(df) < 2: continue
            prev_c, op, now = df['Close'].iloc[-2], df['Open'].iloc[-1], df['Close'].iloc[-1]
            vol = int(df['Volume'].iloc[-2]/1000)
            gap, trend = ((op - prev_c)/prev_c)*100, ((now - op)/op)*100
            data = {'id': symbol.split('.')[0], 'name': info[0], 'gap': gap, 'trend': trend, 'vol': vol}
            if vol >= 3000 and gap >= 2.0: star_picks.append(data)
            # 準備存入 Sheets (格式：日期, 代號, 名稱, 溢價率, 走勢, 合計/量)
            log_rows.append([today_str, data['id'], data['name'], f"{gap:.2f}%", f"{trend:.2f}%", vol])
        except: continue
    
    write_to_sheet(log_rows)
    msg = "🌅 *09:15 開盤強弱勢監控*\n----------------------------\n"
    if star_picks:
        msg += "🔥 *主力強勢跳空*\n"
        for i in star_picks:
            msg += f"`[{i['id']}]` *{i['name']}*: Gap `{i['gap']:+.2f}%` | Trend `{i['trend']:+.2f}%` \n"
    else: msg += "今日暫無符合強勢跳空標的。\n"
    return msg

# --- 下午 16:00 邏輯 ---
def run_after_hours_report():
    try:
        twse = pd.DataFrame(requests.get("https://www.twse.com.tw/rwd/zh/fund/T86W?response=json&selectType=ALL").json()['data'])
        tpex = pd.DataFrame(requests.get("https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D").json()['aaData'])
    except: return "⚠️ 證交所資料抓取失敗。"

    msg = "📊 *今日法人大動作 (門檻200張)*\n----------------------------\n"
    log_rows, today_str = [], datetime.datetime.now().strftime('%Y-%m-%d')
    for sym, info in stock_dict.items():
        sid, f, t = sym.split('.')[0], 0, 0
        if sym.endswith('.TW'):
            row = twse[twse[0].str.strip() == sid]
            if not row.empty:
                f, t = int(row.iloc[0][2].replace(',',''))//1000, int(row.iloc[0][12].replace(',',''))//1000
        else:
            row = tpex[tpex[0].str.strip() == sid]
            if not row.empty:
                f, t = int(str(row.iloc[0][8]).replace(',',''))//1000, int(str(row.iloc[0][10]).replace(',',''))//1000
        
        total = f + t
        log_rows.append([today_str, sid, info[0], total, f, t])
        if abs(total) >= 200:
            icon = "💎" if total > 0 else "💀"
            msg += f"{icon} `[{sid}]` *{info[0]}*: `{(total):+d}張` (外`{f:+}`/投`{t:+}`)\n"
    
    write_to_sheet(log_rows)
    return msg

if __name__ == "__main__":
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    if now.weekday() == 5: # 週六總結
        # 此處可加入您之前的 get_weekly_summary()
        report = "🏆 本週總結報告生成中..."
    elif now.weekday() < 5:
        report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
    else: report = None

    if report: send_telegram_msg(report)
