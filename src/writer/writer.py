"""
AI 寫作模組 - 使用 GitHub Copilot SDK 生成市場分析文章
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# System Prompt 模板
SYSTEM_PROMPT = """你是一位專業的加密貨幣市場分析師，專門撰寫比特幣每日市場日報。

## 你的任務
根據我提供的 JSON 格式市場數據，撰寫一篇專業、客觀且易讀的市場日報。

## 寫作風格
- 語氣專業但不過於艱深，適合一般投資人閱讀
- 使用繁體中文撰寫
- 數據要精確引用，不可編造任何未提供的數據
- 根據市場狀況調整語氣：
  - 如果價格下跌超過 5%，語氣要帶有警示
  - 如果情緒指數顯示「極度貪婪」，提醒回調風險
  - 如果情緒指數顯示「極度恐慌」，提醒可能的抄底機會（但仍需謹慎）

## 技術指標解讀規則

### RSI (相對強弱指標)
- RSI > 70：超買區，提醒回調風險，不宜追高
- RSI < 30：超賣區，可能出現反彈，關注底部支撐
- 30-70：中性區間

### MACD (指數平滑異同移動平均線)
- DIF 線向上突破 DEA 線 (黃金交叉) → 看漲訊號
- DIF 線向下突破 DEA 線 (死亡交叉) → 看跌訊號
- MACD 在零軸之上代表多頭動能，之下代表空頭動能

### 移動平均線 (MA)
- 價格在 MA200 之上：長期牛市格局
- 價格在 MA200 之下：長期熊市格局
- MA50 > MA200 (黃金交叉)：中期趨勢向上
- MA50 < MA200 (死亡交叉)：中期趨勢向下

### 布林通道 (Bollinger Bands)
- 價格觸碰上軌：可能過熱，注意回調風險
- 價格觸碰下軌：可能超跌，關注反彈機會
- 通道收窄：即將發生大幅波動

### BTC Dominance (比特幣市佔率)
- BTC.D 上漲：資金回流比特幣，山寨幣可能下跌
- BTC.D 下跌：資金流向山寨幣 (Altcoin Season)

## 輸出格式
必須嚴格遵守以下 Hugo Markdown 格式，包含完整的 Front Matter：

```markdown
---
title: "比特幣日報 - {日期}"
description: "{簡短描述當日市場狀況，30字以內}"
date: {YYYY-MM-DD}
categories:
  - 市場分析
tags:
  - Bitcoin
  - BTC
  - 日報
image: ""
---

## 📊 市場快照

{基於價格數據的客觀描述，包含現價、24小時漲跌幅、交易量}

## 📈 技術面分析

{根據 RSI、MACD、均線、布林通道等技術指標進行分析}
- 引用具體數值（如 RSI 數值、MA50/MA200 價位）
- 說明目前的技術面訊號（超買/超賣、黃金/死亡交叉等）
- 指出關鍵支撐/阻力位

## 🌐 市場結構

{根據 BTC Dominance 分析市場資金流向}
- 說明 BTC 市佔率變化及其意義
- 對山寨幣市場的影響判斷

## 🎭 情緒分析

{結合恐慌貪婪指數與新聞的主觀解讀}

## 💡 操作建議

{綜合技術面、市場結構、情緒面給出建議}
- 根據當前市場狀況給出保守/積極的簡單總結
- 必須加上風險警示

---

*本文由 CoinPilot AI 自動生成，僅供參考，不構成投資建議。*
```

## 重要規則
1. 只能使用我提供的數據，嚴禁編造價格或新聞
2. Front Matter 必須完整且格式正確
3. 日期格式必須為 YYYY-MM-DD
4. 每個章節都要有內容，不可留空
5. 技術指標必須引用 JSON 中的實際數值
6. 若技術指標數據不完整，可簡化該章節但不可留空
"""

# Front Matter 驗證正則表達式
FRONT_MATTER_PATTERN = re.compile(
    r"^---\s*\n"
    r"title:\s*.+\n"
    r"description:\s*.+\n"
    r"date:\s*\d{4}-\d{2}-\d{2}\s*\n"
    r".*?"
    r"---\s*\n",
    re.MULTILINE | re.DOTALL,
)


class Writer:
    """
    AI 文章生成器 - 使用 GitHub Copilot SDK

    使用方式:
        writer = Writer()
        await writer.start()
        article = await writer.generate_article(context_data)
        await writer.save_article(article, "site/content/posts/")
        await writer.stop()
    """

    def __init__(
        self,
        model: str = "gemini-3-flash",
        github_token: Optional[str] = None,
    ):
        """
        初始化 AI 寫作器

        Args:
            model: 使用的 AI 模型 (gemini-3-flash, gpt-4.1, claude-sonnet-4.5)
            github_token: GitHub Token (可選，預設使用環境變數或已登入用戶)
        """
        self.model = model
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.client = None
        self.session = None

    async def start(self):
        """啟動 Copilot SDK 客戶端"""
        try:
            from copilot import CopilotClient

            logger.info(f"正在初始化 Copilot SDK (模型: {self.model})...")

            config = {
                "log_level": os.getenv("LOG_LEVEL", "info"),
                "auto_start": True,
                "auto_restart": True,
            }

            if self.github_token:
                config["github_token"] = self.github_token

            self.client = CopilotClient(config)
            await self.client.start()

            logger.info("Copilot SDK 客戶端已啟動")

        except ImportError:
            logger.error("找不到 github-copilot-sdk，請執行: pip install github-copilot-sdk")
            raise
        except Exception as e:
            logger.error(f"Copilot SDK 啟動失敗: {e}")
            raise

    async def stop(self):
        """停止 Copilot SDK 客戶端"""
        if self.client:
            await self.client.stop()
            logger.info("Copilot SDK 客戶端已停止")

    def _build_prompt(self, context_data: dict) -> str:
        """
        建構使用者提示詞

        Args:
            context_data: 從 collector 獲取的每日市場資料

        Returns:
            str: 完整的使用者提示詞
        """
        today = datetime.now().strftime("%Y-%m-%d")

        prompt = f"""請根據以下 JSON 數據撰寫今日 ({today}) 的比特幣市場日報：

