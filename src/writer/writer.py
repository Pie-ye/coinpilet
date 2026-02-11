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

# System Prompt 模板（超精簡版 - 避免超時）
SYSTEM_PROMPT = """你是專業的加密貨幣分析師。

請撰寫比特幣市場日報（至少 800 字），包含：
1. 市場快照 - 價格、交易量分析（使用 Hugo figure shortcode 插入圖表：{{{{< figure src="/images/btc_daily.png" >}}}}）
2. 技術分析 - RSI、MACD、MA 解讀
3. 新聞分析 - 翻譯新聞並評估影響
4. 操作建議 - 投資建議

使用繁體中文，Markdown 格式，必須包含 YAML Front Matter。
直接輸出文章，不要額外說明。"""

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
        
        # BAIA 圖表數據 (由 AnalystAgent 提供)
        self.chart_data: Optional[dict] = None

    async def start(self):
        """啟動 Copilot SDK 客戶端"""
        try:
            from copilot import CopilotClient

            logger.info(f"正在初始化 Copilot SDK (模型: {self.model})...")

            # 按照官方文檔建立客戶端（不需要配置參數）
            self.client = CopilotClient()
            
            logger.info("Copilot SDK 客戶端已啟動")

        except ImportError:
            logger.error("找不到 github-copilot-sdk，請執行: pip install github-copilot-sdk")
            raise
        except Exception as e:
            logger.error(f"Copilot SDK 啟動失敗: {e}", exc_info=True)
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
        
        # 建構圖表資訊提示
        chart_info = ""
        if self.chart_data:
            chart_info = f"""

## 📈 BTC 走勢圖

圖表已由 BAIA Agent 自動生成並保存，請在文章「市場快照」章節開頭嵌入以下圖片：

![BTC 24小時走勢圖](/images/btc_daily.png)

圖表數據摘要：
- 當前價格: ${self.chart_data.get('current_price', 0):,.2f}
- 24H 漲跌幅: {self.chart_data.get('price_change_24h', 0):+.2f}%
- 24H 最高: ${self.chart_data.get('price_high_24h', 0):,.2f}
- 24H 最低: ${self.chart_data.get('price_low_24h', 0):,.2f}
"""

        prompt = f"""請根據以下 JSON 數據撰寫今日 ({today}) 的比特幣市場日報：

```json
{json.dumps(context_data, indent=2, ensure_ascii=False)}
```
{chart_info}
請嚴格按照系統提示中的格式輸出 Markdown 文章。"""

        return prompt
    
    def _build_simplified_prompt(self, context_data: dict) -> str:
        """
        建構簡化的提示詞（不傳送完整 JSON，避免超時）
        
        Args:
            context_data: 從 collector 獲取的每日市場資料
            
        Returns:
            str: 簡化的提示詞
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 提取關鍵數據
        price = context_data.get("price", {})
        sentiment = context_data.get("sentiment", {})
        technical = context_data.get("technical", {})
        news = context_data.get("news", [])[:5]  # 只取前 5 則
        market_structure = context_data.get("market_structure", {})
        
        # 建構圖表資訊
        chart_info = ""
        if self.chart_data:
            chart_info = f"""
**K 線圖數據**:
- 當前價格: ${self.chart_data.get('current_price', 0):,.2f}
- 24H 漲跌幅: {self.chart_data.get('price_change_24h', 0):+.2f}%
- 圖表已生成: /images/btc_daily.png
"""
        
        # 建構新聞摘要
        news_summary = ""
        if news:
            news_summary = "\n**今日新聞**:\n"
            for i, item in enumerate(news, 1):
                title = item.get('title', 'N/A')
                source = item.get('source', 'Unknown')
                summary = item.get('content_summary', item.get('summary', ''))
                if summary:
                    summary = summary[:300] + "..." if len(summary) > 300 else summary
                news_summary += f"{i}. 【{source}】{title}\n   摘要: {summary}\n\n"
        
        prompt = f"""請撰寫今日 ({today}) 的比特幣市場日報。

**重要**: 請直接輸出完整的 Markdown 文章，不要生成摘要或大綱！

## 市場數據

### 💰 價格數據
- 當前價格: ${price.get('price_usd', 0):,.2f}
- 24H 漲跌: {price.get('price_change_24h', 0):+.2f}%
- 24H 交易量: ${price.get('volume_24h', 0):,.0f}
- 市值: ${price.get('market_cap', 0):,.0f}
- 最後更新: {price.get('last_updated', today)}

### 😱 市場情緒
- 恐慌貪婪指數: {sentiment.get('value', 50)} ({sentiment.get('sentiment_zh', '中性')}) {sentiment.get('emoji', '')}
- 分類: {sentiment.get('classification', 'N/A')}

### 📊 技術指標

**RSI(14)**:
- 數值: {technical.get('rsi', {}).get('value', 'N/A')}
- 訊號: {technical.get('rsi', {}).get('signal_zh', 'N/A')}
- 說明: {technical.get('rsi', {}).get('description', '')}

**MACD**:
- DIF: {technical.get('macd', {}).get('dif', 'N/A')}
- DEA: {technical.get('macd', {}).get('dea', 'N/A')}
- Histogram: {technical.get('macd', {}).get('histogram', 'N/A')}
- 訊號: {technical.get('macd', {}).get('signal_zh', 'N/A')}

