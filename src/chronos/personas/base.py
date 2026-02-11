"""
投資人角色基礎類別

定義所有投資人角色的共同介面與行為
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PersonaConfig:
    """角色配置"""
    
    # 基本資訊
    id: str  # 角色 ID
    name: str  # 角色名稱
    name_zh: str  # 中文名稱
    emoji: str  # 表情符號
    
    # 投資風格
    style: str  # 投資風格描述
    philosophy: str  # 投資哲學
    risk_tolerance: str  # 風險承受度 (low, medium, high)
    
    # 資訊偏好
    use_news: bool = True  # 是否參考新聞
    use_technical: bool = True  # 是否參考技術指標
    use_fear_greed: bool = True  # 是否參考恐懼貪婪指數
    
    # 決策參數
    max_position_pct: float = 100.0  # 最大持倉比例
    min_trade_pct: float = 5.0  # 最小交易比例


@dataclass
class MarketContext:
    """市場上下文資訊"""
    
    # 基本資訊
    current_date: str  # 模擬日期 (YYYY-MM-DD)
    btc_price: float  # 當日 BTC 價格
    btc_change_pct: float  # 當日漲跌幅
    
    # 技術指標 (可選)
    rsi: Optional[float] = None
    rsi_signal: Optional[str] = None
    macd_signal: Optional[str] = None  # bullish, bearish, neutral
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    bb_position: Optional[str] = None  # above_upper, below_lower, within
    overall_technical: Optional[str] = None  # bullish, bearish, neutral
    
    # 市場情緒 (可選)
    fear_greed_value: Optional[int] = None
    fear_greed_label: Optional[str] = None
    
    # 新聞 (可選)
    news_headlines: list[str] = field(default_factory=list)
    news_summaries: list[str] = field(default_factory=list)
    
    # 投資組合狀態
    portfolio_value: float = 0.0
    usd_balance: float = 0.0
    btc_quantity: float = 0.0
    return_pct: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "current_date": self.current_date,
            "btc_price": self.btc_price,
            "btc_change_pct": self.btc_change_pct,
            "rsi": self.rsi,
            "rsi_signal": self.rsi_signal,
            "macd_signal": self.macd_signal,
            "ma_50": self.ma_50,
            "ma_200": self.ma_200,
            "bb_position": self.bb_position,
            "overall_technical": self.overall_technical,
            "fear_greed_value": self.fear_greed_value,
            "fear_greed_label": self.fear_greed_label,
            "news_headlines": self.news_headlines,
            "portfolio_value": self.portfolio_value,
            "usd_balance": self.usd_balance,
            "btc_quantity": self.btc_quantity,
            "return_pct": self.return_pct,
        }


class InvestorPersona(ABC):
    """
    投資人角色基礎類別
    
    每位投資人角色必須實作：
    - get_config(): 返回角色配置
    - build_system_prompt(): 建構 System Prompt
    - build_decision_prompt(): 建構決策請求 Prompt
    """
    
    def __init__(self, model: str = "gemini-3-flash"):
        """
        初始化投資人角色
        
        Args:
            model: AI 模型名稱
        """
        self.model = model
        self.config = self.get_config()
        self.client = None
        
        logger.info(f"初始化投資人: {self.config.emoji} {self.config.name_zh}")
    
    @abstractmethod
    def get_config(self) -> PersonaConfig:
        """返回角色配置"""
        pass
    
    @abstractmethod
    def build_system_prompt(self, current_date: str) -> str:
        """
        建構 System Prompt
        
        Args:
            current_date: 模擬日期
            
        Returns:
            str: System Prompt
        """
        pass
    
    def build_decision_prompt(self, context: MarketContext) -> str:
        """
        建構決策請求 Prompt
        
        根據角色的資訊偏好，選擇性地包含不同類型的資訊
        
        Args:
            context: 市場上下文
            
        Returns:
            str: 決策請求 Prompt
        """
        sections = []
        
        # 基本市場資訊
        sections.append(f"""## 市場資訊

日期: {context.current_date}
BTC 價格: ${context.btc_price:,.2f}
今日漲跌: {context.btc_change_pct:+.2f}%""")
        
        # 技術指標 (如果角色需要)
        if self.config.use_technical and context.rsi is not None:
            ma50_str = f"${context.ma_50:,.2f}" if context.ma_50 else "N/A"
            ma200_str = f"${context.ma_200:,.2f}" if context.ma_200 else "N/A"
            tech_section = f"""
## 技術指標

- RSI(14): {context.rsi:.1f} ({context.rsi_signal or 'N/A'})
- MACD 信號: {context.macd_signal or 'N/A'}
- MA50: {ma50_str}
- MA200: {ma200_str}
- 布林通道位置: {context.bb_position or 'N/A'}
- 綜合技術信號: {context.overall_technical or 'N/A'}"""
            sections.append(tech_section)
        
        # 恐懼貪婪指數 (如果角色需要)
        if self.config.use_fear_greed and context.fear_greed_value is not None:
            fg_section = f"""
## 市場情緒

- Fear & Greed Index: {context.fear_greed_value} ({context.fear_greed_label or 'N/A'})"""
            sections.append(fg_section)
        
        # 新聞 (如果角色需要)
        if self.config.use_news and context.news_headlines:
            news_list = "\n".join([f"- {h}" for h in context.news_headlines[:5]])
            news_section = f"""
