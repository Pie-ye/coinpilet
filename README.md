# CoinPilot AI 🚀

自動化加密貨幣分析與出版系統 — 每日比特幣市場日報自動生成器

## 功能特色

- 📊 **資料採集**：自動抓取 BTC 價格、恐慌貪婪指數、熱門新聞、技術指標
- 🤖 **AI 分析**：使用 GitHub Copilot SDK 生成專業市場日報
- 🌐 **網站發布**：Hugo 靜態網站自動建置
- 🖥️ **Web GUI**：簡易 Web 控制台，一鍵採集、生成、發布
- 🚀 **自動部署**：推送到 GitHub，Cloudflare Pages 自動部署

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
- Hugo Extended
- GitHub Copilot CLI (已認證)
- Docker (可選)

### 安裝

```bash
# 複製環境變數範本
cp .env.example .env

# 安裝 Python 依賴
pip install -e .

# 或使用 Docker
docker compose build
```

### 使用方式

#### 🖥️ Web GUI（推薦）

```bash
# 啟動 Web 控制台
python main.py web

# 或使用 Docker
docker compose up web
```

然後在瀏覽器開啟 http://localhost:8000，使用 Web 介面控制：

- 🔄 **抓取資料** - 採集最新市場數據
- 📊 **查看報告** - 預覽 JSON 資料
- 🚀 **發布網站** - 執行完整流程並推送到 GitHub

#### ⌨️ CLI（命令列）

```bash
# 執行完整流程 (採集 → AI 生成 → 建置 → 推送)
python main.py run

# 單獨執行各階段
python main.py collect   # 僅採集資料
python main.py write     # 僅 AI 生成文章
python main.py build     # 僅建置 Hugo 網站
python main.py serve     # 啟動 Hugo 開發伺服器
python main.py status    # 查看系統狀態

# 使用 Docker
docker compose run --rm app python main.py run
```

### GitHub 與 Cloudflare Pages 設定

1. **初始化 Git 倉庫**（如果尚未設定）：
   ```bash
   git init
   git remote add origin https://github.com/Pie-ye/coinpilet.git
   git branch -M main
   ```

2. **在 Cloudflare Pages 設定專案**：
   - 連結 GitHub 倉庫 `Pie-ye/coinpilet`
   - 建置目錄：`site/public`
   - 分支：`main`

3. **使用 Web GUI 發布**：
   - 點擊「🚀 發布網站」按鈕
   - 系統會自動執行：採集 → 生成 → 建置 → 推送
   - Cloudflare Pages 會自動偵測並部署

## 專案結構

```
CoinPilot AI/
├── src/
│   ├── api/            # Web API 模組 ⭐
│   │   └── server.py   # FastAPI 伺服器
│   ├── web/            # 前端介面 ⭐
│   │   └── static/
│   │       └── index.html
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
├── pyproject.toml      # Python 專案設定
├── Dockerfile
└── docker-compose.yml
```

## 資料來源

| 資料 | 來源 | API |
|------|------|-----|
| BTC 價格 | CoinGecko | `/api/v3/simple/price` |
| K線數據 | Binance | `/api/v3/klines` |
| 恐慌貪婪指數 | Alternative.me | `/fng/` |
| 新聞標題 | Google News | RSS Feed |
| 技術指標 | pandas-ta | RSI, MACD, MA, BB |

## API 端點（Web GUI）

| 端點 | 方法 | 功能 |
|------|------|------|
| `/` | GET | Web 控制台首頁 |
| `/api/status` | GET | 系統狀態 |
| `/api/report` | GET | 查看採集報告 |
| `/api/collect` | POST | 執行資料採集 |
| `/api/publish` | POST | 完整發布流程 |
| `/api/github/push` | POST | 僅推送到 GitHub |

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
