import os
import json
import requests
import pandas as pd
import gspread
import datetime
import yfinance as yf
from google.oauth2.service_account import Credentials
from datetime import timedelta

# ==========================================
# 1. 安全資訊 (由 GitHub Secrets 傳入)
# ==========================================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GCP_KEY = os.getenv('GCP_SERVICE_ACCOUNT_KEY')
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')

# ==========================================
# 2. 完整監控清單 (整合所有截圖標的)
# ==========================================
stock_dict = {
    # 上市標的 (.TW)
    '2454.TW': ['聯發科', 'IC設計'], '2330.TW': ['台積電', '晶圓代工'], '2317.TW': ['鴻海', 'EMS'],
    '2382.TW': ['廣達', 'AI伺服器'], '3711.TW': ['日月光', '封測'], '2308.TW': ['台達電', '電源'],
    '2376.TW': ['技嘉', 'AI伺服器'], '2347.TW': ['聯強', '通路'], '9933.TW': ['中鼎', '工程'],
    '3037.TW': ['欣興', 'PCB'], '4958.TW': ['臻鼎-KY', 'PCB'], '2313.TW': ['華通', 'PCB'],
    '2356.TW': ['英業達', '代工'], '2891.TW': ['中信金', '金融'], '2881.TW': ['富邦金', '金融'],
    '2882.TW': ['國泰金', '金融'], '2834.TW': ['臺企銀', '金融'], '2451.TW': ['創見', '記憶體'],
    '6166.TW': ['凌華', 'IPC'], '2009.TW': ['第一銅', '銅業'], '0050.TW': ['元大台灣50', 'ETF'],
    '006208.TW': ['富邦台50', 'ETF'], '6803.TW': ['崑鼎', '綠能'], '00885.TW': ['富邦越南', 'ETF'],
    '6005.TW': ['群益證', '證券'], '4104.TW': ['佳醫', '生技'], '1476.TW': ['儒鴻', '紡織'],
    '1101.TW': ['台泥', '水泥'], '6919.TW': ['康霈*', '生技'], '2618.TW': ['長榮航', '航運'],
    '2409.TW': ['友達', '面板'], '8462.TW': ['柏文', '健身'], '00679B.TW': ['元大美債20', 'ETF'],
    '00720B.TW': ['元大公司債', 'ETF'], '00933B.TW': ['國泰金融債', 'ETF'], '1513.TW': ['中興電', '能源'],
    
    # 上櫃標的 (.TWO)
    '3293.TWO': ['鈊象', '遊戲'], '8069.TWO': ['元太', '電子紙'], '3653.TWO': ['健策', '散熱'],
    '6217.TWO': ['中探針', '測試'], '8261.TWO': ['富鼎', 'MOSFET'], '5009.TWO': ['榮剛', '鋼鐵'],
    '6237.TWO': ['驊訊', 'IC設計']
}

# ==========================================
# 3. 通用功能函數
# ==========================================
def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_sheet():
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds_dict = json.loads(GCP_KEY)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).get_worksheet(0)

# ==========================================
# 4. 模式 A：早上 09:15 開盤監控
# ==========================================
def run_morning_report():
    star_picks, others = [], []
    for symbol, info in stock_dict.items():
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="2d")
            if len(df) < 2: continue
            prev_c, op, now = df['Close'].iloc[-2], df['Open'].iloc[-1], df['Close'].iloc[-1]
            vol = int(df['Volume'].iloc[-2]/1000)
            gap, trend = ((op - prev_c)/prev_c)*100, ((now - op)/op)*100
            data = {'id': symbol.split('.')[0], 'name': info[0], 'gap': gap, 'trend': trend, 'vol': vol, 'sector': info[1]}
            if vol >= 3000 and gap >= 2.0: star_picks.append(data)
            else: others.append(data)
        except: continue
    
    msg = "🌅 *09:15 開盤強弱勢監控* 🌅\n----------------------------\n"
    if star_picks:
        msg += "🔥 *主力強勢跳空*\n"
        for i in star_picks:
            icon = "🚀" if i['trend'] > 0 else "⚠️"
            msg += f"`[{i['id']}]` *{i['name']}*: Gap `{i['gap']:+.2f}%` | Trend `{i['trend']:+.2f}%` {icon}\n"
    
    msg += "\n📊 *其餘觀察標的*\n"
    for i in sorted(others, key=lambda x: x['gap'], reverse=True)[:8]:
        icon = "⤴️" if i['trend'] > 0 else "⤵️"
        msg += f"`{i['id']}` {i['name']}: `{i['gap']:+.2f}%` ({icon})\n"
    return msg

# ==========================================
# 5. 模式 B：下午 16:00 法人籌碼監控
# ==========================================
def run_after_hours_report():
    try:
        twse = pd.DataFrame(requests.get("https://www.twse.com.tw/rwd/zh/fund/T86W?response=json&selectType=ALL").json()['data'])
        tpex = pd.DataFrame(requests.get("https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=AL&t=D").json()['aaData'])
    except: return "⚠️ 證交所資料更新中，請稍後再試。"

    msg = "📊 *今日法人大動作清單 (門檻200張)* 📊\n----------------------------\n"
    all_data = []
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
        
        res = {'日期': datetime.datetime.now().strftime('%Y-%m-%d'), '代號': sid, '名稱': info[0], '合計': f+t, '外資': f, '投信': t}
        all_data.append(res)
        if abs(f+t) >= 200:
            icon = "💎" if (f+t) > 0 else "💀"
            msg += f"{icon} `[{sid}]` *{info[0]}*: `{(f+t):+d}張` (外`{f:+}`/投`{t:+}`)\n"
    
    # 寫入 Google Sheet
    try:
        sheet = get_sheet()
        sheet.append_rows([list(d.values()) for d in all_data])
    except: pass
    return msg

# ==========================================
# 6. 模式 C：週六 09:00 週籌碼總結
# ==========================================
def run_weekly_summary():
    try:
        df = pd.DataFrame(get_sheet().get_all_records())
        df['日期'] = pd.to_datetime(df['日期'])
        weekly = df[df['日期'] >= (datetime.datetime.now() - timedelta(days=7))]
        summary = weekly.groupby(['代號', '名稱'])['合計'].sum().reset_index().sort_values(by='合計', ascending=False)
        
        msg = "🏆 *本週法人佈局總排行榜* 🏆\n----------------------------\n"
        msg += "💰 *本週最強吸金*\n"
        for _, r in summary.head(5).iterrows():
            if r['合計'] > 0: msg += f"🔥 `[{r['代號']}]` *{r['名稱']}*: `+{int(r['合計'])}張` \n"
        msg += "\n💀 *本週法人棄守*\n"
        for _, r in summary.tail(5).sort_values(by='合計').iterrows():
            if r['合計'] < 0: msg += f"❄️ `[{r['代號']}]` *{r['名稱']}*: `{int(r['合計'])}張` \n"
        return msg
    except: return "⚠️ 週總結計算失敗，請檢查試算表格式。"

# ==========================================
# 7. 主執行邏輯
# ==========================================
if __name__ == "__main__":
    now = datetime.datetime.utcnow() + timedelta(hours=8)
    weekday = now.weekday() # 0=Mon, 5=Sat
    
    if weekday == 5: # 週六
        report = run_weekly_summary()
    elif weekday < 5: # 週一至五
        report = run_after_hours_report() if now.hour >= 14 else run_morning_report()
    else:
        report = None # 週日不執行
        
    if report: send_telegram_msg(report)