```json
{json.dumps(context_data, indent=2, ensure_ascii=False)}
```

請嚴格按照系統提示中的格式輸出 Markdown 文章。"""

        return prompt

    async def generate_article(self, context_data: dict) -> str:
        """
        生成市場分析文章

        Args:
            context_data: 從 collector 獲取的每日市場資料

        Returns:
            str: 生成的 Markdown 文章

        Raises:
            RuntimeError: SDK 未啟動或生成失敗
            ValueError: 生成的文章格式驗證失敗
        """
        if not self.client:
            raise RuntimeError("Copilot SDK 客戶端未啟動，請先調用 start()")

        logger.info("正在生成市場分析文章...")

        try:
            # 建立會話
            session = await self.client.create_session(
                {
                    "model": self.model,
                    "streaming": False,
                    "system_prompt": SYSTEM_PROMPT,
                }
            )

            # 發送請求並等待回應
            user_prompt = self._build_prompt(context_data)
            response = await session.send_and_wait({"prompt": user_prompt})

            article = response.data.content

            # 驗證 Front Matter 格式
            if not self.validate_front_matter(article):
                logger.warning("生成的文章 Front Matter 格式可能有問題，嘗試修復...")
                article = self._fix_front_matter(article, context_data)

            logger.info(f"文章生成完成 (長度: {len(article)} 字元)")
            return article

        except Exception as e:
            logger.error(f"文章生成失敗: {e}")
            raise

    def validate_front_matter(self, content: str) -> bool:
        """
        驗證 Markdown Front Matter 格式

        Args:
            content: Markdown 文章內容

        Returns:
            bool: 格式是否正確
        """
        # 檢查是否以 --- 開頭
        if not content.strip().startswith("---"):
            return False

        # 檢查是否有結束的 ---
        parts = content.split("---", 2)
        if len(parts) < 3:
            return False

        # 檢查必要欄位
        front_matter = parts[1]
        required_fields = ["title:", "date:"]
        for field in required_fields:
            if field not in front_matter:
                return False

        return True

    def _fix_front_matter(self, content: str, context_data: dict) -> str:
        """
        嘗試修復 Front Matter 格式問題

        Args:
            content: 原始文章內容
            context_data: 市場資料

        Returns:
            str: 修復後的文章
        """
        today = datetime.now().strftime("%Y-%m-%d")
        price = context_data.get("price", {}).get("price_usd", 0)
        change = context_data.get("price", {}).get("price_change_24h", 0)

        # 建立預設 Front Matter
        default_front_matter = f"""---
title: "比特幣日報 - {today}"
description: "BTC ${price:,.0f}，24h {'上漲' if change > 0 else '下跌'} {abs(change):.1f}%"
date: {today}
categories:
  - 市場分析
tags:
  - Bitcoin
  - BTC
  - 日報
image: ""
---

"""

        # 如果內容沒有 Front Matter，直接添加
        if not content.strip().startswith("---"):
            return default_front_matter + content

        # 如果 Front Matter 不完整，替換它
        try:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return default_front_matter + parts[2]
        except Exception:
            pass

        return default_front_matter + content

    async def save_article(
        self,
        content: str,
        output_dir: str | Path,
        filename: Optional[str] = None,
    ) -> Path:
        """
        保存文章到檔案

        Args:
            content: Markdown 文章內容
            output_dir: 輸出目錄
            filename: 檔案名稱 (預設為日期)

        Returns:
            Path: 保存的檔案路徑
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = datetime.now().strftime("%Y-%m-%d") + ".md"

        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"文章已保存至: {filepath}")
        return filepath


