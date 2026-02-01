# CoinPilot AI 🚀

自動化加密貨幣分析與出版系統 — 每日比特幣市場日報自動生成器

## 功能特色

- 📊 **資料採集**：自動抓取 BTC 價格、恐慌貪婪指數、熱門新聞
- 🤖 **AI 分析**：使用 GitHub Copilot SDK 生成專業市場日報
- 🌐 **網站發布**：Hugo 靜態網站自動建置

## 系統架構

```
採集層 (Eyes)     → Python 爬蟲抓取 API 資料
                      ↓
大腦層 (Brain)    → Copilot SDK 生成 Markdown 文章
                      ↓
展示層 (Face)     → Hugo 編譯靜態網站
                      ↓
部署層 (Hands)    → GitHub Pages 發布 (手動)
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

```bash
# 執行完整流程 (採集 → AI 生成 → 建置)
python main.py run

# 單獨執行各階段
python main.py collect   # 僅採集資料
python main.py write     # 僅 AI 生成文章
python main.py build     # 僅建置 Hugo 網站

# 使用 Docker
docker compose run --rm app python main.py run
```

## 專案結構

```
CoinPilot AI/
├── src/
│   ├── collector/      # 資料採集模組
│   │   ├── coingecko.py
│   │   ├── fear_greed.py
│   │   ├── news.py
│   │   └── collector.py
│   ├── writer/         # AI 寫作模組
│   │   └── writer.py
│   └── publisher/      # 網站發布模組
│       └── hugo.py
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
| 恐慌貪婪指數 | Alternative.me | `/fng/` |
| 新聞標題 | Google News | RSS Feed |

## 授權

MIT License
