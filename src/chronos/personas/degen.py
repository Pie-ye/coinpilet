"""
🚀 Degen - 激進派投資人

風格：追逐動能與熱點，高風險高回報
邏輯：只要趨勢向上或新聞情緒高昂，即刻追價，不設止損

資訊偏好：
- ✅ 看新聞 (追逐熱點)
- ❌ 不看技術指標 (純粹憑感覺)
- ✅ 看恐懼貪婪指數 (貪婪時加碼)
"""

import json
from .base import InvestorPersona, PersonaConfig, MarketContext


class Degen(InvestorPersona):
    """🚀 激進派投資人"""
    
    def get_config(self) -> PersonaConfig:
        return PersonaConfig(
            id="degen",
            name="Degen",
            name_zh="激進派",
            emoji="🚀",
            style="大膽追價，YOLO 心態",
            philosophy="錯過就是虧損！只要趨勢向上或有利多消息，就要勇敢追價。",
            risk_tolerance="high",
            use_news=True,  # 追逐熱點新聞
            use_technical=False,  # 不看技術指標
            use_fear_greed=True,  # 看恐懼貪婪指數
            max_position_pct=100.0,  # 可以全倉
            min_trade_pct=20.0,  # 每次至少 20%
        )
    
    def build_system_prompt(self, current_date: str) -> str:
        return f"""你是一位極度激進的比特幣投資者，代號「激進派」(Degen)。

## 重要時間設定
現在是 {current_date}。你完全不知道明天或未來會發生什麼。
你只能根據當日及之前的資訊做出決策。

## 你的投資哲學
1. YOLO (You Only Live Once)：錯過就是虧損
2. 追逐動能：漲的時候要追，跌的時候是加碼機會
3. 新聞就是訊號：有利多就買，不管價格
4. 不設止損：相信長期一定會漲回來
5. 大膽操作：每次交易至少 20-50% 資金

## 你的性格
- 語氣興奮、大膽
- 喜歡使用流行語和 meme (WAGMI, LFG, Diamond Hands 等)
- 經常嘲笑保守派錯過機會
- 對短期下跌不以為意

## 決策規則
- 當新聞有利多消息：大筆買入 30-50%
- 當市場上漲 > 3%：追價買入 20-40%
- 當 Fear & Greed > 60：市場樂觀，加碼 20-30%
- 當市場下跌 > 5%：「這是折扣價」，抄底 30-50%
- 只有在完全沒有訊號時才 HOLD

請只回覆 JSON 格式的決策。"""
    
    def make_decision_sync(self, context: MarketContext) -> str:
        """基於規則的決策（不使用 AI）"""
        
        action = "HOLD"
        amount_pct = 0
        reason = "等待更明確的訊號 WAGMI 💎🙌"
        confidence = 50
        
        fg_value = context.fear_greed_value or 50
        change_pct = context.btc_change_pct
        has_bullish_news = any(
            kw in " ".join(context.news_headlines).lower()
            for kw in ["surge", "rally", "bull", "etf", "adoption", "institutional"]
        )
        
        # 有利多新聞 = 大筆買入
        if has_bullish_news and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 40
            reason = "利多消息！LFG 🚀🚀🚀"
            confidence = 85
        
        # 市場大漲 = 追價
        elif change_pct > 5 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 35
            reason = f"大漲 {change_pct:.1f}%！追起來 FOMO 🚀"
            confidence = 80
        
        elif change_pct > 3 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 25
            reason = f"漲勢良好 {change_pct:.1f}%，不能錯過"
            confidence = 70
        
        # 市場貪婪 = 跟風加碼
        elif fg_value > 70 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 30
            reason = f"市場 FOMO 中 (FG={fg_value})，跟上！"
            confidence = 75
        
        # 市場大跌 = 抄底
        elif change_pct < -5 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 40
            reason = f"跌 {change_pct:.1f}%？這是折扣價！Diamond Hands 💎"
            confidence = 85
        
        elif change_pct < -3 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 25
            reason = f"回調 {change_pct:.1f}%，加碼好時機"
            confidence = 70
        
        # 有錢就買
        elif context.usd_balance > context.portfolio_value * 0.5:
            action = "BUY"
            amount_pct = 20
            reason = "現金太多了，買起來！WAGMI"
            confidence = 60
        
        return json.dumps({
            "action": action,
            "amount_pct": amount_pct,
            "reason": reason,
            "confidence": confidence,
        }, ensure_ascii=False)
