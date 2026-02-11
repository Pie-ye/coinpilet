"""
Trade 交易執行模組

處理 AI 決策的解析與執行
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TradeAction(Enum):
    """交易動作"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeDecision:
    """AI 交易決策"""
    action: TradeAction
    amount_pct: float  # 操作比例 (0-100)
    reason: str  # 決策理由
    confidence: float = 0.0  # 信心度 (0-100)
    raw_response: str = ""  # 原始回應
    
    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "amount_pct": self.amount_pct,
            "reason": self.reason,
            "confidence": self.confidence,
        }


class TradeExecutor:
    """
    交易執行器
    
    負責：
    1. 解析 AI 回傳的 JSON 決策
    2. 驗證決策合理性
    3. 執行交易更新 Portfolio
    """
    
    def __init__(self):
        """初始化交易執行器"""
        self.log = logger
    
    def parse_decision(self, ai_response: str) -> TradeDecision:
        """
        解析 AI 回應為交易決策
        
        預期 JSON 格式:
        {
            "action": "BUY" | "SELL" | "HOLD",
            "amount_pct": 0-100,
            "reason": "決策理由",
            "confidence": 0-100
        }
        
        Args:
            ai_response: AI 模型的回應文字
            
        Returns:
            TradeDecision: 解析後的交易決策
        """
        try:
            # 嘗試從回應中提取 JSON
            json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', ai_response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
            else:
                # 嘗試直接解析整個回應
                data = json.loads(ai_response)
            
            # 解析 action
            action_str = data.get("action", "HOLD").upper()
            try:
                action = TradeAction(action_str)
            except ValueError:
                self.log.warning(f"無效的 action: {action_str}, 預設為 HOLD")
                action = TradeAction.HOLD
            
            # 解析 amount_pct
            amount_pct = float(data.get("amount_pct", 0))
            amount_pct = max(0, min(100, amount_pct))  # 限制在 0-100
            
            # 解析 reason
            reason = str(data.get("reason", "無說明"))
            
            # 解析 confidence
            confidence = float(data.get("confidence", 50))
            confidence = max(0, min(100, confidence))
            
            return TradeDecision(
                action=action,
                amount_pct=amount_pct,
                reason=reason,
                confidence=confidence,
                raw_response=ai_response,
            )
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.log.warning(f"JSON 解析失敗: {e}, 回應: {ai_response[:200]}...")
            
            # 嘗試從文字中推斷意圖
            response_lower = ai_response.lower()
            
            if "buy" in response_lower or "買入" in response_lower:
                action = TradeAction.BUY
                amount_pct = 10  # 保守預設
            elif "sell" in response_lower or "賣出" in response_lower:
                action = TradeAction.SELL
                amount_pct = 10
            else:
                action = TradeAction.HOLD
                amount_pct = 0
            
            return TradeDecision(
                action=action,
                amount_pct=amount_pct,
                reason=f"[解析失敗] {ai_response[:200]}",
                confidence=0,
                raw_response=ai_response,
            )
    
    def execute(
        self,
        decision: TradeDecision,
        portfolio,
        date: str,
        btc_price: float,
    ) -> bool:
        """
        執行交易決策
        
        Args:
            decision: 交易決策
            portfolio: Portfolio 物件
            date: 交易日期
            btc_price: BTC 價格
            
        Returns:
            bool: 執行是否成功
        """
        if decision.action == TradeAction.HOLD:
            portfolio.hold(date, btc_price, decision.reason)
            return True
        
        elif decision.action == TradeAction.BUY:
            # 計算買入金額 (可用 USD 餘額的百分比)
            usd_amount = portfolio.usd_balance * (decision.amount_pct / 100)
            
            if usd_amount < 10:  # 最小交易金額
                self.log.debug(f"買入金額過小 (${usd_amount:.2f}), 改為 HOLD")
                portfolio.hold(date, btc_price, f"[買入金額過小] {decision.reason}")
                return True
            
            return portfolio.buy(date, btc_price, usd_amount, decision.reason)
        
        elif decision.action == TradeAction.SELL:
            # 計算賣出數量 (持倉的百分比)
            btc_quantity = portfolio.btc_position.quantity * (decision.amount_pct / 100)
            
            if btc_quantity < 0.0001:  # 最小交易數量
                self.log.debug(f"賣出數量過小 ({btc_quantity:.8f}), 改為 HOLD")
                portfolio.hold(date, btc_price, f"[賣出數量過小] {decision.reason}")
                return True
            
            return portfolio.sell(date, btc_price, btc_quantity, decision.reason)
        
        return False
    
    def validate_decision(
        self,
        decision: TradeDecision,
        portfolio,
        btc_price: float,
    ) -> tuple[bool, str]:
        """
        驗證交易決策是否合理
        
        Args:
            decision: 交易決策
            portfolio: Portfolio 物件
            btc_price: BTC 價格
            
        Returns:
            tuple[bool, str]: (是否有效, 原因)
        """
        if decision.action == TradeAction.HOLD:
            return True, "HOLD 永遠有效"
        
        if decision.amount_pct <= 0:
            return False, "操作比例必須大於 0"
        
        if decision.amount_pct > 100:
            return False, "操作比例不能超過 100%"
        
        if decision.action == TradeAction.BUY:
            usd_amount = portfolio.usd_balance * (decision.amount_pct / 100)
            if usd_amount < 10:
                return False, f"買入金額不足 (${usd_amount:.2f})"
            if portfolio.usd_balance < 10:
                return False, "USD 餘額不足"
        
        elif decision.action == TradeAction.SELL:
            if portfolio.btc_position.quantity <= 0:
                return False, "無 BTC 持倉可賣"
            btc_quantity = portfolio.btc_position.quantity * (decision.amount_pct / 100)
            if btc_quantity < 0.0001:
                return False, f"賣出數量不足 ({btc_quantity:.8f} BTC)"
        
        return True, "決策有效"
