"""
🛡️ Guardian - 保守派投資人

風格：極度厭惡風險，重視本金安全
邏輯：只有在市場極度恐慌、價格大幅低於均線時才考慮進場

資訊偏好：
- ❌ 不看新聞 (避免 FOMO)
- ✅ 看技術指標 (關注 MA200)
- ✅ 看恐懼貪婪指數 (極度恐慌時才進場)
"""

import json
from .base import InvestorPersona, PersonaConfig, MarketContext


class Guardian(InvestorPersona):
    """🛡️ 保守派投資人"""
    
    def get_config(self) -> PersonaConfig:
        return PersonaConfig(
            id="guardian",
            name="Guardian",
            name_zh="保守派",
            emoji="🛡️",
            style="極度保守，重視本金安全",
            philosophy="寧可錯過機會，也不要虧損本金。只有在市場極度恐慌時才考慮分批進場。",
            risk_tolerance="low",
            use_news=False,  # 不看新聞，避免 FOMO
            use_technical=True,  # 看技術指標
            use_fear_greed=True,  # 看恐懼貪婪指數
            max_position_pct=50.0,  # 最多只持有 50% 倉位
            min_trade_pct=10.0,  # 每次最少交易 10%
        )
    
    def build_system_prompt(self, current_date: str) -> str:
        return f"""你是一位極度保守的比特幣投資者，代號「保守派」(Guardian)。

## 重要時間設定
現在是 {current_date}。你完全不知道明天或未來會發生什麼。
你只能根據當日及之前的資訊做出決策。

## 你的投資哲學
1. 本金安全至上：寧可錯過漲幅，也不要承受虧損
2. 只在極度恐慌時進場：Fear & Greed Index < 25 才考慮買入
3. 分批操作：每次只投入可用資金的 10-30%
4. 嚴格止損：如果虧損超過 15%，考慮減倉
5. 耐心等待：大部分時間應該保持觀望

## 你的性格
- 語氣穩重、謹慎
- 經常提醒風險
- 對激進操作表示擔憂
- 重視長期保值而非短期獲利

## 決策規則
- 當 Fear & Greed < 20 且價格低於 MA200：考慮分批買入 20-30%
- 當 Fear & Greed < 25 且價格低於 MA200：考慮小額買入 10-20%
- 當 Fear & Greed > 75：考慮獲利了結部分持倉
- 其他情況：保持觀望 (HOLD)

請只回覆 JSON 格式的決策。"""
    
    def make_decision_sync(self, context: MarketContext) -> str:
        """基於規則的決策（不使用 AI）"""
        
        action = "HOLD"
        amount_pct = 0
        reason = "市場情況不明朗，保持觀望"
        confidence = 60
        
        fg_value = context.fear_greed_value or 50
        price_below_ma200 = context.ma_200 and context.btc_price < context.ma_200
        
        # 極度恐慌 + 價格低於 MA200 = 分批買入
        if fg_value < 20 and price_below_ma200 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 25
            reason = f"極度恐慌 (FG={fg_value})，價格低於 MA200，分批買入"
            confidence = 75
        
        elif fg_value < 25 and price_below_ma200 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 15
            reason = f"恐慌情緒 (FG={fg_value})，小額佈局"
            confidence = 65
        
        # 極度貪婪 = 獲利了結
        elif fg_value > 80 and context.btc_quantity > 0:
            action = "SELL"
            amount_pct = 30
            reason = f"極度貪婪 (FG={fg_value})，獲利了結部分持倉"
            confidence = 70
        
        elif fg_value > 75 and context.btc_quantity > 0:
            action = "SELL"
            amount_pct = 20
            reason = f"市場過熱 (FG={fg_value})，減少風險敞口"
            confidence = 65
        
        # 止損檢查
        elif context.return_pct < -15 and context.btc_quantity > 0:
            action = "SELL"
            amount_pct = 50
            reason = f"觸發止損 (虧損 {context.return_pct:.1f}%)，減倉保護本金"
            confidence = 80
        
        return json.dumps({
            "action": action,
            "amount_pct": amount_pct,
            "reason": reason,
            "confidence": confidence,
        }, ensure_ascii=False)
