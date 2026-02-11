"""
投資顧問 Agent - 整合四大投資人角色提供綜合投資建議

整合 Guardian、Quant、Strategist、Degen 四位 AI 投資者的決策，
計算 $1M 資金的最佳配置建議。

使用方式:
    advisor = InvestmentAdvisor()
    context = advisor.build_market_context(daily_context)
    decisions = advisor.get_multi_strategy_decisions(context)
    allocation = advisor.calculate_portfolio_allocation(decisions, btc_price=66500)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

from src.chronos.personas import Guardian, Degen, Quant, Strategist
from src.chronos.personas.base import MarketContext, PersonaConfig
from src.collector.collector import DailyContext

logger = structlog.get_logger(__name__)


@dataclass
class PersonaDecision:
    """單一投資人角色的決策"""
    
    persona_id: str  # guardian, quant, strategist, degen
    persona_name: str  # 中文名稱
    emoji: str
    action: str  # BUY, SELL, HOLD
    amount_pct: float  # 建議操作比例
    reason: str  # 決策理由
    confidence: int  # 信心度 0-100
    risk_tolerance: str  # low, medium, high
    
    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "emoji": self.emoji,
            "action": self.action,
            "amount_pct": self.amount_pct,
            "reason": self.reason,
            "confidence": self.confidence,
            "risk_tolerance": self.risk_tolerance,
        }


@dataclass
class MultiStrategyDecisions:
    """四位投資者的綜合決策"""
    
    decisions: dict[str, PersonaDecision] = field(default_factory=dict)
    consensus_action: str = "HOLD"  # 共識行動
    consensus_confidence: int = 50  # 共識信心度
    buy_votes: int = 0
    sell_votes: int = 0
    hold_votes: int = 0
    
    def to_dict(self) -> dict:
        return {
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "consensus_action": self.consensus_action,
            "consensus_confidence": self.consensus_confidence,
            "buy_votes": self.buy_votes,
            "sell_votes": self.sell_votes,
            "hold_votes": self.hold_votes,
        }
    
    def to_markdown_table(self) -> str:
        """生成 Markdown 格式的決策對比表"""
        lines = [
            "| 投資者 | 決策 | 比例 | 信心度 | 理由 |",
            "|--------|------|------|--------|------|",
        ]
        for persona_id, decision in self.decisions.items():
            action_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(decision.action, "⚪")
            lines.append(
                f"| {decision.emoji} {decision.persona_name} | "
                f"{action_emoji} {decision.action} | "
                f"{decision.amount_pct}% | "
                f"{decision.confidence}% | "
                f"{decision.reason} |"
            )
        
        # 添加共識行
        lines.append("|--------|------|------|--------|------|")
        consensus_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(self.consensus_action, "⚪")
        lines.append(
            f"| **📊 共識** | "
            f"**{consensus_emoji} {self.consensus_action}** | "
            f"**-** | "
            f"**{self.consensus_confidence}%** | "
            f"**買:{self.buy_votes} 賣:{self.sell_votes} 持有:{self.hold_votes}** |"
        )
        
        return "\n".join(lines)


@dataclass
class PortfolioAllocation:
    """資金配置建議"""
    
    total_capital: float  # 總資金 (USD)
    btc_price: float  # 當前 BTC 價格
    recommended_action: str  # BUY, SELL, HOLD
    
    # 配置金額
    buy_amount_usd: float = 0.0  # 建議買入金額
    hold_amount_usd: float = 0.0  # 建議持有金額
    sell_amount_usd: float = 0.0  # 建議賣出金額 (如果有持倉)
    
    # BTC 數量
    btc_to_buy: float = 0.0
    btc_to_hold: float = 0.0
    btc_to_sell: float = 0.0
    
    # 加權比例
    weighted_buy_pct: float = 0.0
    weighted_sell_pct: float = 0.0
    
    # 風險評估
    risk_level: str = "medium"  # low, medium, high
    allocation_rationale: str = ""
    
    def to_dict(self) -> dict:
        return {
            "total_capital": self.total_capital,
            "btc_price": self.btc_price,
            "recommended_action": self.recommended_action,
            "buy_amount_usd": self.buy_amount_usd,
            "hold_amount_usd": self.hold_amount_usd,
            "sell_amount_usd": self.sell_amount_usd,
            "btc_to_buy": self.btc_to_buy,
            "btc_to_hold": self.btc_to_hold,
            "btc_to_sell": self.btc_to_sell,
            "weighted_buy_pct": self.weighted_buy_pct,
            "weighted_sell_pct": self.weighted_sell_pct,
            "risk_level": self.risk_level,
            "allocation_rationale": self.allocation_rationale,
        }
    
    def format_summary(self) -> str:
        """格式化配置摘要"""
        action_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(self.recommended_action, "⚪")
        
        lines = [
            f"### {action_emoji} 建議操作：{self.recommended_action}",
            "",
            f"**總資金**: ${self.total_capital:,.0f}",
            f"**當前 BTC 價格**: ${self.btc_price:,.2f}",
            "",
        ]
        
        if self.recommended_action == "BUY":
            lines.extend([
                f"**建議買入**:",
                f"- 金額: ${self.buy_amount_usd:,.0f} ({self.weighted_buy_pct:.1f}%)",
                f"- 數量: {self.btc_to_buy:.4f} BTC",
                f"- 保留現金: ${self.hold_amount_usd:,.0f}",
            ])
        elif self.recommended_action == "SELL":
            lines.extend([
                f"**建議賣出**:",
                f"- 金額: ${self.sell_amount_usd:,.0f} ({self.weighted_sell_pct:.1f}%)",
                f"- 數量: {self.btc_to_sell:.4f} BTC",
            ])
        else:
            lines.extend([
                f"**建議持有**:",
                f"- 維持現有配置",
                f"- 等待更明確的市場訊號",
            ])
        
        lines.extend([
            "",
            f"**風險等級**: {self.risk_level.upper()}",
            f"**配置理由**: {self.allocation_rationale}",
        ])
        
        return "\n".join(lines)


class InvestmentAdvisor:
    """
    投資顧問 - 整合四大投資人角色提供綜合建議
    
    使用方式:
        advisor = InvestmentAdvisor()
        context = advisor.build_market_context(daily_context)
        decisions = advisor.get_multi_strategy_decisions(context)
        allocation = advisor.calculate_portfolio_allocation(
            decisions, 
            total_capital=1000000,
            btc_price=66500
        )
    """
    
    def __init__(self):
        """初始化四大投資人角色"""
        self.personas = {
            "guardian": Guardian(),
            "quant": Quant(),
            "strategist": Strategist(),
            "degen": Degen(),
        }
        logger.info("投資顧問初始化完成", personas=list(self.personas.keys()))
    
    def build_market_context(
        self,
        daily_context: DailyContext,
        usd_balance: float = 1000000.0,
        btc_quantity: float = 0.0,
        portfolio_value: Optional[float] = None,
    ) -> MarketContext:
        """
        從 DailyContext 建立 MarketContext
        
        Args:
            daily_context: 採集器的每日資料
            usd_balance: USD 餘額
            btc_quantity: BTC 持有量
            portfolio_value: 投資組合總值
        """
        price_data = daily_context.price or {}
        sentiment_data = daily_context.sentiment or {}
        technical_data = daily_context.technical or {}
        news_data = daily_context.news or []
        
        # 計算投資組合價值
        btc_price = price_data.get("price_usd", 0) or 0
        if portfolio_value is None:
            portfolio_value = usd_balance + (btc_quantity * btc_price)
        
        # 提取技術指標（防禦性檢查）
        rsi_data = technical_data.get("rsi") or {}
        macd_data = technical_data.get("macd") or {}
        ma_data = technical_data.get("ma") or technical_data.get("moving_averages") or {}
        bb_data = technical_data.get("bollinger") or technical_data.get("bollinger_bands") or {}
        
        rsi = rsi_data.get("value")
        rsi_signal = rsi_data.get("signal")
        macd_signal = macd_data.get("signal")
        ma_50 = ma_data.get("ma50") or ma_data.get("ma_50")
        ma_200 = ma_data.get("ma200") or ma_data.get("ma_200")
        bb_position = bb_data.get("position")
        overall_technical = technical_data.get("overall_signal")
        
        # 提取新聞標題
        news_headlines = [item.get("title", "") for item in news_data[:5] if item]
        news_summaries = [(item.get("summary") or "")[:200] for item in news_data[:3] if item]
        
        return MarketContext(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            btc_price=btc_price,
            btc_change_pct=price_data.get("change_24h", 0) or 0,
            rsi=rsi,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            ma_50=ma_50,
            ma_200=ma_200,
            bb_position=bb_position,
            overall_technical=overall_technical,
            fear_greed_value=sentiment_data.get("value"),
            fear_greed_label=sentiment_data.get("label"),
            news_headlines=news_headlines,
            news_summaries=news_summaries,
            portfolio_value=portfolio_value,
            usd_balance=usd_balance,
            btc_quantity=btc_quantity,
            return_pct=0.0,  # 初始投資無回報率
        )
    
    def get_multi_strategy_decisions(
        self, 
        context: MarketContext
    ) -> MultiStrategyDecisions:
        """
        獲取四位投資者的決策
        
        Args:
            context: 市場上下文
            
        Returns:
            MultiStrategyDecisions: 包含四位投資者決策的結構
        """
        result = MultiStrategyDecisions()
        
        for persona_id, persona in self.personas.items():
            try:
                config = persona.get_config()
                decision_json = persona.make_decision_sync(context)
                decision_data = json.loads(decision_json)
                
                decision = PersonaDecision(
                    persona_id=persona_id,
                    persona_name=config.name_zh,
                    emoji=config.emoji,
                    action=decision_data.get("action", "HOLD"),
                    amount_pct=decision_data.get("amount_pct", 0),
                    reason=decision_data.get("reason", "無理由"),
                    confidence=decision_data.get("confidence", 50),
                    risk_tolerance=config.risk_tolerance,
                )
                
                result.decisions[persona_id] = decision
                
                # 統計投票
                if decision.action == "BUY":
                    result.buy_votes += 1
                elif decision.action == "SELL":
                    result.sell_votes += 1
                else:
                    result.hold_votes += 1
                    
                logger.debug(
                    f"{config.emoji} {config.name_zh} 決策",
                    action=decision.action,
                    amount_pct=decision.amount_pct,
                    confidence=decision.confidence,
                )
                
            except Exception as e:
                logger.error(f"獲取 {persona_id} 決策失敗", error=str(e))
                # 失敗時使用預設 HOLD 決策
                result.decisions[persona_id] = PersonaDecision(
                    persona_id=persona_id,
                    persona_name=persona_id,
                    emoji="❓",
                    action="HOLD",
                    amount_pct=0,
                    reason=f"決策失敗: {str(e)}",
                    confidence=0,
                    risk_tolerance="medium",
                )
                result.hold_votes += 1
        
        # 計算共識
        result.consensus_action, result.consensus_confidence = self._calculate_consensus(result)
        
        logger.info(
            "四位投資者決策完成",
            consensus=result.consensus_action,
            confidence=result.consensus_confidence,
            votes=f"買:{result.buy_votes} 賣:{result.sell_votes} 持有:{result.hold_votes}",
        )
        
        return result
    
    def _calculate_consensus(
        self, 
        decisions: MultiStrategyDecisions
    ) -> tuple[str, int]:
        """
        計算共識決策
        
        使用加權投票：信心度作為權重
        """
        # 計算各行動的加權分數
        buy_score = 0.0
        sell_score = 0.0
        hold_score = 0.0
        
        for decision in decisions.decisions.values():
            weight = decision.confidence / 100.0
            if decision.action == "BUY":
                buy_score += weight
            elif decision.action == "SELL":
                sell_score += weight
            else:
                hold_score += weight
        
        # 決定共識行動
        max_score = max(buy_score, sell_score, hold_score)
        
        # 如果買賣分歧太大，傾向 HOLD
        if abs(buy_score - sell_score) < 0.5 and buy_score > 0 and sell_score > 0:
            consensus_action = "HOLD"
            consensus_confidence = 40  # 低信心度表示分歧
        elif buy_score == max_score:
            consensus_action = "BUY"
            consensus_confidence = int(buy_score / len(decisions.decisions) * 100)
        elif sell_score == max_score:
            consensus_action = "SELL"
            consensus_confidence = int(sell_score / len(decisions.decisions) * 100)
        else:
            consensus_action = "HOLD"
            consensus_confidence = int(hold_score / len(decisions.decisions) * 100)
        
        return consensus_action, min(consensus_confidence, 95)
    
    def calculate_portfolio_allocation(
        self,
        decisions: MultiStrategyDecisions,
        total_capital: float = 1000000.0,
        btc_price: float = 66500.0,
        current_btc_holding: float = 0.0,
    ) -> PortfolioAllocation:
        """
        計算資金配置建議
        
        Args:
            decisions: 四位投資者決策
            total_capital: 總資金 (USD)
            btc_price: 當前 BTC 價格
            current_btc_holding: 當前 BTC 持有量
            
        Returns:
            PortfolioAllocation: 資金配置建議
        """
        allocation = PortfolioAllocation(
            total_capital=total_capital,
            btc_price=btc_price,
            recommended_action=decisions.consensus_action,
        )
        
        # 計算加權平均操作比例
        total_buy_weight = 0.0
        total_sell_weight = 0.0
        buy_pct_weighted = 0.0
        sell_pct_weighted = 0.0
        
        for decision in decisions.decisions.values():
            weight = decision.confidence / 100.0
            if decision.action == "BUY":
                buy_pct_weighted += decision.amount_pct * weight
                total_buy_weight += weight
            elif decision.action == "SELL":
                sell_pct_weighted += decision.amount_pct * weight
                total_sell_weight += weight
        
        # 計算最終配置比例
        if total_buy_weight > 0:
            allocation.weighted_buy_pct = buy_pct_weighted / total_buy_weight
        if total_sell_weight > 0:
            allocation.weighted_sell_pct = sell_pct_weighted / total_sell_weight
        
        # 根據共識決定配置
        if decisions.consensus_action == "BUY":
            # 使用加權買入比例，但限制最大 50% 以控制風險
            buy_pct = min(allocation.weighted_buy_pct, 50.0)
            allocation.buy_amount_usd = total_capital * (buy_pct / 100.0)
            allocation.hold_amount_usd = total_capital - allocation.buy_amount_usd
            allocation.btc_to_buy = allocation.buy_amount_usd / btc_price
            allocation.risk_level = self._assess_risk_level(decisions)
            allocation.allocation_rationale = (
                f"基於 {decisions.buy_votes} 位投資者建議買入，"
                f"共識信心度 {decisions.consensus_confidence}%，"
                f"建議分批建倉"
            )
            
        elif decisions.consensus_action == "SELL":
            # 使用加權賣出比例
            sell_pct = min(allocation.weighted_sell_pct, 50.0)
            if current_btc_holding > 0:
                allocation.btc_to_sell = current_btc_holding * (sell_pct / 100.0)
                allocation.sell_amount_usd = allocation.btc_to_sell * btc_price
            allocation.risk_level = self._assess_risk_level(decisions)
            allocation.allocation_rationale = (
                f"基於 {decisions.sell_votes} 位投資者建議賣出，"
                f"共識信心度 {decisions.consensus_confidence}%，"
                f"建議分批減倉"
            )
            
        else:  # HOLD
            allocation.hold_amount_usd = total_capital
            allocation.btc_to_hold = current_btc_holding
            allocation.risk_level = "low"
            allocation.allocation_rationale = (
                f"投資者意見分歧（買:{decisions.buy_votes} 賣:{decisions.sell_votes} 持有:{decisions.hold_votes}），"
                f"建議維持觀望並等待更明確訊號"
            )
        
        logger.info(
            "資金配置計算完成",
            action=allocation.recommended_action,
            buy_usd=f"${allocation.buy_amount_usd:,.0f}",
            btc_qty=f"{allocation.btc_to_buy:.4f} BTC",
            risk=allocation.risk_level,
        )
        
        return allocation
    
    def _assess_risk_level(self, decisions: MultiStrategyDecisions) -> str:
        """評估風險等級"""
        # 檢查保守派（Guardian）的決策
        guardian = decisions.decisions.get("guardian")
        if guardian and guardian.action == "SELL":
            return "high"  # 保守派也要賣，風險高
        if guardian and guardian.action == "HOLD" and decisions.consensus_action == "BUY":
            return "medium"  # 保守派觀望但共識是買，中等風險
        if guardian and guardian.action == "BUY":
            return "low"  # 連保守派都買，風險較低
        return "medium"


# 便捷函數
def get_investment_advice(
    daily_context: DailyContext,
    total_capital: float = 1000000.0,
) -> tuple[MultiStrategyDecisions, PortfolioAllocation]:
    """
    獲取投資建議的便捷函數
    
    Args:
        daily_context: 每日市場資料
        total_capital: 總資金
        
    Returns:
        (decisions, allocation): 決策和配置建議
    """
    advisor = InvestmentAdvisor()
    context = advisor.build_market_context(daily_context, usd_balance=total_capital)
    decisions = advisor.get_multi_strategy_decisions(context)
    allocation = advisor.calculate_portfolio_allocation(
        decisions,
        total_capital=total_capital,
        btc_price=context.btc_price,
    )
    return decisions, allocation
