"""
Debate 辯論生成模組

每日交易結算後，讓四位 AI 投資者互相評論彼此的操作
產出具有娛樂性的對話腳本
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DebateEntry:
    """辯論對話條目"""
    speaker: str  # 發言者 ID
    speaker_name: str  # 發言者名稱
    emoji: str  # 發言者表情
    content: str  # 發言內容
    
    def to_markdown(self) -> str:
        return f"**{self.emoji} {self.speaker_name}**: {self.content}"


@dataclass
class DailyDebate:
    """每日辯論腳本"""
    date: str
    btc_price: float
    btc_change_pct: float
    market_summary: str
    entries: list[DebateEntry]
    
    def to_markdown(self) -> str:
        """轉換為 Markdown 格式"""
        lines = [
            f"# 📅 {self.date} 每日圓桌辯論",
            "",
            f"## 市場概況",
            f"- **BTC 價格**: ${self.btc_price:,.2f}",
            f"- **日漲跌幅**: {self.btc_change_pct:+.2f}%",
            f"- **市場摘要**: {self.market_summary}",
            "",
            "---",
            "",
            "## 辯論實錄",
            "",
        ]
        
        for entry in self.entries:
            lines.append(entry.to_markdown())
            lines.append("")
        
        lines.append("---")
        lines.append(f"*生成時間: {datetime.now().isoformat()}*")
        
        return "\n".join(lines)
    
    def save(self, output_dir: str = "output/debates"):
        """儲存辯論腳本為 Markdown 檔案"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.date}.md"
        filepath = output_path / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_markdown())
        
        logger.info(f"辯論腳本已儲存: {filepath}")
        return filepath


# 投資者角色設定
INVESTOR_PROFILES = {
    "guardian": {
        "name": "保守派",
        "emoji": "🛡️",
        "personality": "謹慎、保守、重視風險控制",
        "speaking_style": "語氣穩重，經常提醒風險，對激進操作表示擔憂",
    },
    "degen": {
        "name": "激進派",
        "emoji": "🚀",
        "personality": "大膽、追逐熱點、YOLO 心態",
        "speaking_style": "語氣興奮，喜歡用流行語，嘲笑保守派錯過機會",
    },
    "quant": {
        "name": "量化派",
        "emoji": "📊",
        "personality": "理性、數據驅動、情緒冷淡",
        "speaking_style": "語氣平淡，經常引用指標數據，不參與情緒化討論",
    },
    "strategist": {
        "name": "宏觀派",
        "emoji": "🌍",
        "personality": "長線思維、關注基本面和政策",
        "speaking_style": "語氣從容，經常提到宏觀經濟和政策影響",
    },
}