class MockWriter(Writer):
    """
    模擬寫作器 - 用於測試或無 SDK 環境

    當 Copilot SDK 無法使用時，使用此類生成範本文章
    """

    async def start(self):
        logger.info("使用 MockWriter (模擬模式)")

    async def stop(self):
        pass

    async def generate_article(self, context_data: dict) -> str:
        """生成模擬文章"""
        today = datetime.now().strftime("%Y-%m-%d")

        price = context_data.get("price", {})
        sentiment = context_data.get("sentiment", {})
        news = context_data.get("news", [])

        price_usd = price.get("price_usd", 0)
        change_24h = price.get("price_change_24h", 0)
        volume = price.get("volume_24h", 0)
        fear_greed = sentiment.get("value", 50)
        fear_greed_zh = sentiment.get("sentiment_zh", "中性")
        emoji = sentiment.get("emoji", "😐")

        # 決定語氣
        if change_24h < -5:
            tone = "⚠️ 市場出現較大波動，投資者需謹慎應對。"
        elif fear_greed > 75:
            tone = "🔔 市場情緒過熱，需警惕回調風險。"
        elif fear_greed < 25:
            tone = "📉 市場情緒極度悲觀，但危機中可能存在機會。"
        else:
            tone = "市場運行平穩，維持觀望態度。"

        # 新聞標題
        news_section = ""
        if news:
            news_section = "今日重點新聞：\n"
            for item in news[:3]:
                news_section += f"- {item.get('title', 'N/A')} ({item.get('source', 'Unknown')})\n"

        article = f"""---
title: "比特幣日報 - {today}"
description: "BTC ${price_usd:,.0f}，24h {'上漲' if change_24h > 0 else '下跌'} {abs(change_24h):.1f}%"
date: {today}
categories:
  - 市場分析
tags:
  - Bitcoin
  - BTC
  - 日報
image: ""
---

## 📊 市場快照

截至今日，比特幣 (BTC) 報價 **${price_usd:,.2f}** 美元。

| 指標 | 數值 |
|------|------|
| 24h 漲跌幅 | {change_24h:+.2f}% |
| 24h 交易量 | ${volume:,.0f} |
| 市值 | ${price.get('market_cap', 0):,.0f} |

{tone}

## 🎭 情緒分析

{emoji} **恐慌貪婪指數：{fear_greed}（{fear_greed_zh}）**

{news_section}

市場情緒目前處於「{fear_greed_zh}」區間。{'投資者普遍樂觀，但需注意追高風險。' if fear_greed > 50 else '投資者偏向謹慎，可能是佈局的時機，但仍需控制風險。'}

## 💡 操作建議

根據當前市場狀況：

- **短期**：{'建議觀望，等待回調後再進場' if fear_greed > 60 else '可小倉位試探性建倉' if fear_greed < 40 else '維持現有部位，密切關注市場變化'}
- **中長期**：比特幣作為加密貨幣龍頭，長期趨勢仍值得關注

> ⚠️ **風險提示**：加密貨幣市場波動劇烈，本文僅供參考，不構成投資建議。請根據自身風險承受能力謹慎決策。

---

*本文由 CoinPilot AI 自動生成，資料來源：CoinGecko、Alternative.me、Google News*
"""

        return article


def get_writer(
    model: str = "gemini-3-flash",
    use_mock: bool = False,
    github_token: Optional[str] = None,
) -> Writer:
    """
    工廠函數 - 獲取適當的 Writer 實例

    Args:
        model: AI 模型名稱
        use_mock: 是否使用模擬寫作器
        github_token: GitHub Token

    Returns:
        Writer: Writer 實例
    """
    if use_mock:
        return MockWriter(model=model)

    try:
        import copilot  # noqa: F401

        return Writer(model=model, github_token=github_token)
    except ImportError:
        logger.warning("Copilot SDK 未安裝，使用 MockWriter")
        return MockWriter(model=model)


if __name__ == "__main__":
    # 測試用
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 測試資料
    test_context = {
        "collected_at": "2026-02-01T09:00:00",
        "price": {
            "price_usd": 98500.00,
            "price_change_24h": -2.35,
            "volume_24h": 28500000000,
            "market_cap": 1950000000000,
        },
        "sentiment": {
            "value": 72,
            "classification": "Greed",
            "sentiment_zh": "貪婪",
            "emoji": "😊",
        },
        "news": [
            {"title": "Bitcoin ETF sees record inflows", "source": "CoinDesk"},
            {"title": "BTC price analysis: Key levels to watch", "source": "Cointelegraph"},
            {"title": "Institutional investors increase Bitcoin holdings", "source": "Bloomberg"},
        ],
    }

    async def test():
        writer = get_writer(use_mock=True)
        await writer.start()
        article = await writer.generate_article(test_context)
        print(article)
        await writer.stop()

    asyncio.run(test())