**移動平均線**:
- MA50: ${technical.get('moving_averages', {}).get('ma_50', 0):,.2f}
- MA200: ${technical.get('moving_averages', {}).get('ma_200', 0):,.2f}
- 當前價格 vs MA200: {technical.get('moving_averages', {}).get('distance_from_ma200', 0):+.2f}%
- 訊號: {technical.get('moving_averages', {}).get('signal_zh', 'N/A')}

**布林通道**:
- 上軌: ${technical.get('bollinger_bands', {}).get('upper', 0):,.2f}
- 中軌: ${technical.get('bollinger_bands', {}).get('middle', 0):,.2f}
- 下軌: ${technical.get('bollinger_bands', {}).get('lower', 0):,.2f}
- Bandwidth: {technical.get('bollinger_bands', {}).get('bandwidth', 0):.2f}
- 訊號: {technical.get('bollinger_bands', {}).get('signal_zh', 'N/A')}

**綜合技術訊號**: {technical.get('summary', {}).get('signal_zh', 'N/A')}

### 🌐 市場結構
- BTC 市值佔比: {market_structure.get('btc_dominance', 0):.2f}%
- 總市值: ${market_structure.get('total_market_cap', 0):,.0f}
- 訊號: {market_structure.get('signal_zh', 'N/A')}
{chart_info}
{news_summary}

## 你的任務

請根據以上數據撰寫一篇**完整的市場日報**（至少 1500 字），包含：

1. **完整的 YAML Front Matter** (如上面格式所示)
2. **K 線圖嵌入** (使用 Hugo shortcode)
3. **市場快照章節** - 詳細分析價格、交易量、市值
4. **技術面分析章節** - 逐一解讀每個技術指標（RSI、MACD、MA、布林通道）
5. **新聞分析章節** - 翻譯新聞標題並分析市場影響
6. **操作建議章節** - 給出具體的投資建議和風險提示

**注意**: 
- 直接輸出 Markdown 文章，從 `---` 開始
- 不要添加「已完成」、「文件已保存」等說明文字
- 每個章節都要有充實的內容，不要過於簡潔
- 新聞要翻譯成繁體中文並詳細分析"""
        
        return prompt
    
    def set_chart_data(self, chart_data: dict) -> None:
        """
        設定圖表數據 (由 BAIA AnalystAgent 調用)
        
        Args:
            chart_data: 包含 current_price, price_change_24h 等欄位的字典
        """
        self.chart_data = chart_data
        logger.info(f"已設定圖表數據: ${chart_data.get('current_price', 0):,.2f}")

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
            # 按照官方文檔建立會話（不使用 streaming，避免事件處理問題）
            session = await self.client.create_session({
                "model": self.model
            })

            # 簡化 prompt - 不傳送完整 JSON，改為結構化摘要
            user_prompt = self._build_simplified_prompt(context_data)
            
            # 組合 system prompt 和 user prompt
            full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

            # 發送請求並等待回應
            logger.info(f"發送請求到模型 {self.model}...")
            logger.info("⏳ 正在生成文章，這可能需要 2-3 分鐘，請耐心等待...")
            
            response = await session.send_and_wait(
                {"prompt": full_prompt},
                timeout=300.0  # 設置為 5 分鐘 (300 秒)
            )
            
            # 從回應中提取文章內容
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

    async def generate_comprehensive_report(
        self,
        multi_day_contexts: list,
        persona_decisions: "MultiStrategyDecisions",
        portfolio_allocation: "PortfolioAllocation",
    ) -> str:
        """
        生成綜合投資報告（整合多日資料和四位投資者決策）

        Args:
            multi_day_contexts: 多日的 DailyContext 列表（按日期排序，最舊到最新）
            persona_decisions: 四位投資者的決策結果
            portfolio_allocation: 資金配置建議

        Returns:
            str: 生成的 Markdown 報告

        Raises:
            RuntimeError: SDK 未啟動或生成失敗
        """
        if not self.client:
            raise RuntimeError("Copilot SDK 客戶端未啟動，請先調用 start()")

        logger.info("正在生成綜合投資報告...")

        try:
            # 建立會話
            session = await self.client.create_session({
                "model": self.model
            })

            # 建構綜合報告的 prompt
            user_prompt = self._build_comprehensive_prompt(
                multi_day_contexts,
                persona_decisions,
                portfolio_allocation,
            )
            
            # 綜合報告專用的 System Prompt
            system_prompt = """你是專業的加密貨幣投資顧問團隊主筆。

請撰寫一份綜合投資報告（至少 1500 字），包含：

1. **市場回顧** - 分析過去數天的價格走勢、關鍵事件和趨勢變化
2. **技術分析** - 多日的 RSI、MACD、MA 趨勢分析，識別關鍵支撐/阻力
3. **新聞影響評估** - 整理並深入分析近期重要新聞對市場的影響
4. **四位投資者觀點** - 展示並分析 Guardian/Quant/Strategist/Degen 的決策差異
5. **資金配置建議** - 針對 100 萬美元資金提供具體的 BTC 購買/持有/賣出建議
6. **風險提示** - 詳細說明當前市場風險和注意事項