## 今日新聞

{news_list}"""
            sections.append(news_section)
        
        # 投資組合狀態
        sections.append(f"""
## 你的投資組合

- 總資產: ${context.portfolio_value:,.2f}
- USD 餘額: ${context.usd_balance:,.2f}
- BTC 持倉: {context.btc_quantity:.6f} BTC
- 累計報酬: {context.return_pct:+.2f}%""")
        
        # 決策請求
        sections.append("""
## 決策請求

根據以上資訊，請做出今日的投資決策。

請以 JSON 格式回覆：
```json
{
    "action": "BUY" | "SELL" | "HOLD",
    "amount_pct": 0-100,
    "reason": "你的決策理由（50字以內）",
    "confidence": 0-100
}
```

說明：
- action: 操作類型
- amount_pct: 操作比例（BUY 時為可用 USD 的百分比，SELL 時為持有 BTC 的百分比）
- reason: 簡短的決策理由
- confidence: 對此決策的信心度""")
        
        return "\n".join(sections)

    def build_decision_prompt_compact(self, context: MarketContext) -> str:
        """
        建構簡化版決策提示詞（縮短內容以避免超時）
        """
        ma50_str = f"${context.ma_50:,.2f}" if context.ma_50 is not None else "N/A"
        ma200_str = f"${context.ma_200:,.2f}" if context.ma_200 is not None else "N/A"
        rsi_str = f"{context.rsi:.1f}" if context.rsi is not None else "N/A"

        prompt = f"""請根據以下重點資訊做出今日投資決策：

日期: {context.current_date}
BTC 價格: ${context.btc_price:,.2f}
今日漲跌: {context.btc_change_pct:+.2f}%

技術指標:
- RSI(14): {rsi_str} ({context.rsi_signal or 'N/A'})"""

        if context.macd_signal or context.ma_50 or context.ma_200:
            prompt += f"""
- MACD 信號: {context.macd_signal or 'N/A'}
- MA50: {ma50_str}
- MA200: {ma200_str}
- 綜合技術信號: {context.overall_technical or 'N/A'}"""

        if self.config.use_fear_greed and context.fear_greed_value is not None:
            prompt += f"""

市場情緒:
- Fear & Greed Index: {context.fear_greed_value} ({context.fear_greed_label or 'N/A'})"""

        prompt += f"""

投資組合:
- 總資產: ${context.portfolio_value:,.2f}
- USD 餘額: ${context.usd_balance:,.2f}
- BTC 持倉: {context.btc_quantity:.6f} BTC
- 累計報酬: {context.return_pct:+.2f}%

請以 JSON 格式回覆：
```json
{{
    "action": "BUY" | "SELL" | "HOLD",
    "amount_pct": 0-100,
    "reason": "你的決策理由（50字以內）",
    "confidence": 0-100
}}
```
"""

        return prompt
    
    async def start(self, github_token: Optional[str] = None):
        """啟動角色 (初始化 Copilot SDK)"""
        try:
            from copilot import CopilotClient
            
            # 按照官方文檔建立客戶端（不需要配置參數）
            self.client = CopilotClient()
            
            logger.info(f"{self.config.emoji} {self.config.name_zh} 已啟動")
            
        except ImportError:
            logger.error("找不到 github-copilot-sdk，請執行: pip install github-copilot-sdk")
            raise
        except Exception as e:
            logger.error(f"Copilot SDK 啟動失敗: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """停止角色"""
        if self.client:
            await self.client.stop()
            logger.info(f"{self.config.emoji} {self.config.name_zh} 已停止")
    
    async def make_decision(self, context: MarketContext) -> str:
        """
        做出投資決策
        
        Args:
            context: 市場上下文
            
        Returns:
            str: AI 回應 (JSON 格式)
        """
        if not self.client:
            # 沒有 client 時，fallback 到規則決策
            logger.warning(f"{self.config.name_zh} 未啟動 Copilot SDK，使用規則決策")
            return self.make_decision_sync(context)
        
        system_prompt = self.build_system_prompt(context.current_date)
        user_prompt = self.build_decision_prompt(context)
        
        # 組合 system prompt 和 user prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            session = await self.client.create_session({
                "model": self.model,
            })
            
            response = await session.send_and_wait(
                {"prompt": full_prompt},
                timeout=300.0  # 5 分鐘超時（與 main.py 保持一致）
            )
            
            # 提取回應內容
            logger.debug(f"{self.config.name_zh} AI 決策完成")
            return response.data.content
            
        except asyncio.TimeoutError:
            logger.warning(
                f"{self.config.name_zh} AI 決策超時 (>300s)，"
                f"降級為規則決策 [日期: {context.current_date}]"
            )
            return self.make_decision_sync(context)
        except Exception as e:
            logger.warning(
                f"{self.config.name_zh} AI 決策失敗: {type(e).__name__}: {e}, "
                f"降級為規則決策 [日期: {context.current_date}]"
            )
            return self.make_decision_sync(context)
    
    def make_decision_sync(self, context: MarketContext) -> str:
        """
        同步版本的決策 (使用簡單規則，不調用 AI)
        
        用於測試或當 AI 不可用時
        """
        # 子類別可以覆寫此方法提供更具體的規則
        return '{"action": "HOLD", "amount_pct": 0, "reason": "等待更好的機會", "confidence": 50}'
