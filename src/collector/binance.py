"""
Binance API 客戶端 - 抓取 BTC K 線數據 (OHLCV) 和期貨籌碼面數據

API 文件: 
- Spot: https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data
- Futures: https://binance-docs.github.io/apidocs/futures/en/

使用 data-api.binance.vision 端點（現貨）和 fapi.binance.com 端點（期貨）
Rate Limit: 6000 weight/分鐘
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class OHLCData:
    """K 線數據結構 (OHLCV)"""

    timestamp: int  # 開盤時間 (毫秒)
    open: float  # 開盤價
    high: float  # 最高價
    low: float  # 最低價
    close: float  # 收盤價
    volume: float  # 成交量 (BTC)
    close_time: int  # 收盤時間 (毫秒)
    quote_volume: float  # 成交額 (USDT)
    trades: int  # 成交筆數

    @property
    def datetime(self) -> datetime:
        """轉換為 datetime 物件"""
        return datetime.fromtimestamp(self.timestamp / 1000)

    @property
    def date_str(self) -> str:
        """轉換為日期字串 (YYYY-MM-DD)"""
        return self.datetime.strftime("%Y-%m-%d")

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "datetime": self.datetime.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "trades": self.trades,
        }


@dataclass
class FuturesDerivativesData:
    """期貨籌碼面數據"""
    
    # 未平倉合約
    open_interest: float  # OI (BTC)
    open_interest_usd: float  # OI (USDT)
    
    # 資金費率
    funding_rate: float  # 當前資金費率
    funding_rate_pct: float  # 資金費率百分比
    next_funding_time: Optional[datetime] = None  # 下次結算時間
    
    # 多空比 (Top Traders)
    long_short_ratio: float = 1.0  # 多空比
    long_account_pct: float = 50.0  # 多頭帳戶比例
    short_account_pct: float = 50.0  # 空頭帳戶比例
    
    # 買賣盤比 (Taker Buy/Sell)
    taker_buy_volume: float = 0.0  # 主動買入量
    taker_sell_volume: float = 0.0  # 主動賣出量
    taker_buy_sell_ratio: float = 1.0  # 買賣比
    
    # 訊號
    signal: str = "neutral"  # bullish, bearish, neutral
    signal_zh: str = "中性"
    
    def to_dict(self) -> dict:
        return {
            "open_interest": {
                "value_btc": self.open_interest,
                "value_usd": self.open_interest_usd,
            },
            "funding_rate": {
                "rate": self.funding_rate,
                "rate_pct": self.funding_rate_pct,
                "next_funding_time": self.next_funding_time.isoformat() if self.next_funding_time else None,
            },
            "long_short_ratio": {
                "ratio": self.long_short_ratio,
                "long_pct": self.long_account_pct,
                "short_pct": self.short_account_pct,
            },
            "taker_volume": {
                "buy_volume": self.taker_buy_volume,
                "sell_volume": self.taker_sell_volume,
                "buy_sell_ratio": self.taker_buy_sell_ratio,
            },
            "signal": self.signal,
            "signal_zh": self.signal_zh,
        }


class BinanceClient:
    """
    Binance API 客戶端 - 專注於 K 線數據抓取

    使用方式:
        client = BinanceClient()
        daily_klines = client.get_klines(interval="1d", limit=200)
        hourly_klines = client.get_klines(interval="4h", limit=100)
    """

    # 使用純市場數據端點，無需認證
    BASE_URL = "https://data-api.binance.vision/api/v3"
    TIMEOUT = 30

    # Rate limit 控制
    MIN_REQUEST_INTERVAL = 0.5  # 最少間隔 0.5 秒

    # 支援的時間週期
    VALID_INTERVALS = [
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M",
    ]

    def __init__(self, symbol: str = "BTCUSDT"):
        """
        初始化 Binance 客戶端

        Args:
            symbol: 交易對符號 (預設 BTCUSDT)
        """
        self.symbol = symbol
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "CoinPilot-AI/0.1.0",
            }
        )
        self._last_request_time = 0

    def _rate_limit(self):
        """Rate limit 控制，確保請求間隔"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            sleep_time = self.MIN_REQUEST_INTERVAL - elapsed
            logger.debug(f"Rate limit: 等待 {sleep_time:.2f} 秒")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def get_klines(
        self,
        interval: str = "1d",
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[OHLCData]:
        """
        獲取 K 線數據

        Args:
            interval: 時間週期 (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
            limit: 數量限制 (最大 1000)
            start_time: 開始時間 (毫秒時間戳)
            end_time: 結束時間 (毫秒時間戳)

        Returns:
            list[OHLCData]: K 線數據列表

        Raises:
            ValueError: 無效的時間週期
            requests.RequestException: API 請求失敗
        """
        if interval not in self.VALID_INTERVALS:
            raise ValueError(
                f"無效的時間週期: {interval}，支援: {self.VALID_INTERVALS}"
            )

        self._rate_limit()

        endpoint = f"{self.BASE_URL}/klines"
        params = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }

        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        logger.info(
            f"正在從 Binance 獲取 {self.symbol} {interval} K 線數據 (limit={limit})..."
        )

        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()

            klines = []
            for item in data:
                kline = OHLCData(
                    timestamp=item[0],
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    close_time=item[6],
                    quote_volume=float(item[7]),
                    trades=item[8],
                )
                klines.append(kline)

            logger.info(f"成功獲取 {len(klines)} 根 K 線")
            return klines

        except requests.RequestException as e:
            logger.error(f"Binance API 請求失敗: {e}")
            raise

    def get_daily_klines(self, days: int = 365) -> list[OHLCData]:
        """
        獲取日線數據

        Args:
            days: 天數 (最大 1000)

        Returns:
            list[OHLCData]: 日線數據列表
        """
        return self.get_klines(interval="1d", limit=days)

    def get_4h_klines(self, days: int = 90) -> list[OHLCData]:
        """
        獲取 4 小時線數據

        Args:
            days: 天數 (每天 6 根，最大 166 天)

        Returns:
            list[OHLCData]: 4H 線數據列表
        """
        # 每天 6 根 4H K 線
        limit = min(days * 6, 1000)
        return self.get_klines(interval="4h", limit=limit)

    def get_historical_klines(
        self,
        interval: str = "1d",
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> list[OHLCData]:
        """
        獲取指定日期範圍的歷史 K 線數據

        會自動分批請求以繞過 1000 根限制

        Args:
            interval: 時間週期
            start_date: 開始日期
            end_date: 結束日期 (預設為今天)

        Returns:
            list[OHLCData]: K 線數據列表
        """
        if end_date is None:
            end_date = datetime.now()

        if start_date is None:
            # 預設取 365 天
            start_date = end_date - timedelta(days=365)

        start_time = int(start_date.timestamp() * 1000)
        end_time = int(end_date.timestamp() * 1000)

        all_klines = []
        current_start = start_time

        logger.info(
            f"正在獲取 {start_date.date()} 到 {end_date.date()} 的 {interval} K 線..."
        )

        while current_start < end_time:
            klines = self.get_klines(
                interval=interval,
                limit=1000,
                start_time=current_start,
                end_time=end_time,
            )

            if not klines:
                break

            all_klines.extend(klines)

            # 更新下一批的起始時間
            current_start = klines[-1].close_time + 1

            # 如果本批次少於 1000 根，代表已取完
            if len(klines) < 1000:
                break

        logger.info(f"共獲取 {len(all_klines)} 根 {interval} K 線")
        return all_klines

    def get_current_price(self) -> float:
        """
        獲取當前價格 (ticker)

        Returns:
            float: 當前價格
        """
        self._rate_limit()

        endpoint = f"{self.BASE_URL}/ticker/price"
        params = {"symbol": self.symbol}

        response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
        response.raise_for_status()
        data = response.json()

        return float(data["price"])

    # =========================================================================
    # 期貨籌碼面數據 (Futures Derivatives)
    # =========================================================================
    
    FUTURES_BASE_URL = "https://fapi.binance.com"
    
    def get_open_interest(self) -> dict:
        """
        獲取未平倉合約量 (Open Interest)
        
        Returns:
            dict: {open_interest: float, open_interest_usd: float}
        """
        self._rate_limit()
        
        endpoint = f"{self.FUTURES_BASE_URL}/fapi/v1/openInterest"
        params = {"symbol": self.symbol}
        
        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            oi = float(data.get("openInterest", 0))
            
            # 獲取當前價格來計算 USD 值
            price = self.get_current_price()
            oi_usd = oi * price
            
            logger.info(f"BTC 未平倉合約: {oi:,.2f} BTC (${oi_usd:,.0f})")
            
            return {
                "open_interest": oi,
                "open_interest_usd": oi_usd,
            }
        except Exception as e:
            logger.warning(f"獲取未平倉合約失敗: {e}")
            return {"open_interest": 0, "open_interest_usd": 0}
    
    def get_funding_rate(self) -> dict:
        """
        獲取資金費率 (Funding Rate)
        
        Returns:
            dict: {funding_rate: float, funding_rate_pct: float, next_funding_time: datetime}
        """
        self._rate_limit()
        
        endpoint = f"{self.FUTURES_BASE_URL}/fapi/v1/premiumIndex"
        params = {"symbol": self.symbol}
        
        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            funding_rate = float(data.get("lastFundingRate", 0))
            next_funding_time_ms = data.get("nextFundingTime", 0)
            next_funding_time = datetime.fromtimestamp(next_funding_time_ms / 1000) if next_funding_time_ms else None
            
            funding_rate_pct = funding_rate * 100
            
            logger.info(f"BTC 資金費率: {funding_rate_pct:+.4f}%")
            
            return {
                "funding_rate": funding_rate,
                "funding_rate_pct": funding_rate_pct,
                "next_funding_time": next_funding_time,
            }
        except Exception as e:
            logger.warning(f"獲取資金費率失敗: {e}")
            return {"funding_rate": 0, "funding_rate_pct": 0, "next_funding_time": None}
    
    def get_long_short_ratio(self) -> dict:
        """
        獲取多空比 (Top Trader Long/Short Ratio - Accounts)
        
        Returns:
            dict: {long_short_ratio: float, long_pct: float, short_pct: float}
        """
        self._rate_limit()
        
        endpoint = f"{self.FUTURES_BASE_URL}/futures/data/topLongShortAccountRatio"
        params = {
            "symbol": self.symbol,
            "period": "5m",  # 5分鐘, 15分鐘, 30分鐘, 1小時, 2小時, 4小時, 6小時, 12小時, 1天
            "limit": 1,
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            if data and len(data) > 0:
                latest = data[0]
                long_short_ratio = float(latest.get("longShortRatio", 1))
                long_account = float(latest.get("longAccount", 0.5))
                short_account = float(latest.get("shortAccount", 0.5))
                
                long_pct = long_account * 100
                short_pct = short_account * 100
                
                logger.info(f"BTC 多空比: {long_short_ratio:.2f} (多:{long_pct:.1f}% 空:{short_pct:.1f}%)")
                
                return {
                    "long_short_ratio": long_short_ratio,
                    "long_pct": long_pct,
                    "short_pct": short_pct,
                }
            
            return {"long_short_ratio": 1, "long_pct": 50, "short_pct": 50}
            
        except Exception as e:
            logger.warning(f"獲取多空比失敗: {e}")
            return {"long_short_ratio": 1, "long_pct": 50, "short_pct": 50}
    
    def get_taker_volume(self) -> dict:
        """
        獲取主動買賣量 (Taker Buy/Sell Volume)
        
        Returns:
            dict: {buy_volume: float, sell_volume: float, buy_sell_ratio: float}
        """
        self._rate_limit()
        
        endpoint = f"{self.FUTURES_BASE_URL}/futures/data/takerlongshortRatio"
        params = {
            "symbol": self.symbol,
            "period": "5m",
            "limit": 1,
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            if data and len(data) > 0:
                latest = data[0]
                buy_sell_ratio = float(latest.get("buySellRatio", 1))
                buy_vol = float(latest.get("buyVol", 0))
                sell_vol = float(latest.get("sellVol", 0))
                
                logger.info(f"BTC 買賣比: {buy_sell_ratio:.2f}")
                
                return {
                    "buy_volume": buy_vol,
                    "sell_volume": sell_vol,
                    "buy_sell_ratio": buy_sell_ratio,
                }
            
            return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 1}
            
        except Exception as e:
            logger.warning(f"獲取買賣量失敗: {e}")
            return {"buy_volume": 0, "sell_volume": 0, "buy_sell_ratio": 1}
    
    def get_derivatives_data(self) -> FuturesDerivativesData:
        """
        獲取完整的期貨籌碼面數據
        
        Returns:
            FuturesDerivativesData: 籌碼面數據結構
        """
        logger.info("正在從 Binance Futures 獲取籌碼面數據...")
        
        # 獲取各項數據
        oi_data = self.get_open_interest()
        funding_data = self.get_funding_rate()
        ls_data = self.get_long_short_ratio()
        taker_data = self.get_taker_volume()
        
        # 分析訊號
        signal, signal_zh = self._analyze_derivatives_signal(
            funding_data.get("funding_rate_pct", 0),
            ls_data.get("long_short_ratio", 1),
            taker_data.get("buy_sell_ratio", 1),
        )
        
        return FuturesDerivativesData(
            open_interest=oi_data.get("open_interest", 0),
            open_interest_usd=oi_data.get("open_interest_usd", 0),
            funding_rate=funding_data.get("funding_rate", 0),
            funding_rate_pct=funding_data.get("funding_rate_pct", 0),
            next_funding_time=funding_data.get("next_funding_time"),
            long_short_ratio=ls_data.get("long_short_ratio", 1),
            long_account_pct=ls_data.get("long_pct", 50),
            short_account_pct=ls_data.get("short_pct", 50),
            taker_buy_volume=taker_data.get("buy_volume", 0),
            taker_sell_volume=taker_data.get("sell_volume", 0),
            taker_buy_sell_ratio=taker_data.get("buy_sell_ratio", 1),
            signal=signal,
            signal_zh=signal_zh,
        )
    
    def _analyze_derivatives_signal(
        self,
        funding_rate_pct: float,
        long_short_ratio: float,
        buy_sell_ratio: float,
    ) -> tuple[str, str]:
        """
        分析籌碼面訊號
        
        Args:
            funding_rate_pct: 資金費率百分比
            long_short_ratio: 多空比
            buy_sell_ratio: 買賣比
            
        Returns:
            (signal, signal_zh): 訊號和中文描述
        """
        bullish_signals = 0
        bearish_signals = 0
        
        # 資金費率分析
        # 正費率 = 多頭付空頭 = 市場偏多
        # 極端正費率 (>0.1%) = 過熱，可能反轉
        # 負費率 = 空頭付多頭 = 市場偏空
        if funding_rate_pct > 0.1:
            bearish_signals += 1  # 過熱警告
        elif funding_rate_pct > 0.03:
            bullish_signals += 1  # 正常偏多
        elif funding_rate_pct < -0.03:
            bullish_signals += 1  # 空頭擁擠，可能反彈
        elif funding_rate_pct < 0:
            bearish_signals += 1  # 偏空
        
        # 多空比分析
        # >1.5 = 多頭擁擠，小心回調
        # <0.7 = 空頭擁擠，可能反彈
        if long_short_ratio > 1.5:
            bearish_signals += 1
        elif long_short_ratio < 0.7:
            bullish_signals += 1
        elif long_short_ratio > 1.1:
            bullish_signals += 1
        elif long_short_ratio < 0.9:
            bearish_signals += 1
        
        # 買賣比分析
        if buy_sell_ratio > 1.2:
            bullish_signals += 1
        elif buy_sell_ratio < 0.8:
            bearish_signals += 1
        
        # 綜合判斷
        if bullish_signals > bearish_signals + 1:
            return "bullish", "📈 籌碼面偏多"
        elif bearish_signals > bullish_signals + 1:
            return "bearish", "📉 籌碼面偏空"
        else:
            return "neutral", "⚖️ 籌碼面中性"