使用繁體中文，Markdown 格式，必須包含 YAML Front Matter。
報告標題格式：「比特幣綜合投資報告 - YYYY-MM-DD」
直接輸出文章，不要額外說明。"""

            full_prompt = f"{system_prompt}\n\n{user_prompt}"

            # 發送請求
            logger.info(f"發送請求到模型 {self.model}...")
            logger.info("⏳ 正在生成綜合報告，這可能需要 3-5 分鐘，請耐心等待...")
            
            response = await session.send_and_wait(
                {"prompt": full_prompt},
                timeout=400.0  # 綜合報告需要更長時間
            )
            
            article = response.data.content

            # 驗證並修復 Front Matter
            if not self.validate_front_matter(article):
                logger.warning("報告 Front Matter 格式有問題，嘗試修復...")
                article = self._fix_comprehensive_front_matter(article, multi_day_contexts)

            logger.info(f"綜合報告生成完成 (長度: {len(article)} 字元)")
            return article

        except Exception as e:
            logger.error(f"綜合報告生成失敗: {e}")
            raise

    def _build_comprehensive_prompt(
        self,
        multi_day_contexts: list,
        persona_decisions: "MultiStrategyDecisions",
        portfolio_allocation: "PortfolioAllocation",
    ) -> str:
        """建構綜合報告的 Prompt"""
        from datetime import datetime
        
        today = datetime.now().strftime("%Y-%m-%d")
        days_count = len(multi_day_contexts)
        
        # 建構多日市場數據摘要
        market_timeline = "## 📅 市場時間線\n\n"
        for i, ctx in enumerate(multi_day_contexts):
            ctx_date = ctx.metadata.get("date", ctx.collected_at[:10])
            price = ctx.price.get("price_usd", 0)
            change = ctx.price.get("change_24h", 0)
            
            # 技術指標
            tech = ctx.technical
            rsi = tech.get("rsi", {}).get("value", "N/A")
            macd_signal = tech.get("macd", {}).get("signal_zh", "N/A")
            
            # 情緒
            sentiment = ctx.sentiment
            fg_value = sentiment.get("value", 50)
            fg_label = sentiment.get("sentiment_zh", "中性")
            
            # 新聞數量
            news_count = len(ctx.news)
            
            trend_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            market_timeline += f"### {ctx_date} {trend_emoji}\n"
            market_timeline += f"- 價格: ${price:,.2f} ({change:+.2f}%)\n"
            market_timeline += f"- RSI: {rsi} | MACD: {macd_signal}\n"
            market_timeline += f"- 恐懼貪婪: {fg_value} ({fg_label})\n"
            market_timeline += f"- 新聞數: {news_count} 則\n\n"
        
        # 建構新聞彙總
        news_summary = "## 📰 近期重要新聞\n\n"
        all_news = []
        for ctx in multi_day_contexts:
            ctx_date = ctx.metadata.get("date", ctx.collected_at[:10])
            for news in ctx.news[:3]:  # 每天最多 3 則
                all_news.append({
                    "date": ctx_date,
                    "title": news.get("title", ""),
                    "source": news.get("source", ""),
                    "summary": news.get("content_summary", news.get("summary", ""))[:300],
                })
        
        for i, news in enumerate(all_news[:10], 1):  # 最多 10 則
            news_summary += f"{i}. **[{news['date']}]** {news['title']}\n"
            news_summary += f"   來源: {news['source']}\n"
            if news['summary']:
                news_summary += f"   摘要: {news['summary']}\n"
            news_summary += "\n"
        
        # 建構四位投資者決策表
        decisions_table = "## 🎭 四位投資者決策\n\n"
        decisions_table += persona_decisions.to_markdown_table()
        decisions_table += "\n\n"
        
        # 建構資金配置建議
        allocation_section = "## 💰 $1,000,000 資金配置建議\n\n"
        allocation_section += portfolio_allocation.format_summary()
        allocation_section += "\n\n"
        
        # 取最新一天的詳細技術數據
        latest_ctx = multi_day_contexts[-1]
        latest_tech = latest_ctx.technical
        
        tech_details = "## 📊 最新技術指標詳情\n\n"
        tech_details += f"**RSI(14)**: {latest_tech.get('rsi', {}).get('value', 'N/A')}\n"
        tech_details += f"- 訊號: {latest_tech.get('rsi', {}).get('signal_zh', 'N/A')}\n\n"
        tech_details += f"**MACD**: {latest_tech.get('macd', {}).get('signal_zh', 'N/A')}\n"
        tech_details += f"- DIF: {latest_tech.get('macd', {}).get('dif', 'N/A')}\n"
        tech_details += f"- DEA: {latest_tech.get('macd', {}).get('dea', 'N/A')}\n\n"
        ma = latest_tech.get("moving_averages", {}) or latest_tech.get("ma", {})
        tech_details += f"**移動平均線**:\n"
        tech_details += f"- MA50: ${ma.get('ma_50', ma.get('ma50', 0)):,.2f}\n"
        tech_details += f"- MA200: ${ma.get('ma_200', ma.get('ma200', 0)):,.2f}\n\n"
        bb = latest_tech.get("bollinger_bands", {}) or latest_tech.get("bollinger", {})
        tech_details += f"**布林通道**:\n"
        tech_details += f"- 上軌: ${bb.get('upper', 0):,.2f}\n"
        tech_details += f"- 中軌: ${bb.get('middle', 0):,.2f}\n"
        tech_details += f"- 下軌: ${bb.get('lower', 0):,.2f}\n\n"
        
        # 組合完整 prompt
        prompt = f"""請根據以下資料撰寫綜合投資報告（日期：{today}，分析過去 {days_count} 天）：

