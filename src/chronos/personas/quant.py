"""
📊 Quant - 量化派投資人

風格：冷血、無情緒，只相信數學
邏輯：忽略新聞文字，僅依據技術指標 (RSI, MACD, MA) 產生的黃金/死亡交叉訊號操作

資訊偏好：
- ❌ 不看新聞 (純數學)
- ✅ 看技術指標 (RSI, MACD, MA, BB)
- ❌ 不看恐懼貪婪指數 (情緒指標不可靠)
"""

import json
from .base import InvestorPersona, PersonaConfig, MarketContext


class Quant(InvestorPersona):
    """📊 量化派投資人"""
    
    def get_config(self) -> PersonaConfig:
        return PersonaConfig(
            id="quant",
            name="Quant",
            name_zh="量化派",
            emoji="📊",
            style="數據驅動，情緒冷淡",
            philosophy="市場是可以用數學建模的。情緒是噪音，只有數據才是真相。",
            risk_tolerance="medium",
            use_news=False,  # 不看新聞
            use_technical=True,  # 只看技術指標
            use_fear_greed=False,  # 不看情緒指標
            max_position_pct=80.0,  # 最多 80% 倉位
            min_trade_pct=10.0,  # 每次最少 10%
        )
    
    def build_system_prompt(self, current_date: str) -> str:
        return f"""你是一位純粹的量化交易者，代號「量化派」(Quant)。

## 重要時間設定
現在是 {current_date}。你完全不知道明天或未來會發生什麼。
你只能根據當日及之前的資訊做出決策。

## 你的投資哲學
1. 數據就是一切：只相信技術指標和數學模型
2. 情緒是噪音：新聞、輿論、恐懼貪婪指數都是干擾
3. 紀律執行：指標發出訊號就執行，不猶豫
4. 風險管理：使用固定比例資金管理

## 你的性格
- 語氣平淡、理性
- 經常引用指標數據
- 不參與情緒化討論
- 對市場波動無動於衷

## 交易系統規則
買入信號 (滿足越多條件，倉位越大):
- RSI < 30 (超賣)
- MACD 多頭交叉 (bullish)
- 價格在布林通道下軌以下
- 價格突破 MA50 向上

賣出信號:
- RSI > 70 (超買)
- MACD 空頭交叉 (bearish)
- 價格在布林通道上軌以上
- 價格跌破 MA50

倉位計算:
- 1 個信號 = 15% 倉位
- 2 個信號 = 25% 倉位
- 3+ 個信號 = 40% 倉位

請只回覆 JSON 格式的決策。"""
    
    def make_decision_sync(self, context: MarketContext) -> str:
        """基於規則的決策（不使用 AI）"""
        
        # 計算買入和賣出信號數量
        buy_signals = 0
        sell_signals = 0
        signal_reasons = []
        
        # RSI 信號
        if context.rsi is not None:
            if context.rsi < 30:
                buy_signals += 1
                signal_reasons.append(f"RSI={context.rsi:.1f}<30 超賣")
            elif context.rsi > 70:
                sell_signals += 1
                signal_reasons.append(f"RSI={context.rsi:.1f}>70 超買")
        
        # MACD 信號
        if context.macd_signal:
            if context.macd_signal == "bullish":
                buy_signals += 1
                signal_reasons.append("MACD 多頭")
            elif context.macd_signal == "bearish":
                sell_signals += 1
                signal_reasons.append("MACD 空頭")
        
        # 布林通道信號
        if context.bb_position:
            if context.bb_position == "below_lower":
                buy_signals += 1
                signal_reasons.append("價格低於 BB 下軌")
            elif context.bb_position == "above_upper":
                sell_signals += 1
                signal_reasons.append("價格高於 BB 上軌")
        
        # MA 信號
        if context.ma_50 and context.btc_price:
            if context.btc_price > context.ma_50 * 1.02:  # 價格比 MA50 高 2%
                buy_signals += 0.5  # 半個信號
            elif context.btc_price < context.ma_50 * 0.98:  # 價格比 MA50 低 2%
                sell_signals += 0.5
        
        # 決策邏輯
        action = "HOLD"
        amount_pct = 0
        confidence = 50
        
        if buy_signals >= sell_signals and buy_signals >= 1 and context.usd_balance > 100:
            action = "BUY"
            if buy_signals >= 3:
                amount_pct = 40
                confidence = 85
            elif buy_signals >= 2:
                amount_pct = 25
                confidence = 75
            else:
                amount_pct = 15
                confidence = 65
            reason = f"買入信號: {', '.join(signal_reasons[:3])}"
        
        elif sell_signals > buy_signals and sell_signals >= 1 and context.btc_quantity > 0:
            action = "SELL"
            if sell_signals >= 3:
                amount_pct = 40
                confidence = 85
            elif sell_signals >= 2:
                amount_pct = 25
                confidence = 75
            else:
                amount_pct = 15
                confidence = 65
            reason = f"賣出信號: {', '.join(signal_reasons[:3])}"
        
        else:
            reason = "無明確信號，維持現有倉位"
            if context.rsi:
                reason += f" (RSI={context.rsi:.1f})"
        
        return json.dumps({
            "action": action,
            "amount_pct": amount_pct,
            "reason": reason,
            "confidence": confidence,
        }, ensure_ascii=False)
