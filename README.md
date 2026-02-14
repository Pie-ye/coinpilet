# CoinPilot AI 🚀

![文章數](https://img.shields.io/badge/文章數-1篇-blue)

自動化加密貨幣分析與出版系統 — 每日比特幣市場日報自動生成器

## 📰 最新快訊

| 日期 | 標題 | 摘要 |
|------|------|------|
| 2026-02-14T14:33:11+08:00 | [比特幣市場日報 - 2026年02月14日](site/content/posts/2026-02-14.md) | 比特幣今日價格 $69,540，24小時上漲 3.39%，市場情緒極度恐慌，技術指標顯示空頭壓力持續 |


## 功能特色

- 📊 **資料採集**：自動抓取 BTC 價格、恐慌貪婪指數、熱門新聞、技術指標
- 🤖 **AI 分析**：使用 GitHub Copilot SDK 生成專業市場日報
- 🌐 **網站發布**：Hugo 靜態網站自動建置
- � **自動部署**：一鍵執行完整流程並推送到 GitHub，Cloudflare Pages 自動部署

## 系統架構

```
採集層 (Eyes)     → Python 爬蟲抓取 API 資料
                      ↓
大腦層 (Brain)    → Copilot SDK 生成 Markdown 文章
                      ↓
展示層 (Face)     → Hugo 編譯靜態網站
                      ↓
部署層 (Hands)    → GitHub Push → Cloudflare Pages 自動部署
```

## 快速開始

### 前置需求

- Python 3.10+
- Hugo Extended (建議安裝 v0.124.1 或更新版本)
- GitHub Copilot CLI (已認證)

### 安裝

#### Windows 一鍵安裝（推薦）

雙擊執行 `install.bat`，自動完成所有安裝步驟：

```powershell
# 雙擊執行 install.bat，或在命令列執行：
.\install.bat
```

腳本會自動：
- ✅ 檢查 Python 版本（>= 3.10）
- ✅ 建立虛擬環境 `.venv`
- ✅ 安裝所有 Python 套件（包含開發工具）
- ✅ 嘗試安裝 Hugo Extended（透過 Chocolatey）
- ✅ 檢查 Git 是否可用
- ✅ 建立必要的資料目錄
- ✅ 複製環境變數範本 `.env`

**安裝完成後**，請編輯 `.env` 檔案並填入您的 `GITHUB_TOKEN`：

```bash
# 編輯 .env 檔案
notepad .env

# 將此行改為您的實際 Token：
GITHUB_TOKEN=ghp_your_actual_token_here
```

然後啟動虛擬環境並開始使用：

```powershell
# 啟動虛擬環境
.venv\Scripts\activate

# 查看系統狀態
python main.py status

# 測試資料採集
python main.py collect
```

---

#### 手動安裝（Linux/macOS 或進階使用者）

##### 1. 安裝 Python 依賴

```bash
# 複製環境變數範本
cp .env.example .env

# 建立虛擬環境（可選）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 安裝 Python 依賴
pip install -e .

# 安裝開發工具（可選）
pip install -e ".[dev]"
```

##### 2. 安裝 Hugo Extended

**Windows**:
```powershell
# 使用 Chocolatey（推薦）
choco install hugo-extended

# 或從 GitHub 手動下載
# https://github.com/gohugoio/hugo/releases
# 請下載 hugo_extended_xxx_windows-amd64.zip
```

**Linux/macOS**:
```bash
# 使用 Homebrew
brew install hugo

# 或使用 Snap
snap install hugo --channel=extended
```

**驗證安裝**：
```bash
hugo version
# 應顯示 "extended" 字樣
```

### 使用方式


```bash
# 執行完整流程 (採集 → AI 生成 → 建置 → 推送)
python main.py run

# 單獨執行各階段
python main.py collect   # 僅採集資料
python main.py write     # 僅 AI 生成文章
python main.py build     # 僅建置 Hugo 網站
python main.py serve     # 啟動 Hugo 開發伺服器
python main.py status    # 查看系統狀態
```

### GitHub 與 Cloudflare Pages 設定

1. **初始化 Git 倉庫**（如果尚未設定）：
   ```bash
   git init
   git remote add origin https://github.com/Pie-ye/coinpilet.git
   git branch -M main
   ```

2. **在 Cloudflare Pages 設定專案**：
   - 前往 Cloudflare Dashboard → Pages
   - 點擊「Create a project」→「Connect to Git」
   - 選擇 GitHub 倉庫 `Pie-ye/coinpilet`
   - **重要設定**：
     - **Production branch**: `main`
     - **Framework preset**: `None`（因為我們本地已經建置好）
     - **Build command**: 留空（不需要）
     - **Build output directory**: `site/public` ⚠️ **必須設為此路徑**
     - **Root directory**: `/`（保持預設）
   - 點擊「Save and Deploy」

   ⚠️ **常見錯誤**：如果看到 "Output directory 'public' not found"，請確認：
   - Build output directory 設為 `site/public`（不是 `public`）
   - `.gitignore` 中沒有忽略 `site/public/`
   - 執行過 `python main.py run` 建置網站

3. **執行一鍵發布**：
   ```bash
   python main.py run
   ```
   系統會自動執行：
   - 📊 採集資料
   - 🤖 AI 生成文章
   - 🔨 本地建置 Hugo 網站（輸出到 `site/public`）
   - 🚀 推送完整專案到 GitHub
   - ✅ Cloudflare Pages 自動偵測 `site/public` 並部署

**注意**：
- 推送**整個專案**到 GitHub（不是只推送 site 資料夾）
- Cloudflare Pages 會自動讀取 `site/public` 目錄的內容進行部署
- 無需在 Cloudflare 上執行建置命令，因為我們在本地已完成建置

## 專案結構

```
CoinPilot AI/
├── src/
│   ├── collector/      # 資料採集模組
│   │   ├── binance.py  # K線數據
│   │   ├── coingecko.py
│   │   ├── fear_greed.py
│   │   ├── news.py
│   │   └── technical.py # 技術指標
│   ├── writer/         # AI 寫作模組
│   │   └── writer.py
│   └── publisher/      # 網站發布模組
│       ├── hugo.py
│       └── github.py   # GitHub 推送 ⭐
├── data/               # JSON 資料暫存
├── site/               # Hugo 網站
│   ├── content/posts/  # 文章存放位置
│   └── config/         # Hugo 設定
├── main.py             # 主入口
└── pyproject.toml      # Python 專案設定
```

## 資料來源

| 資料 | 來源 | API |
|------|------|-----|
| BTC 價格 | CoinGecko | `/api/v3/simple/price` |
| K線數據 | Binance | `/api/v3/klines` |
| 恐慌貪婪指數 | Alternative.me | `/fng/` |
| 新聞標題 | Google News | RSS Feed |
| 技術指標 | pandas-ta | RSI, MACD, MA, BB |

## 環境變數

在 `.env` 檔案中設定：

```bash
# GitHub Copilot（必要，用於 AI 寫作）
GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
COPILOT_MODEL=gemini-3-flash

# CoinGecko API（可選，有 Demo Key 可用）
COINGECKO_API_KEY=your_demo_key

# Git 使用者資訊（可選）
GIT_USER_NAME=CoinPilot Bot
GIT_USER_EMAIL=bot@coinpilot.ai
```

## 授權

MIT License