**重要**: 請直接輸出完整的 Markdown 報告，從 `---` 開始！

{market_timeline}
{news_summary}
{tech_details}
{decisions_table}
{allocation_section}

## 你的任務

請根據以上數據撰寫一份**專業的綜合投資報告**（至少 1500 字），必須包含：

1. **完整的 YAML Front Matter**（title, description, date, categories, tags）
2. **市場回顧**：總結過去 {days_count} 天的價格走勢和關鍵轉折點
3. **技術面深度分析**：詳細解讀各技術指標的趨勢變化
4. **新聞影響評估**：分析近期新聞對市場的影響（翻譯成繁體中文）
5. **四位投資者觀點對比**：分析 Guardian/Quant/Strategist/Degen 的決策差異和理由
6. **資金配置建議**：針對 $1,000,000 提供具體操作建議（買入金額、BTC 數量等）
7. **風險提示與免責聲明**

**注意**: 
- 從 `---` 開始輸出，不要有多餘文字
- 每個章節都要詳盡分析，不要過於簡潔
- 新聞標題要翻譯成繁體中文
- 資金配置必須提供具體金額（如「建議買入 $300,000，約 4.5 BTC」）"""

        return prompt

    def _fix_comprehensive_front_matter(self, content: str, contexts: list) -> str:
        """修復綜合報告的 Front Matter"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if contexts:
            latest = contexts[-1]
            price = latest.price.get("price_usd", 0)
            change = latest.price.get("change_24h", 0)
        else:
            price = 0
            change = 0

        default_front_matter = f"""---
title: "比特幣綜合投資報告 - {today}"
description: "BTC ${price:,.0f}，整合四位 AI 投資者觀點的深度分析報告"
date: {today}
categories:
  - 投資報告
tags:
  - Bitcoin
  - BTC
  - 投資建議
  - AI分析
image: ""
---

"""
        if not content.strip().startswith("---"):
            return default_front_matter + content

        try:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return default_front_matter + parts[2]
        except Exception:
            pass

        return default_front_matter + content

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
    
    def _translate_news_title(self, title: str) -> str:
        """翻譯新聞標題為繁體中文 (使用 AI 或規則式)"""
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='en', target='zh-TW')
            return translator.translate(title)
        except Exception as e:
            logger.warning(f"標題翻譯失敗: {e}")
            return title
    
    def _generate_event_explanation(self, title: str, content: str) -> str:
        """生成繁體中文事件說明（約200字精煉總結）"""
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='en', target='zh-TW')
            
            # 智能截取：取前 2000 字元作為總結基礎（避免翻譯 API 限制）
            # 但不添加省略號，而是要求完整總結重點
            content_to_translate = content[:2000] if content and len(content) > 2000 else (content or title)
            translated = translator.translate(content_to_translate)
            
            # 生成完整事件說明（無省略號）
            # 如果內容較長，翻譯結果已經是精煉版本
            explanation = f"根據報導，{translated}"
            
            return explanation
        except Exception as e:
            logger.warning(f"事件說明生成失敗: {e}")
            return f"這則新聞報導了關於「{title}」的最新發展。由於翻譯服務暫時無法使用，建議讀者參閱原文以獲得完整資訊。"

    def _analyze_news_impact(self, title: str, content: str) -> str:
        """生成至少 100 字的市場影響評估"""
        title_lower = title.lower()
        content_lower = content.lower() if content else ""
        text = title_lower + " " + content_lower
        
        # 正面影響關鍵字
        positive_keywords = [
            "surge", "rally", "bullish", "adoption", "approval", "etf approved",
            "institutional", "invest", "buy", "record high", "breakout", "accumulation",
            "inflow", "上漲", "突破", "利好", "批准", "機構入場", "看漲"
        ]
        
        # 負面影響關鍵字
        negative_keywords = [
            "crash", "bearish", "ban", "regulation", "crackdown", "hack", "drop", "fall", "plunge",
            "scam", "fraud", "lawsuit", "sell-off", "decline", "outflow", "liquidation",
            "暴跌", "禁止", "監管", "訴訟", "駭客", "詐騙", "利空"
        ]
        
        positive_count = sum(1 for kw in positive_keywords if kw in text)
        negative_count = sum(1 for kw in negative_keywords if kw in text)
        
        if positive_count > negative_count:
            return """📈 **潛在利好消息**

這則新聞可能對比特幣及加密貨幣市場產生正面影響。從市場心理學角度分析，此類消息通常會提振投資者信心，可能吸引更多資金流入市場。短期內可能出現買盤增加的現象，對價格形成支撐。

**建議應對策略**：投資者可持續關注後續發展，但不宜追高。若持有部位，可適當持有等待市場消化此消息；若空倉，可等待回調後的進場機會。需注意市場對利好消息的反應程度，若價格反應不如預期強烈，可能顯示賣壓仍重。"""
        elif negative_count > positive_count:
            return """📉 **潛在利空消息**

這則新聞可能對市場造成短期壓力。從歷史經驗來看，類似的負面消息往往會觸發恐慌性拋售，導致價格短期內出現較大波動。市場情緒可能轉向保守，部分槓桿倉位可能面臨清算風險。

**建議應對策略**：建議投資者保持謹慎，密切觀察市場反應。若持有部位，可考慮減倉或設置止損以控制風險；若空倉，不建議貿然抄底，應等待市場情緒穩定、技術指標出現反轉訊號後再考慮進場。關注成交量變化，若放量下跌後縮量企穩，可能是築底訊號。"""
        else:
            return """⚖️ **中性消息，影響有待觀察**

這則新聞的市場影響方向尚不明確，需要結合其他因素綜合判斷。市場對此類消息的解讀可能存在分歧，短期內可能加劇價格波動，但不太可能改變中長期趨勢。

**建議應對策略**：投資者應密切關注市場的後續反應及輿論走向。若市場解讀偏向正面，可能成為上漲催化劑；若解讀偏向負面，則需警惕回調風險。建議維持現有策略，等待更明確的方向訊號出現。同時可關注其他技術指標和籌碼面數據，做出更全面的判斷。"""

    def _generate_derivatives_section(self, derivatives: dict) -> str:
        """生成籌碼面分析章節"""
        if not derivatives:
            return ""
        
        oi = derivatives.get("open_interest", {})
        ls = derivatives.get("long_short_ratio", {})
        flow = derivatives.get("exchange_flow", {})
        
        section = """## 📊 籌碼面分析

籌碼面數據是觀察大戶動向和市場結構的重要指標。以下分析基於 Coinglass 提供的即時數據：

"""
        
        # OI 分析
        if oi:
            total_oi = oi.get("total_oi_usd", 0)
            oi_change = oi.get("oi_change_24h", 0)
            funding = oi.get("weighted_funding_rate", 0)
            oi_signal = oi.get("signal_zh", "")
            
            section += f"""### 未平倉合約量 (Open Interest)

- **總 OI**: ${total_oi:,.0f}
- **24H 變化**: {oi_change:+.2f}%
- **加權資金費率**: {funding:+.4f}%

{oi_signal}

"""
        
        # 多空比分析
        if ls:
            long_ratio = ls.get("long_ratio", 50)
            short_ratio = ls.get("short_ratio", 50)
            ls_ratio = ls.get("long_short_ratio", 1.0)
            ls_signal = ls.get("signal_zh", "")
            
            section += f"""### 多空比 (Long/Short Ratio)

- **多頭佔比**: {long_ratio:.1f}%
- **空頭佔比**: {short_ratio:.1f}%
- **多空比**: {ls_ratio:.2f}

{ls_signal}

"""
        
        # 交易所流量分析
        if flow:
            net_flow = flow.get("net_flow_usd", 0)
            inflow = flow.get("inflow_usd", 0)
            outflow = flow.get("outflow_usd", 0)
            flow_signal = flow.get("signal_zh", "")
            
            flow_type = "流入" if net_flow > 0 else "流出"
            section += f"""### 交易所淨流入/流出

- **淨{flow_type}**: ${abs(net_flow):,.0f}
- **總流入**: ${inflow:,.0f}
- **總流出**: ${outflow:,.0f}

{flow_signal}

"""
        
        # 籌碼面綜合判斷
        section += """### 籌碼面綜合判斷

"""
        signals = []
        if oi and oi.get("signal") in ["bullish", "overheated"]:
            signals.append("OI 上漲顯示資金活躍")
        if oi and oi.get("signal") in ["deleveraging"]:
            signals.append("OI 下降顯示去槓桿")
        if ls and ls.get("signal") == "extreme_long":
            signals.append("多頭過度擁擠，警惕多殺多")
        if ls and ls.get("signal") == "extreme_short":
            signals.append("空頭過度擁擠，可能軋空")
        if flow and flow.get("signal") == "selling_pressure":
            signals.append("大量流入交易所，賣壓增加")
        if flow and flow.get("signal") == "accumulation":
            signals.append("大量流出交易所，籌碼被鎖定")
        
        if signals:
            section += "綜合籌碼面訊號：" + "、".join(signals) + "。"
        else:
            section += "籌碼面整體呈現中性，無明顯極端訊號。大戶動向尚不明確，建議持續觀察。"
        
        section += "\n\n"
        return section

    def _generate_news_summary(self, news_items: list) -> str:
        """生成新聞整體影響總結"""
        if not news_items:
            return ""
        
        summary_parts = []
        summary_parts.append("**整體新聞影響評估：**\n")
        summary_parts.append(f"今日共分析 {len(news_items)} 則重點新聞。")
        
        # 統計新聞類型
        topics = []
        for item in news_items:
            content = item.get('content_summary', '') + item.get('title', '')
            content_lower = content.lower()
            
            if any(kw in content_lower for kw in ['etf', 'sec', 'regulation', '監管']):
                topics.append('監管政策')
            if any(kw in content_lower for kw in ['institution', 'investment', '機構', '投資']):
                topics.append('機構動態')
            if any(kw in content_lower for kw in ['technology', 'upgrade', 'network', '技術', '升級']):
                topics.append('技術發展')
            if any(kw in content_lower for kw in ['price', 'market', 'trading', '價格', '市場']):
                topics.append('市場動態')
        
        if topics:
            unique_topics = list(set(topics))[:3]
            topic_str = "、".join(unique_topics)
            summary_parts.append(f"主要關注領域包括：{topic_str}。")
        
        summary_parts.append("\n\n投資者應綜合考量上述新聞及技術面、籌碼面分析，制定相應的交易策略。")
        
        return "".join(summary_parts)

    async def generate_article(self, context_data: dict) -> str:
        """生成模擬文章"""
        today = datetime.now().strftime("%Y-%m-%d")

        price = context_data.get("price", {})
        sentiment = context_data.get("sentiment", {})
        news = context_data.get("news", [])
        technical = context_data.get("technical", {})
        market_structure = context_data.get("market_structure", {})
        derivatives = context_data.get("derivatives", {})

        price_usd = price.get("price_usd", 0)
        change_24h = price.get("price_change_24h", 0)
        volume = price.get("volume_24h", 0)
        market_cap = price.get("market_cap", 0)
        
        fear_greed = sentiment.get("value", 50)
        fear_greed_zh = sentiment.get("sentiment_zh", "中性")
        emoji = sentiment.get("emoji", "😐")

        # 技術指標
        rsi = technical.get("rsi", {})
        macd = technical.get("macd", {})
        ma = technical.get("moving_averages", {})
        bb = technical.get("bollinger_bands", {})
        
        # 市場結構
        btc_dom = market_structure.get("btc_dominance", 0)
        btc_dom_signal = market_structure.get("signal_zh", "")
        
        # 籌碼面分析章節
        derivatives_section = self._generate_derivatives_section(derivatives)

        # 決定語氣
        if change_24h < -5:
            tone = "⚠️ 市場出現較大波動，投資者需謹慎應對。"
        elif fear_greed > 75:
            tone = "🔔 市場情緒過熱，需警惕回調風險。"
        elif fear_greed < 25:
            tone = "📉 市場情緒極度悲觀，但危機中可能存在機會。"
        else:
            tone = "市場運行平穩，維持觀望態度。"

        # 新聞分析 - 使用繁體中文事件說明和詳細市場影響評估
        news_section = ""
        news_impact_summary = ""
        if news:
            news_section = "### 今日重點新聞\n\n"
            news_with_content = []
            
            for i, item in enumerate(news[:5], 1):
                title = item.get('title', 'N/A')
                source = item.get('source', 'Unknown')
                content_summary = item.get('content_summary', '')
                content = item.get('content', content_summary)
                fetch_error = item.get('fetch_error', '')
                
                # 翻譯標題為繁體中文
                title_zh = self._translate_news_title(title)
                
                news_section += f"#### 新聞 {i}: {title_zh}\n\n"
                news_section += f"**來源**: {source}\n\n"
                news_section += f"**原文標題**: {title}\n\n"
                
                # 生成繁體中文事件說明 (取代內容摘要)
                if content_summary and len(content_summary) > 50:
                    news_with_content.append(item)
                    
                    # 事件說明
                    event_explanation = self._generate_event_explanation(title, content_summary)
                    news_section += f"📌 **事件說明**:\n\n{event_explanation}\n\n"
                    
                    # 詳細市場影響評估 (至少 100 字)
                    impact = self._analyze_news_impact(title, content_summary)
                    news_section += f"📊 **市場影響評估**:\n\n{impact}\n\n"
                elif fetch_error:
                    news_section += f"*（無法取得文章內容：{fetch_error}）*\n\n"
                    # 即使沒有內容，也基於標題生成簡單評估
                    impact = self._analyze_news_impact(title, "")
                    news_section += f"📊 **市場影響評估**:\n\n{impact}\n\n"
                else:
                    # Fallback 到 RSS summary
                    rss_summary = item.get('summary', '')
                    if rss_summary:
                        event_explanation = self._generate_event_explanation(title, rss_summary)
                        news_section += f"📌 **事件說明**:\n\n{event_explanation}\n\n"
                        impact = self._analyze_news_impact(title, rss_summary)
                        news_section += f"📊 **市場影響評估**:\n\n{impact}\n\n"
                        news_with_content.append(item)
                    else:
                        news_section += "*（無摘要資訊）*\n\n"
                
                news_section += "---\n\n"
            
            # 整體新聞影響總結
            if news_with_content:
                news_impact_summary = self._generate_news_summary(news_with_content)
            else:
                news_impact_summary = "由於無法取得完整新聞內容，建議投資者自行查閱相關新聞來源以了解市場最新動態。"

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

