# openstock_prince
開盤溢價率自動通知

---

# 🚀 台股開盤溢價監控機器人 (Taiwan Stock Opening Monitor)

這是一個自動化監控台股**「開盤溢價率（跳空幅度）」**的工具。每天早上 **09:01**，系統會自動抓取預設的自選股清單，計算開盤價相對於昨日收盤價的漲跌幅，並透過 **Telegram Bot** 即時推送報表到你的手機。

---

## 📌 核心功能
* **自動化執行**：利用 GitHub Actions，無需開電腦，每個交易日準時執行。
* **精準計算**：計算「開盤溢價率」，快速掌握盤前強勢與弱勢股。
* **即時通知**：整合 Telegram 機器人，支援 Markdown 美化排版。
* **自選監控**：涵蓋台積電、聯發科、奇鋐、健策等 AI 與電子指標股。

---

## 📈 計算公式
本工具所定義的「開盤溢價率」即為**開盤跳空漲幅**：

$$\text{開盤溢價率 (\%)} = \frac{\text{今日開盤價} - \text{昨日收盤價}}{\text{昨日收盤價}} \times 100\%$$

---

## 🛠️ 技術棧 (Tech Stack)
* **Language**: Python 3.10+
* **Libraries**: `yfinance`, `pandas`, `requests`
* **Platform**: GitHub Actions (Node.js 24 運行環境)
* **Notification**: Telegram Bot API

---

## ⚙️ 設定步驟 (Setup)

### 1. Telegram 機器人準備
1.  透過 `@BotFather` 創立機器人，取得 **`TELEGRAM_TOKEN`**。
2.  透過 `@GetIDBot` 取得你的個人 **`TELEGRAM_CHAT_ID`**。

### 2. GitHub Secrets 設定
在 GitHub Repository 的 `Settings > Secrets and variables > Actions` 中新增以下兩個密鑰：
* `TELEGRAM_TOKEN`: 你的機器人 Token。
* `TELEGRAM_CHAT_ID`: 你的聊天 ID (例如: `7856977680`)。

### 3. 部署自動化腳本
確保專案路徑包含：
* `stock_monitor.py`: 主程式邏輯。
* `.github/workflows/main.yml`: 定時任務設定檔。

---

## 📋 監控清單 (Stock List)
目前監控包含以下族群（依據群組一與群組五整理）：
* **權值/AI**: 2330 台積電, 2454 聯發科, 2317 鴻海, 2382 廣達。
* **散熱/散熱模組**: 3017 奇鋐, 3653 健策。
* **其他指標**: 8069 元太, 3081 聯亞, 3711 日月光投控, 1513 中興電等。

---

## ⏰ 執行排程
* **執行時間**：每週一至週五 09:01 (台灣時間)。
* **觸發機制**：GitHub Actions Cron Job (`1 1 * * 1-5` UTC)。

---

## 📂 檔案結構
```text
.
├── .github/workflows/
│   └── main.yml          # GitHub Actions 自動化排程
├── stock_monitor.py       # Python 核心監控程式
└── README.md              # 專案說明文件 (本檔案)
```

---

### ⚠️ 免責聲明
本工具僅供技術交流與個人盤勢追蹤參考，不構成任何投資建議。投資人應獨立判斷、審慎評估並自負投資風險。

---

**你需要我幫你把這段 MD 語法直接轉成 `.md` 檔案上傳的建議嗎？或者需要我在 README 中加入更多關於「如何解讀溢價率」的教學？**