class DebateGenerator:
    """
    辯論生成器
    
    使用 AI 模型生成四位投資者之間的對話
    """
    
    def __init__(
        self,
        model: str = "gemini-3-flash",
        output_dir: str = "output/debates",
    ):
        """
        初始化辯論生成器
        
        Args:
            model: AI 模型名稱
            output_dir: 輸出目錄
        """
        self.model = model
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = None
    
    async def start(self, github_token: Optional[str] = None):
        """啟動辯論生成器 (初始化 Copilot SDK)"""
        try:
            from copilot import CopilotClient
            
            # 按照官方文檔建立客戶端（不需要配置參數）
            self.client = CopilotClient()
            
            logger.info("DebateGenerator 已啟動")
            
        except ImportError:
            logger.error("找不到 github-copilot-sdk，請執行: pip install github-copilot-sdk")
            raise
        except Exception as e:
            logger.error(f"Copilot SDK 啟動失敗: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """停止辯論生成器"""
        if self.client:
            await self.client.stop()
            logger.info("DebateGenerator 已停止")
    
    def _build_debate_prompt(
        self,
        date: str,
        btc_price: float,
        btc_change_pct: float,
        trades_summary: dict[str, dict],
        market_context: str = "",
    ) -> str:
        """
        建構辯論提示詞
        
        Args:
            date: 日期
            btc_price: BTC 價格
            btc_change_pct: 日漲跌幅
            trades_summary: 各投資者的交易摘要
            market_context: 市場背景資訊
        """
        # 建構各投資者的操作摘要
        trades_text = []
        for investor_id, trade_info in trades_summary.items():
            profile = INVESTOR_PROFILES.get(investor_id, {})
            name = profile.get("name", investor_id)
            emoji = profile.get("emoji", "")
            
            action = trade_info.get("action", "HOLD")
            amount_pct = trade_info.get("amount_pct", 0)
            reason = trade_info.get("reason", "無說明")
            portfolio_value = trade_info.get("portfolio_value", 0)
            return_pct = trade_info.get("return_pct", 0)
            
            trades_text.append(
                f"- {emoji} {name}:\n"
                f"  - 操作: {action}"
                f"{f' ({amount_pct}%)' if amount_pct > 0 else ''}\n"
                f"  - 理由: {reason}\n"
                f"  - 當前淨值: ${portfolio_value:,.0f} ({return_pct:+.1f}%)"
            )
        
        prompt = f"""你是一個對話腳本生成器，負責生成四位 AI 投資者之間的每日辯論對話。

## 當前情境

日期: {date}
BTC 價格: ${btc_price:,.2f}
日漲跌幅: {btc_change_pct:+.2f}%
{f'市場背景: {market_context}' if market_context else ''}

## 今日各投資者操作

{chr(10).join(trades_text)}

## 投資者人設

1. 🛡️ 保守派 (Guardian): 極度厭惡風險，只在市場極度恐慌時才考慮進場
2. 🚀 激進派 (Degen): 追逐動能與熱點，YOLO 心態，喜歡嘲笑保守派
3. 📊 量化派 (Quant): 只相信數學和指標，語氣冷淡，不參與情緒爭論
4. 🌍 宏觀派 (Strategist): 關注基本面和政策，長線思維

## 任務

請生成一段約 4-6 輪的對話，讓四位投資者根據今日的市場表現和各自的操作互相評論。

要求：
1. 對話要有衝突感和娛樂性
2. 各角色要符合人設，說話風格要鮮明
3. 可以互相調侃、質疑對方的決策
4. 結尾可以有一點共識或懸念

請以 JSON 格式回傳，格式如下：
```json
{{
  "market_summary": "一句話總結今日市場",
  "entries": [
    {{"speaker": "guardian", "content": "對話內容"}},
    {{"speaker": "degen", "content": "對話內容"}},
    ...
  ]
}}
```
"""
        return prompt
    
    async def generate(
        self,
        date: str,
        btc_price: float,
        btc_change_pct: float,
        trades_summary: dict[str, dict],
        market_context: str = "",
    ) -> DailyDebate:
        """
        生成每日辯論
        
        Args:
            date: 日期
            btc_price: BTC 價格
            btc_change_pct: 日漲跌幅
            trades_summary: 各投資者的交易摘要
            market_context: 市場背景資訊
            
        Returns:
            DailyDebate: 辯論腳本
        """
        if not self.client:
            raise RuntimeError("DebateGenerator 尚未啟動，請先調用 start()")
        
        prompt = self._build_debate_prompt(
            date, btc_price, btc_change_pct, trades_summary, market_context
        )
        
        try:
            # 組合 system prompt 和 user prompt
            system_prompt = "你是一個專業的對話腳本生成器，擅長創作有趣且符合角色設定的對話。請只回傳 JSON 格式。"
            full_prompt = f"{system_prompt}\n\n{prompt}"
            
            session = await self.client.create_session({
                "model": self.model,
            })
            
            response = await session.send_and_wait(
                {"prompt": full_prompt},
                timeout=90.0  # 90 秒超時
            )
            response_text = response.data.content
            
            # 解析回應
            entries = self._parse_debate_response(response_text)
            
            # 提取市場摘要
            market_summary = self._extract_market_summary(response_text)
            
            debate = DailyDebate(
                date=date,
                btc_price=btc_price,
                btc_change_pct=btc_change_pct,
                market_summary=market_summary,
                entries=entries,
            )
            
            logger.info(f"生成辯論完成: {date}, {len(entries)} 輪對話")
            return debate
            
        except Exception as e:
            logger.error(f"生成辯論失敗: {e}")
            # 返回預設辯論
            return self._create_fallback_debate(
                date, btc_price, btc_change_pct, trades_summary
            )
    
    def _parse_debate_response(self, response: str) -> list[DebateEntry]:
        """解析 AI 回應為辯論條目"""
        import re
        
        entries = []
        
        try:
            # 提取 JSON
            json_match = re.search(r'\{.*"entries".*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                for entry in data.get("entries", []):
                    speaker = entry.get("speaker", "unknown")
                    content = entry.get("content", "")
                    
                    profile = INVESTOR_PROFILES.get(speaker, {})
                    
                    entries.append(DebateEntry(
                        speaker=speaker,
                        speaker_name=profile.get("name", speaker),
                        emoji=profile.get("emoji", "❓"),
                        content=content,
                    ))
        
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"解析辯論回應失敗: {e}")
        
        return entries
    
    def _extract_market_summary(self, response: str) -> str:
        """從回應中提取市場摘要"""
        import re
        
        try:
            json_match = re.search(r'\{.*"market_summary".*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("market_summary", "市場波動中")
        except:
            pass
        
        return "市場波動中"
    
    def _create_fallback_debate(
        self,
        date: str,
        btc_price: float,
        btc_change_pct: float,
        trades_summary: dict[str, dict],
    ) -> DailyDebate:
        """創建預設辯論 (當 AI 生成失敗時)"""
        
        # 根據漲跌幅生成預設對話
        if btc_change_pct > 5:
            entries = [
                DebateEntry("degen", "激進派", "🚀", "看到沒！又漲了！早說要 all-in 了！"),
                DebateEntry("guardian", "保守派", "🛡️", "漲越多越要小心，別忘了風險控制。"),
                DebateEntry("quant", "量化派", "📊", "RSI 已經超買，技術面建議觀望。"),
                DebateEntry("strategist", "宏觀派", "🌍", "短期波動不影響長期趨勢，繼續持有。"),
            ]
            market_summary = "BTC 大漲，市場情緒高漲"
        elif btc_change_pct < -5:
            entries = [
                DebateEntry("guardian", "保守派", "🛡️", "還好我早就說要保守，你們看看..."),
                DebateEntry("degen", "激進派", "🚀", "這只是回調，正是加倉的好機會！"),
                DebateEntry("quant", "量化派", "📊", "跌破支撐位，等待確認底部。"),
                DebateEntry("strategist", "宏觀派", "🌍", "基本面沒變，恐慌時正是佈局時。"),
            ]
            market_summary = "BTC 大跌，市場恐慌"
        else:
            entries = [
                DebateEntry("quant", "量化派", "📊", "橫盤整理中，等待突破方向。"),
                DebateEntry("degen", "激進派", "🚀", "無聊，什麼時候才會有行情..."),
                DebateEntry("guardian", "保守派", "🛡️", "穩定就是好事，耐心等待。"),
                DebateEntry("strategist", "宏觀派", "🌍", "關注即將公布的經濟數據。"),
            ]
            market_summary = "BTC 橫盤整理"
        
        return DailyDebate(
            date=date,
            btc_price=btc_price,
            btc_change_pct=btc_change_pct,
            market_summary=market_summary,
            entries=entries,
        )
    
    def generate_sync(
        self,
        date: str,
        btc_price: float,
        btc_change_pct: float,
        trades_summary: dict[str, dict],
        market_context: str = "",
    ) -> DailyDebate:
        """
        同步版本的辯論生成 (使用預設模板，不調用 AI)
        
        適用於測試或當 AI 不可用時
        """
        return self._create_fallback_debate(
            date, btc_price, btc_change_pct, trades_summary
        )