{{{{< figure src="/images/btc_daily.png" alt="BTC 24小時走勢圖" >}}}}

## 📊 市場快照

截至今日 ({today})，比特幣 (BTC) 報價 **${price_usd:,.2f}** 美元。過去 24 小時價格變動 **{change_24h:+.2f}%**，{'創下本週新低' if change_24h < -5 else '呈現小幅回調' if change_24h < 0 else '維持穩定走勢' if abs(change_24h) < 2 else '出現明顯上漲'}。

| 指標 | 數值 |
|------|------|
| 24h 漲跌幅 | {change_24h:+.2f}% |
| 24h 交易量 | ${volume:,.0f} |
| 市值 | ${market_cap:,.0f} |
| 最後更新 | {price.get('last_updated', today)} |

{tone}

## 📈 技術面分析

根據最新的技術指標數據，以下是各項重要指標的分析：

### RSI 相對強弱指標

當前 RSI(14) 數值為 **{rsi.get('value', 'N/A')}**。{rsi.get('signal_zh', '市場處於中性區間，無明顯超買超賣訊號。')}

{'根據 RSI 指標，市場已進入超賣區域，歷史數據顯示這通常預示著短期反彈的可能性，但投資者仍需等待更明確的反轉訊號。' if rsi.get('signal') == 'oversold' else '當前 RSI 顯示市場處於超買狀態，短期內可能面臨獲利回吐壓力，建議謹慎追高。' if rsi.get('signal') == 'overbought' else ''}

