"""
籌碼面指標收集器 - 抓取 OI、多空比、交易所流量

資料來源優先順序:
1. Coinglass API (付費，功能最全)
2. Binance 公開 API (免費，作為備用)

Binance 免費 API:
- /fapi/v1/openInterest - 未平倉量
- /futures/data/globalLongShortAccountRatio - 多空比
- /fapi/v1/fundingRate - 資金費率
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


@dataclass
class OpenInterestData:
    """未平倉合約量資料結構"""
    
    total_oi_usd: float  # 總未平倉量 (USD)
    oi_change_24h: float  # 24H 變化百分比
    oi_change_4h: float  # 4H 變化百分比
    weighted_funding_rate: float  # 加權資金費率
    signal: str  # 訊號: bullish, bearish, neutral
    signal_zh: str  # 中文訊號說明
    
    def to_dict(self) -> dict:
        return {
            "total_oi_usd": self.total_oi_usd,
            "oi_change_24h": self.oi_change_24h,
            "oi_change_4h": self.oi_change_4h,
            "weighted_funding_rate": self.weighted_funding_rate,
            "signal": self.signal,
            "signal_zh": self.signal_zh,
        }


@dataclass
class LongShortRatioData:
    """多空比資料結構"""
    
    long_ratio: float  # 多頭比例 (%)
    short_ratio: float  # 空頭比例 (%)
    long_short_ratio: float  # 多空比 (>1 多頭主導, <1 空頭主導)
    signal: str  # 訊號: extreme_long, extreme_short, neutral
    signal_zh: str  # 中文訊號說明
    
    def to_dict(self) -> dict:
        return {
            "long_ratio": self.long_ratio,
            "short_ratio": self.short_ratio,
            "long_short_ratio": self.long_short_ratio,
            "signal": self.signal,
            "signal_zh": self.signal_zh,
        }


@dataclass
class ExchangeFlowData:
    """交易所淨流入/流出資料結構"""
    
    net_flow_usd: float  # 淨流入 (正=流入, 負=流出)
    inflow_usd: float  # 流入量
    outflow_usd: float  # 流出量
    net_flow_btc: float  # 淨流入 (BTC)
    signal: str  # 訊號: selling_pressure, accumulation, neutral
    signal_zh: str  # 中文訊號說明
    
    def to_dict(self) -> dict:
        return {
            "net_flow_usd": self.net_flow_usd,
            "inflow_usd": self.inflow_usd,
            "outflow_usd": self.outflow_usd,
            "net_flow_btc": self.net_flow_btc,
            "signal": self.signal,
            "signal_zh": self.signal_zh,
        }


@dataclass
class DerivativesData:
    """籌碼面指標完整資料結構"""
    
    open_interest: Optional[OpenInterestData] = None
    long_short_ratio: Optional[LongShortRatioData] = None
    exchange_flow: Optional[ExchangeFlowData] = None
    collected_at: str = ""
    
    def to_dict(self) -> dict:
        return {
            "open_interest": self.open_interest.to_dict() if self.open_interest else None,
            "long_short_ratio": self.long_short_ratio.to_dict() if self.long_short_ratio else None,
            "exchange_flow": self.exchange_flow.to_dict() if self.exchange_flow else None,
            "collected_at": self.collected_at,
        }
    
    def has_any_data(self) -> bool:
        """檢查是否有任何籌碼數據"""
        return any([self.open_interest, self.long_short_ratio, self.exchange_flow])


class CoinglassClient:
    """籌碼面指標收集器 - 優先使用 Coinglass，備用 Binance 公開 API"""
    
    # Coinglass API
    COINGLASS_BASE_URL = "https://open-api.coinglass.com/public/v2"
    
    # Binance 公開 API (免費)
    BINANCE_FUTURES_URL = "https://fapi.binance.com"
    BINANCE_DATA_URL = "https://fapi.binance.com/futures/data"
    
    TIMEOUT = 30
    
    # 極端值閾值
    EXTREME_LONG_RATIO = 2.5  # 多空比 > 2.5 視為極端做多
    EXTREME_SHORT_RATIO = 0.4  # 多空比 < 0.4 視為極端做空
    HIGH_OI_CHANGE_THRESHOLD = 10  # OI 24H 變化 > 10% 視為顯著
    SIGNIFICANT_FLOW_USD = 100_000_000  # 1億美元視為顯著流量
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化籌碼面指標收集器
        
        Args:
            api_key: Coinglass API Key (選填，沒有則使用 Binance 公開 API)
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CoinPilot-AI/0.1.0",
        })
        
        # 用於追蹤數據來源
        self.data_source = "binance"
        
        if api_key:
            self.session.headers.update({
                "coinglassSecret": api_key,
            })
            self.data_source = "coinglass"
            logger.info("籌碼面指標: 使用 Coinglass API")
        else:
            logger.info("籌碼面指標: 使用 Binance 免費公開 API")
    
    def _make_coinglass_request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """
        發送 Coinglass API 請求
        """
        if not self.api_key:
            return None
        
        url = f"{self.COINGLASS_BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("success") is False or data.get("code") != "0":
                error_msg = data.get("msg", "Unknown error")
                logger.debug(f"Coinglass API 錯誤: {error_msg}")
                return None
            
            return data.get("data")
            
        except Exception as e:
            logger.debug(f"Coinglass API 請求失敗: {e}")
            return None
    
    def _make_binance_request(self, url: str, params: dict = None) -> Optional[dict]:
        """
        發送 Binance 公開 API 請求
        """
        try:
            response = self.session.get(url, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Binance API 請求失敗: {e}")
            return None
    
    def get_open_interest(self, symbol: str = "BTC") -> Optional[OpenInterestData]:
        """
        獲取未平倉合約量 (Open Interest)
        優先使用 Coinglass，失敗則使用 Binance
        """
        logger.info(f"正在獲取 {symbol} Open Interest...")
        
        # 嘗試 Coinglass
        if self.api_key:
            data = self._make_coinglass_request("/open_interest", {"symbol": symbol})
            if data:
                return self._parse_coinglass_oi(data)
        
        # 備用: Binance 免費 API
        return self._get_oi_from_binance(symbol)
    
    def _get_oi_from_binance(self, symbol: str = "BTC") -> Optional[OpenInterestData]:
        """從 Binance 獲取 OI 數據"""
        binance_symbol = f"{symbol}USDT"
        
        # 獲取當前 OI
        oi_data = self._make_binance_request(
            f"{self.BINANCE_FUTURES_URL}/fapi/v1/openInterest",
            {"symbol": binance_symbol}
        )
        
        # 獲取資金費率
        funding_data = self._make_binance_request(
            f"{self.BINANCE_FUTURES_URL}/fapi/v1/fundingRate",
            {"symbol": binance_symbol, "limit": 1}
        )
        
        if not oi_data:
            return None
        
        try:
            # Binance 返回的是合約數量，需要轉換為 USD
            oi_value = float(oi_data.get("openInterest", 0))
            
            # 獲取當前價格來計算 USD 價值
            price_data = self._make_binance_request(
                f"{self.BINANCE_FUTURES_URL}/fapi/v1/ticker/price",
                {"symbol": binance_symbol}
            )
            price = float(price_data.get("price", 1)) if price_data else 1
            total_oi_usd = oi_value * price
            
            # 資金費率
            funding_rate = 0
            if funding_data and len(funding_data) > 0:
                funding_rate = float(funding_data[0].get("fundingRate", 0)) * 100
            
            # 獲取 24H OI 歷史來計算變化
            oi_change_24h = self._calculate_oi_change_binance(binance_symbol, total_oi_usd)
            
            signal, signal_zh = self._analyze_oi_signal(oi_change_24h, funding_rate)
            
            result = OpenInterestData(
                total_oi_usd=total_oi_usd,
                oi_change_24h=oi_change_24h,
                oi_change_4h=0,  # Binance 不提供 4H 數據
                weighted_funding_rate=funding_rate,
                signal=signal,
                signal_zh=signal_zh,
            )
            
            self.data_source = "binance"
            logger.info(f"[Binance] Open Interest: ${total_oi_usd:,.0f} ({oi_change_24h:+.2f}%)")
            return result
            
        except Exception as e:
            logger.error(f"Binance OI 資料解析失敗: {e}")
            return None
    
    def _calculate_oi_change_binance(self, symbol: str, current_oi: float) -> float:
        """計算 24H OI 變化百分比 (從 Binance)"""
        try:
            # 獲取 OI 歷史數據
            hist_data = self._make_binance_request(
                f"{self.BINANCE_DATA_URL}/openInterestHist",
                {"symbol": symbol, "period": "1h", "limit": 24}
            )
            
            if hist_data and len(hist_data) > 0:
                # 取最舊的數據點
                old_oi = float(hist_data[0].get("sumOpenInterestValue", current_oi))
                if old_oi > 0:
                    return ((current_oi - old_oi) / old_oi) * 100
        except Exception:
            pass
        
        return 0.0
    
    def _parse_coinglass_oi(self, data) -> Optional[OpenInterestData]:
        """解析 Coinglass OI 數據"""
        try:
            if isinstance(data, list) and len(data) > 0:
                oi_data = data[0]
            else:
                oi_data = data
            
            total_oi = float(oi_data.get("openInterest", 0))
            oi_change_24h = float(oi_data.get("oiChange24h", 0)) * 100
            oi_change_4h = float(oi_data.get("oiChange4h", 0)) * 100 if "oiChange4h" in oi_data else 0
            funding_rate = float(oi_data.get("avgFundingRate", 0)) * 100
            
            signal, signal_zh = self._analyze_oi_signal(oi_change_24h, funding_rate)
            
            result = OpenInterestData(
                total_oi_usd=total_oi,
                oi_change_24h=oi_change_24h,
                oi_change_4h=oi_change_4h,
                weighted_funding_rate=funding_rate,
                signal=signal,
                signal_zh=signal_zh,
            )
            
            self.data_source = "coinglass"
            logger.info(f"[Coinglass] Open Interest: ${total_oi:,.0f} ({oi_change_24h:+.2f}%)")
            return result
            
        except Exception as e:
            logger.error(f"Coinglass OI 資料解析失敗: {e}")
            return None
    
    def _analyze_oi_signal(self, oi_change_24h: float, funding_rate: float) -> tuple[str, str]:
        """分析 OI 訊號"""
        # OI 上漲 + 正資金費率 = 多頭強勢
        # OI 下跌 = 平倉/減倉
        # 高資金費率 = 過熱警告
        
        if oi_change_24h > self.HIGH_OI_CHANGE_THRESHOLD:
            if funding_rate > 0.05:
                return "overheated", "⚠️ OI 大幅上漲且資金費率偏高，市場可能過熱，需注意回調風險。多頭持倉成本上升，軋空後可能出現獲利了結。"
            else:
                return "bullish", "📈 OI 顯著上漲，新資金持續進場做多。若價格同步上漲，顯示趨勢強勁（真漲）；需配合價格走勢判斷。"
        elif oi_change_24h < -self.HIGH_OI_CHANGE_THRESHOLD:
            return "deleveraging", "📉 OI 大幅下降，市場正在去槓桿。可能是多空雙殺後的清算，或是主動減倉。短期波動可能加劇。"
        elif abs(funding_rate) > 0.1:
            if funding_rate > 0:
                return "long_crowded", "⚠️ 資金費率極高，多頭擁擠。做多成本高昂，容易發生多頭清算 (Long Squeeze)。"
            else:
                return "short_crowded", "⚠️ 資金費率為負，空頭擁擠。容易發生軋空 (Short Squeeze)。"
        else:
            return "neutral", "⚖️ OI 變化溫和，市場持倉穩定，無明顯極端訊號。"
    
    def get_long_short_ratio(self, symbol: str = "BTC") -> Optional[LongShortRatioData]:
        """
        獲取多空比 (Long/Short Ratio)
        優先使用 Coinglass，失敗則使用 Binance
        """
        logger.info(f"正在獲取 {symbol} 多空比...")
        
        # 嘗試 Coinglass
        if self.api_key:
            data = self._make_coinglass_request("/long_short", {"symbol": symbol})
            if data:
                return self._parse_coinglass_ls(data)
        
        # 備用: Binance 免費 API
        return self._get_ls_from_binance(symbol)
    
    def _get_ls_from_binance(self, symbol: str = "BTC") -> Optional[LongShortRatioData]:
        """從 Binance 獲取多空比數據"""
        binance_symbol = f"{symbol}USDT"
        
        # 獲取全球賬戶多空比
        data = self._make_binance_request(
            f"{self.BINANCE_DATA_URL}/globalLongShortAccountRatio",
            {"symbol": binance_symbol, "period": "1h", "limit": 1}
        )
        
        if not data or len(data) == 0:
            # 嘗試備用端點
            data = self._make_binance_request(
                f"{self.BINANCE_DATA_URL}/topLongShortAccountRatio",
                {"symbol": binance_symbol, "period": "1h", "limit": 1}
            )
        
        if not data or len(data) == 0:
            return None
        
        try:
            ls_data = data[0]
            
            # Binance 返回的格式: {"longShortRatio": "1.5", "longAccount": "0.6", "shortAccount": "0.4"}
            long_short_ratio = float(ls_data.get("longShortRatio", 1))
            long_account = float(ls_data.get("longAccount", 0.5)) * 100
            short_account = float(ls_data.get("shortAccount", 0.5)) * 100
            
            signal, signal_zh = self._analyze_ls_signal(long_short_ratio, long_account)
            
            result = LongShortRatioData(
                long_ratio=long_account,
                short_ratio=short_account,
                long_short_ratio=long_short_ratio,
                signal=signal,
                signal_zh=signal_zh,
            )
            
            self.data_source = "binance"
            logger.info(f"[Binance] 多空比: {long_short_ratio:.2f} (多:{long_account:.1f}% / 空:{short_account:.1f}%)")
            return result
            
        except Exception as e:
            logger.error(f"Binance 多空比資料解析失敗: {e}")
            return None
    
    def _parse_coinglass_ls(self, data) -> Optional[LongShortRatioData]:
        """解析 Coinglass 多空比數據"""
        try:
            if isinstance(data, list) and len(data) > 0:
                ls_data = data[0]
            else:
                ls_data = data
            
            long_ratio = float(ls_data.get("longRate", 50))
            short_ratio = float(ls_data.get("shortRate", 50))
            
            if short_ratio > 0:
                long_short_ratio = long_ratio / short_ratio
            else:
                long_short_ratio = long_ratio if long_ratio > 0 else 1.0
            
            signal, signal_zh = self._analyze_ls_signal(long_short_ratio, long_ratio)
            
            result = LongShortRatioData(
                long_ratio=long_ratio,
                short_ratio=short_ratio,
                long_short_ratio=long_short_ratio,
                signal=signal,
                signal_zh=signal_zh,
            )
            
            self.data_source = "coinglass"
            logger.info(f"[Coinglass] 多空比: {long_short_ratio:.2f} (多:{long_ratio:.1f}% / 空:{short_ratio:.1f}%)")
            return result
            
        except Exception as e:
            logger.error(f"Coinglass 多空比資料解析失敗: {e}")
            return None
    
    def _analyze_ls_signal(self, ratio: float, long_pct: float) -> tuple[str, str]:
        """分析多空比訊號"""
        if ratio > self.EXTREME_LONG_RATIO:
            return "extreme_long", f"🔴 極端做多警告！多空比達 {ratio:.2f}，多頭佔比 {long_pct:.1f}%。市場過度樂觀，極易發生「多頭清算」(Long Squeeze)。歷史數據顯示，極端多空比後往往伴隨快速回調，建議謹慎追高並設好止損。"
        elif ratio < self.EXTREME_SHORT_RATIO:
            return "extreme_short", f"🟢 極端做空！多空比僅 {ratio:.2f}，空頭佔比達 {100-long_pct:.1f}%。市場過度悲觀，容易發生「軋空」(Short Squeeze)。逆向思維下可能是抄底機會，但需等待反轉訊號確認。"
        elif ratio > 1.5:
            return "long_bias", f"📈 多頭優勢，多空比 {ratio:.2f}。市場偏向樂觀，多數交易者看漲。但需注意若價格未能突破，可能引發多頭止損。"
        elif ratio < 0.67:
            return "short_bias", f"📉 空頭優勢，多空比 {ratio:.2f}。市場偏向悲觀，多數交易者看跌。但過度做空可能累積軋空能量。"
        else:
            return "neutral", f"⚖️ 多空均衡，多空比 {ratio:.2f}。市場分歧不大，方向尚不明朗，建議等待突破方向確認。"
    
    def get_exchange_flow(self, symbol: str = "BTC") -> Optional[ExchangeFlowData]:
        """
        獲取交易所淨流入/流出
        
        這是最重要的籌碼指標：
        - 流入交易所 = 準備賣出 (利空)
        - 流出交易所 = 長期持有 HODL (利多)
        
        注意：交易所流量數據需要 Coinglass 付費 API
        Binance 公開 API 不提供此數據
        """
        logger.info(f"正在獲取 {symbol} 交易所流量...")
        
        # 只有 Coinglass 提供此數據
        if self.api_key:
            data = self._make_coinglass_request("/exchange_flow", {"symbol": symbol, "interval": "24h"})
            if data:
                return self._parse_coinglass_flow(data)
            
            # 備用端點
            data = self._make_coinglass_request("/exchange_balance", {"symbol": symbol})
            if data:
                return self._parse_coinglass_flow(data)
        
        # Binance 不提供交易所流量數據
        # 返回一個說明訊息
        logger.info("交易所流量數據需要 Coinglass 付費 API，已跳過此指標")
        return None
    
    def _parse_coinglass_flow(self, data) -> Optional[ExchangeFlowData]:
        """解析 Coinglass 交易所流量數據"""
        try:
            if isinstance(data, list) and len(data) > 0:
                flow_data = data[0]
            else:
                flow_data = data
            
            inflow = float(flow_data.get("inflow", 0))
            outflow = float(flow_data.get("outflow", 0))
            net_flow = float(flow_data.get("netflow", inflow - outflow))
            net_flow_btc = float(flow_data.get("netflowBtc", 0))
            
            signal, signal_zh = self._analyze_flow_signal(net_flow, net_flow_btc)
            
            result = ExchangeFlowData(
                net_flow_usd=net_flow,
                inflow_usd=inflow,
                outflow_usd=outflow,
                net_flow_btc=net_flow_btc,
                signal=signal,
                signal_zh=signal_zh,
            )
            
            self.data_source = "coinglass"
            flow_type = "流入" if net_flow > 0 else "流出"
            logger.info(f"[Coinglass] 交易所流量: 淨{flow_type} ${abs(net_flow):,.0f}")
            return result
            
        except Exception as e:
            logger.error(f"Coinglass 交易所流量資料解析失敗: {e}")
            return None
    
    def _analyze_flow_signal(self, net_flow_usd: float, net_flow_btc: float) -> tuple[str, str]:
        """分析交易所流量訊號"""
        abs_flow = abs(net_flow_usd)
        
        if net_flow_usd > self.SIGNIFICANT_FLOW_USD:
            return "selling_pressure", f"📉 大量 BTC 流入交易所！淨流入 ${net_flow_usd:,.0f} ({net_flow_btc:+.2f} BTC)。這通常代表大戶準備賣出，賣壓增加，短期可能面臨價格壓力。建議謹慎操作，關注支撐位。"
        elif net_flow_usd < -self.SIGNIFICANT_FLOW_USD:
            return "accumulation", f"📈 大量 BTC 流出交易所！淨流出 ${abs_flow:,.0f} ({net_flow_btc:+.2f} BTC)。籌碼正被轉移到冷錢包長期持有 (HODL)，這是典型的累積訊號，市場賣壓減少，中長期看好。"
        elif net_flow_usd > self.SIGNIFICANT_FLOW_USD * 0.3:
            return "mild_selling", f"⚠️ 中等規模流入交易所 ${net_flow_usd:,.0f}。賣壓略增，但尚未達到警戒水準，需持續觀察後續流量變化。"
        elif net_flow_usd < -self.SIGNIFICANT_FLOW_USD * 0.3:
            return "mild_accumulation", f"📊 中等規模流出交易所 ${abs_flow:,.0f}。籌碼逐漸被鎖定，顯示市場信心良好，但累積力度尚溫和。"
        else:
            return "neutral", f"⚖️ 交易所流量平穩，淨變化 ${net_flow_usd:+,.0f}。大戶無明顯動作，市場籌碼分佈穩定。"
    
    def collect_all(self, symbol: str = "BTC") -> Optional[DerivativesData]:
        """
        採集所有籌碼面指標
        
        即使部分指標獲取失敗，仍返回已成功獲取的數據
        
        Args:
            symbol: 幣種符號
            
        Returns:
            DerivativesData: 籌碼面指標資料，全部失敗時返回 None
        """
        from datetime import datetime
        
        logger.info("=" * 50)
        logger.info(f"開始採集 {symbol} 籌碼面指標...")
        logger.info("=" * 50)
        
        # 採集各項指標 (即使失敗也繼續)
        open_interest = self.get_open_interest(symbol)
        long_short_ratio = self.get_long_short_ratio(symbol)
        exchange_flow = self.get_exchange_flow(symbol)
        
        # 建立結果
        result = DerivativesData(
            open_interest=open_interest,
            long_short_ratio=long_short_ratio,
            exchange_flow=exchange_flow,
            collected_at=datetime.now().isoformat(),
        )
        
        # 記錄結果
        success_count = sum([
            open_interest is not None,
            long_short_ratio is not None,
            exchange_flow is not None,
        ])
        
        if success_count == 0:
            logger.warning("籌碼面指標採集全部失敗")
            return None
        
        logger.info("=" * 50)
        logger.info(f"籌碼面指標採集完成: {success_count}/3 項成功")
        logger.info("=" * 50)
        
        return result


if __name__ == "__main__":
    # 測試用
    import os
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    api_key = os.getenv("COINGLASS_API_KEY")
    client = CoinglassClient(api_key=api_key)
    
    result = client.collect_all()
    if result:
        print("\n籌碼面指標 JSON:")
        import json
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
