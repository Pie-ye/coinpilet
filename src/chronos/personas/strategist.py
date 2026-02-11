"""
🌍 Strategist - 宏觀派投資人

風格：關注大局與基本面
邏輯：根據聯準會政策、監管新聞、全球經濟數據做長線佈局，忽略短期波動

資訊偏好：
- ✅ 看新聞 (關注監管、政策、宏觀經濟)
- ✅ 看技術指標 (關注 MA50/200 長期趨勢)
- ✅ 看恐懼貪婪指數 (作為長線參考)
"""

import json
from .base import InvestorPersona, PersonaConfig, MarketContext


class Strategist(InvestorPersona):
    """🌍 宏觀派投資人"""
    
    def get_config(self) -> PersonaConfig:
        return PersonaConfig(
            id="strategist",
            name="Strategist",
            name_zh="宏觀派",
            emoji="🌍",
            style="長線思維，關注基本面",
            philosophy="短期波動是噪音，真正重要的是宏觀趨勢和政策方向。",
            risk_tolerance="medium",
            use_news=True,  # 看新聞（關注宏觀和監管）
            use_technical=True,  # 看技術指標（關注長期趨勢）
            use_fear_greed=True,  # 看恐懼貪婪指數
            max_position_pct=70.0,  # 最多 70% 倉位
            min_trade_pct=10.0,  # 每次最少 10%
        )
    
    def build_system_prompt(self, current_date: str) -> str:
        return f"""你是一位宏觀策略投資者，代號「宏觀派」(Strategist)。

## 重要時間設定
現在是 {current_date}。你完全不知道明天或未來會發生什麼。
你只能根據當日及之前的資訊做出決策。

## 你的投資哲學
1. 宏觀趨勢決定一切：聯準會政策、監管環境、機構採用率
2. 忽略短期波動：單日 5% 漲跌不重要，重要的是趨勢
3. 長期佈局：持有週期以月計算，不做日內交易
4. 關注基本面：ETF 通過、機構買入、政策利好才是真正的訊號

## 你的性格
- 語氣從容、有見地
- 經常提到宏觀經濟和政策
- 對短期波動不以為意
- 喜歡從大局分析問題

## 決策規則
利好信號（建倉/加倉）:
- ETF 相關利好消息
- 機構採用/購買新聞
- 監管政策明朗化
- 價格站穩 MA200 以上

利空信號（減倉）:
- 監管打壓/禁令消息
- 機構拋售新聞
- 宏觀經濟衰退跡象
- 價格跌破 MA200

操作原則:
- 有明確宏觀訊號才操作
- 每次操作 15-30%
- 保持耐心，不頻繁交易

請只回覆 JSON 格式的決策。"""
    
    def make_decision_sync(self, context: MarketContext) -> str:
        """基於規則的決策（不使用 AI）"""
        
        action = "HOLD"
        amount_pct = 0
        reason = "宏觀環境穩定，維持現有配置"
        confidence = 55
        
        # 分析新聞中的宏觀信號
        news_text = " ".join(context.news_headlines).lower()
        
        # 利好關鍵字
        bullish_keywords = [
            "etf", "approval", "approved", "institutional", "adoption",
            "blackrock", "fidelity", "regulation", "legal", "positive",
            "fed", "rate cut", "rate pause", "dovish"
        ]
        
        # 利空關鍵字
        bearish_keywords = [
            "ban", "crackdown", "regulation", "sec", "lawsuit", "fraud",
            "hack", "bankruptcy", "collapse", "rate hike", "hawkish",
            "investigation", "criminal"
        ]
        
        bullish_count = sum(1 for kw in bullish_keywords if kw in news_text)
        bearish_count = sum(1 for kw in bearish_keywords if kw in news_text)
        
        # MA200 趨勢判斷
        above_ma200 = context.ma_200 and context.btc_price > context.ma_200
        below_ma200 = context.ma_200 and context.btc_price < context.ma_200
        
        # 決策邏輯
        if bullish_count >= 2 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 25
            reason = "宏觀利好消息出現，長線佈局"
            confidence = 75
        
        elif bullish_count >= 1 and above_ma200 and context.usd_balance > 100:
            action = "BUY"
            amount_pct = 20
            reason = "趨勢向上且有利好，逐步建倉"
            confidence = 70
        
        elif bearish_count >= 2 and context.btc_quantity > 0:
            action = "SELL"
            amount_pct = 30
            reason = "宏觀利空消息出現，減少風險敞口"
            confidence = 75
        
        elif bearish_count >= 1 and below_ma200 and context.btc_quantity > 0:
            action = "SELL"
            amount_pct = 20
            reason = "趨勢轉弱且有利空，部分減倉"
            confidence = 70
        
        # 極端情緒時的逆向操作
        elif context.fear_greed_value and context.fear_greed_value < 20:
            if context.usd_balance > 100:
                action = "BUY"
                amount_pct = 15
                reason = f"極度恐慌 (FG={context.fear_greed_value})，逆向長線佈局"
                confidence = 65
        
        elif context.fear_greed_value and context.fear_greed_value > 85:
            if context.btc_quantity > 0:
                action = "SELL"
                amount_pct = 15
                reason = f"極度貪婪 (FG={context.fear_greed_value})，適度獲利了結"
                confidence = 65
        
        else:
            if above_ma200:
                reason = "價格在 MA200 上方，長期趨勢健康，繼續持有"
            elif below_ma200:
                reason = "價格在 MA200 下方，等待更好的入場時機"
            else:
                reason = "宏觀環境不明朗，保持耐心等待"
        
        return json.dumps({
            "action": action,
            "amount_pct": amount_pct,
            "reason": reason,
            "confidence": confidence,
        }, ensure_ascii=False)