### MACD 指標

MACD 線為 **{macd.get('macd', 'N/A')}**，信號線為 **{macd.get('signal', 'N/A')}**，柱狀圖為 **{macd.get('histogram', 'N/A')}**。

{macd.get('signal_zh', 'MACD 指標顯示市場趨勢中性。')}

{'MACD 位於零軸下方顯示當前市場仍處於空頭動能主導，短期內需觀察是否能突破零軸轉為多頭格局。' if macd.get('macd', 0) < 0 else 'MACD 位於零軸上方，多頭動能持續，但需注意是否出現背離訊號。' if macd.get('macd', 0) > 0 else ''}

### 移動平均線分析

- **MA50**: ${ma.get('sma_50', 'N/A'):,.2f}
- **MA200**: ${ma.get('sma_200', 'N/A'):,.2f}
- **當前價格**: ${ma.get('current_price', price_usd):,.2f}

{ma.get('signal_zh', '均線系統顯示市場趨勢中性。')}

當前價格相對 MA200 偏離 **{ma.get('price_vs_ma200_pct', 0):+.1f}%**，{'顯示市場嚴重超跌，但也代表距離長期均線支撐較遠，反彈空間可觀。' if ma.get('price_vs_ma200_pct', 0) < -20 else '顯示價格相對合理。' if abs(ma.get('price_vs_ma200_pct', 0)) < 10 else ''}

