"""
技術指標計算模組 - 使用 pandas-ta 計算常用技術指標

支援指標:
- RSI (相對強弱指標)
- MACD (指數平滑異同移動平均線)
- SMA / EMA (移動平均線)
- Bollinger Bands (布林通道)

所有指標都包含 AI 解讀標籤，方便 Writer 模組使用
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


@dataclass
class RSIIndicator:
    """RSI 指標數據"""

    value: float  # RSI 值 (0-100)
    period: int = 14  # 計算週期

    @property
    def signal(self) -> str:
        """AI 解讀信號"""
        if self.value > 70:
            return "overbought"  # 超買
        elif self.value < 30:
            return "oversold"  # 超賣
        else:
            return "neutral"  # 中性

    @property
    def signal_zh(self) -> str:
        """中文信號描述"""
        signals = {
            "overbought": "超買區 ⚠️ 提醒回調風險，不宜追高",
            "oversold": "超賣區 💡 可能出現反彈，關注底部支撐",
            "neutral": "中性區間",
        }
        return signals[self.signal]

    def to_dict(self) -> dict:
        return {
            "value": round(float(self.value), 2),
            "period": self.period,
            "signal": self.signal,
            "signal_zh": self.signal_zh,
        }


@dataclass
class MACDIndicator:
    """MACD 指標數據"""

    macd: float  # MACD 線 (DIF)
    signal: float  # 信號線 (DEA)
    histogram: float  # 柱狀圖 (MACD - Signal)
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    @property
    def trend_signal(self) -> str:
        """趨勢信號"""
        # MACD 線在信號線之上
        if self.macd > self.signal:
            if self.histogram > 0 and self.macd > 0:
                return "strong_bullish"  # 強勢看漲
            return "bullish"  # 看漲
        else:
            if self.histogram < 0 and self.macd < 0:
                return "strong_bearish"  # 強勢看跌
            return "bearish"  # 看跌

    @property
    def crossover(self) -> Optional[str]:
        """交叉信號 (需要歷史數據才能判斷，這裡只看當前狀態)"""
        # 簡化判斷：histogram 接近 0 代表可能剛發生交叉
        if abs(self.histogram) < abs(self.macd) * 0.1:
            if self.histogram > 0:
                return "golden_cross"  # 黃金交叉 (剛發生)
            else:
                return "death_cross"  # 死亡交叉 (剛發生)
        return None

    @property
    def signal_zh(self) -> str:
        """中文信號描述"""
        signals = {
            "strong_bullish": "強勢看漲 📈 MACD 位於零軸上方，多頭動能強勁",
            "bullish": "偏多 📈 DIF 線在 DEA 線之上",
            "strong_bearish": "強勢看跌 📉 MACD 位於零軸下方，空頭動能強勁",
            "bearish": "偏空 📉 DIF 線在 DEA 線之下",
        }
        base = signals[self.trend_signal]

        if self.crossover == "golden_cross":
            base += " | 🔔 黃金交叉形成，看漲訊號"
        elif self.crossover == "death_cross":
            base += " | 🔔 死亡交叉形成，看跌訊號"

        return base

    def to_dict(self) -> dict:
        return {
            "macd": round(float(self.macd), 2),
            "signal": round(float(self.signal), 2),
            "histogram": round(float(self.histogram), 2),
            "trend_signal": self.trend_signal,
            "crossover": self.crossover,
            "signal_zh": self.signal_zh,
        }


@dataclass
class MovingAverages:
    """移動平均線數據"""

    current_price: float  # 當前價格
    sma_50: float  # 50 日簡單移動平均
    sma_200: float  # 200 日簡單移動平均
    ema_50: float  # 50 日指數移動平均
    ema_200: float  # 200 日指數移動平均

    @property
    def trend(self) -> str:
        """長期趨勢判斷 (基於 MA200)"""
        if self.current_price > self.sma_200:
            return "bullish"  # 牛市
        else:
            return "bearish"  # 熊市

    @property
    def golden_cross(self) -> bool:
        """黃金交叉 (MA50 > MA200)"""
        return self.sma_50 > self.sma_200

    @property
    def death_cross(self) -> bool:
        """死亡交叉 (MA50 < MA200)"""
        return self.sma_50 < self.sma_200

    @property
    def price_vs_ma200_pct(self) -> float:
        """價格相對 MA200 的偏離百分比"""
        return ((self.current_price - self.sma_200) / self.sma_200) * 100

    @property
    def signal_zh(self) -> str:
        """中文信號描述"""
        parts = []

        # MA200 牛熊判斷
        if self.trend == "bullish":
            parts.append(f"價格在 MA200 之上 ({self.price_vs_ma200_pct:+.1f}%)，處於長期牛市格局 🐂")
        else:
            parts.append(f"價格在 MA200 之下 ({self.price_vs_ma200_pct:+.1f}%)，處於長期熊市格局 🐻")

        # 黃金/死亡交叉
        if self.golden_cross:
            parts.append("MA50 > MA200 黃金交叉，中期趨勢向上")
        else:
            parts.append("MA50 < MA200 死亡交叉，中期趨勢向下")

        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "current_price": round(float(self.current_price), 2),
            "sma_50": round(float(self.sma_50), 2),
            "sma_200": round(float(self.sma_200), 2),
            "ema_50": round(float(self.ema_50), 2),
            "ema_200": round(float(self.ema_200), 2),
            "trend": self.trend,
            "golden_cross": bool(self.golden_cross),
            "price_vs_ma200_pct": round(float(self.price_vs_ma200_pct), 2),
            "signal_zh": self.signal_zh,
        }


@dataclass
class BollingerBands:
    """布林通道數據"""

    upper: float  # 上軌
    middle: float  # 中軌 (SMA20)
    lower: float  # 下軌
    current_price: float  # 當前價格
    bandwidth: float  # 帶寬 (波動率指標)
    period: int = 20
    std_dev: float = 2.0

    @property
    def position(self) -> str:
        """價格在布林通道中的位置"""
        if self.current_price >= self.upper:
            return "above_upper"  # 突破上軌
        elif self.current_price <= self.lower:
            return "below_lower"  # 跌破下軌
        elif self.current_price > self.middle:
            return "upper_half"  # 上半區
        else:
            return "lower_half"  # 下半區

    @property
    def squeeze(self) -> bool:
        """布林通道收窄 (即將變盤)"""
        # bandwidth < 10% 視為收窄
        return self.bandwidth < 10

    @property
    def percent_b(self) -> float:
        """%B 指標 (價格在通道中的相對位置 0-1)"""
        if self.upper == self.lower:
            return 0.5
        return (self.current_price - self.lower) / (self.upper - self.lower)

    @property
    def signal_zh(self) -> str:
        """中文信號描述"""
        position_desc = {
            "above_upper": "價格突破上軌 ⚠️ 可能過熱，注意回調風險",
            "below_lower": "價格跌破下軌 💡 可能超跌，關注反彈機會",
            "upper_half": "價格位於通道上半區，偏強勢",
            "lower_half": "價格位於通道下半區，偏弱勢",
        }

        desc = position_desc[self.position]

        if self.squeeze:
            desc += " | 🔔 通道收窄，即將發生大幅波動"

        return desc

    def to_dict(self) -> dict:
        return {
            "upper": round(float(self.upper), 2),
            "middle": round(float(self.middle), 2),
            "lower": round(float(self.lower), 2),
            "bandwidth": round(float(self.bandwidth), 2),
            "percent_b": round(float(self.percent_b), 3),
            "position": self.position,
            "squeeze": bool(self.squeeze),
            "signal_zh": self.signal_zh,
        }


@dataclass
class TechnicalIndicators:
    """完整技術指標集合"""

    rsi: RSIIndicator
    macd: MACDIndicator
    moving_averages: MovingAverages
    bollinger_bands: BollingerBands
    calculated_at: str = ""  # 計算時間

    def to_dict(self) -> dict:
        return {
            "rsi": self.rsi.to_dict(),
            "macd": self.macd.to_dict(),
            "moving_averages": self.moving_averages.to_dict(),
            "bollinger_bands": self.bollinger_bands.to_dict(),
            "calculated_at": self.calculated_at,
        }

    @property
    def overall_signal(self) -> str:
        """綜合技術信號"""
        bullish_count = 0
        bearish_count = 0

        # RSI
        if self.rsi.signal == "oversold":
            bullish_count += 1
        elif self.rsi.signal == "overbought":
            bearish_count += 1

        # MACD
        if "bullish" in self.macd.trend_signal:
            bullish_count += 1
        else:
            bearish_count += 1

        # 均線趨勢
        if self.moving_averages.trend == "bullish":
            bullish_count += 1
        else:
            bearish_count += 1

        # 布林通道
        if self.bollinger_bands.position == "below_lower":
            bullish_count += 1
        elif self.bollinger_bands.position == "above_upper":
            bearish_count += 1

        if bullish_count >= 3:
            return "bullish"
        elif bearish_count >= 3:
            return "bearish"
        else:
            return "neutral"

    @property
    def overall_signal_zh(self) -> str:
        """綜合技術信號中文描述"""
        signals = {
            "bullish": "📈 技術面偏多",
            "bearish": "📉 技術面偏空",
            "neutral": "⚖️ 技術面中性",
        }
        return signals[self.overall_signal]


class TechnicalAnalyzer:
    """
    技術指標分析器

    使用方式:
        analyzer = TechnicalAnalyzer()

        # 從 K 線數據計算指標
        klines = [{"open": 100, "high": 105, "low": 98, "close": 102, "volume": 1000}, ...]
        indicators = analyzer.calculate(klines)

        print(indicators.rsi.value)
        print(indicators.macd.signal_zh)
    """

    def __init__(self):
        """初始化分析器"""
        pass

    def _prepare_dataframe(self, klines: list[dict]) -> pd.DataFrame:
        """
        將 K 線數據轉換為 pandas DataFrame

        Args:
            klines: K 線數據列表

        Returns:
            pd.DataFrame: 包含 OHLCV 數據的 DataFrame
        """
        df = pd.DataFrame(klines)

        # 確保欄位名稱正確
        column_mapping = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }

        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)

        # 確保數值類型
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def calculate(self, klines: list[dict]) -> TechnicalIndicators:
        """
        計算所有技術指標

        Args:
            klines: K 線數據列表 (至少需要 200 根以計算 MA200)

        Returns:
            TechnicalIndicators: 完整的技術指標集合

        Raises:
            ValueError: K 線數據不足
        """
        if len(klines) < 200:
            logger.warning(
                f"K 線數據不足 ({len(klines)} 根)，MA200 可能不準確"
            )

        df = self._prepare_dataframe(klines)
        current_price = df["Close"].iloc[-1]

        logger.info(f"正在計算技術指標 (共 {len(df)} 根 K 線)...")

        # 計算 RSI
        rsi_series = ta.rsi(df["Close"], length=14)
        rsi = RSIIndicator(value=rsi_series.iloc[-1])

        # 計算 MACD
        macd_df = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        macd = MACDIndicator(
            macd=macd_df.iloc[-1, 0],  # MACD_12_26_9
            signal=macd_df.iloc[-1, 2],  # MACDs_12_26_9
            histogram=macd_df.iloc[-1, 1],  # MACDh_12_26_9
        )

        # 計算移動平均線
        sma_50 = ta.sma(df["Close"], length=50).iloc[-1]
        sma_200 = ta.sma(df["Close"], length=200).iloc[-1] if len(df) >= 200 else ta.sma(df["Close"], length=len(df)).iloc[-1]
        ema_50 = ta.ema(df["Close"], length=50).iloc[-1]
        ema_200 = ta.ema(df["Close"], length=200).iloc[-1] if len(df) >= 200 else ta.ema(df["Close"], length=len(df)).iloc[-1]

        moving_averages = MovingAverages(
            current_price=current_price,
            sma_50=sma_50,
            sma_200=sma_200,
            ema_50=ema_50,
            ema_200=ema_200,
        )

        # 計算布林通道
        bbands_df = ta.bbands(df["Close"], length=20, std=2.0)
        bb_upper = bbands_df.iloc[-1, 0]  # BBU_20_2.0
        bb_middle = bbands_df.iloc[-1, 1]  # BBM_20_2.0
        bb_lower = bbands_df.iloc[-1, 2]  # BBL_20_2.0
        bb_bandwidth = bbands_df.iloc[-1, 3]  # BBB_20_2.0 (bandwidth)

        bollinger_bands = BollingerBands(
            upper=bb_upper,
            middle=bb_middle,
            lower=bb_lower,
            current_price=current_price,
            bandwidth=bb_bandwidth,
        )

        from datetime import datetime

        indicators = TechnicalIndicators(
            rsi=rsi,
            macd=macd,
            moving_averages=moving_averages,
            bollinger_bands=bollinger_bands,
            calculated_at=datetime.now().isoformat(),
        )

        logger.info(f"技術指標計算完成 - 綜合信號: {indicators.overall_signal_zh}")

        return indicators

    def calculate_from_cache(self, cached_klines: list[dict]) -> TechnicalIndicators:
        """
        從快取的 K 線數據計算指標

        Args:
            cached_klines: 快取的 K 線數據 (與 OHLCCache 格式相容)

        Returns:
            TechnicalIndicators: 技術指標集合
        """
        return self.calculate(cached_klines)