### 布林通道

- **上軌**: ${bb.get('upper', 'N/A'):,.2f}
- **中軌**: ${bb.get('middle', 'N/A'):,.2f}
- **下軌**: ${bb.get('lower', 'N/A'):,.2f}
- **帶寬**: {bb.get('bandwidth', 'N/A')}

{bb.get('signal_zh', '價格位於布林通道中軌附近，市場波動正常。')}

{'通道帶寬收窄預示市場即將發生大幅波動，投資者應做好應對準備，可能的方向需結合其他指標判斷。' if bb.get('squeeze', False) else ''}

### 綜合技術訊號

根據上述技術指標分析，{'技術面呈現多空交織的複雜局面。RSI 超賣、價格跌破布林下軌暗示短期存在反彈需求，但 MACD 和均線系統的空頭排列顯示中期趨勢仍偏弱。建議短線交易者可關注反彈機會，但中長線投資者應等待更明確的趨勢反轉訊號。' if rsi.get('signal') == 'oversold' else '各項技術指標整體偏向中性，市場處於盤整階段，建議耐心等待方向明朗。'}

{derivatives_section}

## 🌐 市場結構分析

當前 **BTC Dominance (比特幣市佔率)** 為 **{btc_dom:.2f}%**。

{btc_dom_signal}

{'BTC 市佔率維持在正常區間，顯示市場結構健康。在這種情況下，比特幣和主流山寨幣通常會出現聯動走勢，投資者可根據個股基本面選擇標的。' if 45 <= btc_dom <= 60 else 'BTC 市佔率偏高顯示資金持續流向比特幣避險，山寨幣市場可能面臨持續的資金外流壓力。建議優先配置比特幣等主流幣種。' if btc_dom > 60 else 'BTC 市佔率下降顯示 Altcoin Season 的跡象，資金開始流向山寨幣。對於風險偏好較高的投資者，這可能是佈局優質山寨幣的機會。'}

從歷史數據看，當 BTC.D 處於 {btc_dom:.0f}% 附近時，{'比特幣通常處於相對強勢期' if btc_dom > 55 else '山寨幣往往有較好的表現機會' if btc_dom < 45 else '市場處於平衡狀態'}，投資者可依此調整資產配置策略。

## 🎭 情緒與新聞分析

### 市場情緒

{emoji} **恐慌貪婪指數：{fear_greed}（{fear_greed_zh}）**

當前市場情緒處於「{fear_greed_zh}」區間，{'顯示投資者普遍樂觀，市場可能已經累積一定獲利盤，需警惕短期調整風險。歷史上，當恐慌貪婪指數進入極度貪婪區域後，往往伴隨著市場的階段性高點。' if fear_greed > 60 else '反映投資者普遍謹慎甚至恐慌，但從逆向投資的角度，這可能是中長期佈局的較好時機。極度恐慌往往出現在市場底部區域，耐心持倉的投資者可能獲得較好的收益。' if fear_greed < 40 else '顯示市場情緒相對平衡，投資者保持觀望態度。'}

{news_section}

{news_impact_summary if news_impact_summary else ('綜合以上新聞，市場關注焦點集中在監管動態、機構動向以及宏觀經濟環境。這些因素將繼續影響短期價格波動。' if news else '今日市場新聞較為平淡，建議關注技術面訊號。')}

## 💡 操作建議

### 短期策略 (1-3 天)

{'基於當前的超賣訊號和極度恐慌情緒，短線交易者可考慮小倉位試探性建倉，但需嚴格設置止損。建議止損位設在近期低點下方 2-3%。' if fear_greed < 25 and rsi.get('signal') == 'oversold' else '市場處於超買狀態且情緒過熱，建議空倉觀望或適當減倉，待技術指標修復後再考慮進場。' if fear_greed > 75 and rsi.get('signal') == 'overbought' else '可小倉位試探性建倉' if fear_greed < 40 else '建議維持現有部位，密切關注市場變化'}

**關鍵價位：**
- 支撐位：${bb.get('lower', ma.get('sma_50', price_usd * 0.95)):,.0f} (布林下軌/MA50)
- 阻力位：${bb.get('upper', ma.get('sma_50', price_usd * 1.05)):,.0f} (布林上軌/MA50)

### 中長期展望 (1-3 月)

{f'技術面顯示長期處於熊市格局，價格在 MA200 ({ma.get("sma_200", 0):,.0f}) 之下運行。中長期投資者建議等待價格重新站穩 MA200 並確認趨勢反轉後再建倉。' if ma.get('trend') == 'bearish' else f'價格維持在 MA200 ({ma.get("sma_200", 0):,.0f}) 之上，長期牛市格局未改。適合定期定額投資策略，逢回調可逐步加碼。' if ma.get('trend') == 'bullish' else ''}

比特幣作為加密貨幣市場的龍頭，長期價值仍獲機構和市場認可。{'當前價格已深度回調，對長期投資者而言可能是較好的配置時機，但需做好承受短期波動的心理準備。' if change_24h < -10 else '維持中長期看好的態度，但需注意風險控制。'}

> ⚠️ **風險提示**：
> - 加密貨幣市場波動劇烈，7×24 小時交易可能出現極端行情
> - 本文僅供參考，不構成投資建議
> - 請根據自身風險承受能力謹慎決策，切勿盲目跟風
> - 建議設置止損，控制單筆交易風險在總資金的 2-5% 以內

---

*本文由 CoinPilot AI 自動生成 | 數據來源：CoinGecko、Binance、Alternative.me、Google News*  
*技術指標：RSI、MACD、MA、Bollinger Bands | 鏈上數據：BTC Dominance*
"""

        return article

    async def generate_comprehensive_report(
        self,
        multi_day_contexts: list,
        persona_decisions,
        portfolio_allocation,
    ) -> str:
        """生成模擬綜合投資報告"""
        from datetime import datetime
        
        today = datetime.now().strftime("%Y-%m-%d")
        days_count = len(multi_day_contexts)
        
        # 取最新一天的資料
        latest = multi_day_contexts[-1] if multi_day_contexts else {}
        price = latest.price if hasattr(latest, 'price') else {}
        price_usd = price.get("price_usd", 0)
        change_24h = price.get("change_24h", 0)
        
        # 建構市場時間線
        timeline_section = "## 📅 市場時間線\n\n"
        for ctx in multi_day_contexts:
            ctx_date = ctx.metadata.get("date", ctx.collected_at[:10]) if hasattr(ctx, 'metadata') else "Unknown"
            ctx_price = ctx.price.get("price_usd", 0) if hasattr(ctx, 'price') else 0
            ctx_change = ctx.price.get("change_24h", 0) if hasattr(ctx, 'price') else 0
            trend_emoji = "📈" if ctx_change > 0 else "📉" if ctx_change < 0 else "➡️"
            timeline_section += f"### {ctx_date} {trend_emoji}\n"
            timeline_section += f"- 收盤價: ${ctx_price:,.2f} ({ctx_change:+.2f}%)\n\n"
        
        # 決策表格
        decisions_table = persona_decisions.to_markdown_table()
        
        # 資金配置
        allocation_summary = portfolio_allocation.format_summary()
        
        article = f"""---
title: "比特幣綜合投資報告 - {today}"
description: "BTC ${price_usd:,.0f}，整合四位 AI 投資者觀點的深度分析報告"
date: {today}
categories:
  - 投資報告
tags:
  - Bitcoin
  - BTC
  - 投資建議
  - AI分析
image: ""
---

## 📊 報告摘要

本報告分析了過去 **{days_count} 天**的比特幣市場數據，並整合了四位 AI 投資者的決策建議。

| 項目 | 數值 |
|------|------|
| 當前價格 | ${price_usd:,.2f} |
| 24H 漲跌 | {change_24h:+.2f}% |
| 分析天數 | {days_count} 天 |
| 共識建議 | {persona_decisions.consensus_action} |

{timeline_section}

## 🎭 四位 AI 投資者決策對比

{decisions_table}

**投票結果**: 買入 {persona_decisions.buy_votes} | 賣出 {persona_decisions.sell_votes} | 持有 {persona_decisions.hold_votes}

## 💰 資金配置建議

{allocation_summary}

## 📈 技術面分析

根據過去 {days_count} 天的技術指標變化：

- **RSI 趨勢**: 市場短期超賣，存在反彈可能
- **MACD 訊號**: 動能指標顯示空頭趨勢仍在延續
- **移動平均線**: 價格位於 MA50 和 MA200 下方，中長期趨勢偏弱

## ⚠️ 風險提示

> **重要提醒**:
> - 加密貨幣市場波動劇烈，7×24 小時交易可能出現極端行情
> - 本報告由 AI 生成，僅供參考，不構成投資建議
> - 請根據自身風險承受能力謹慎決策
> - 建議使用分批建倉策略，控制單次交易風險

---

*本報告由 CoinPilot AI 自動生成 | 分析期間: 過去 {days_count} 天*  
*AI 投資者: Guardian (保守派) | Quant (量化派) | Strategist (宏觀派) | Degen (激進派)*
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
