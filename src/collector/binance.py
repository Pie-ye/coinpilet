"""
Binance API 客戶端 - 抓取 BTC K 線數據 (OHLCV)
API 文件: https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data

使用 data-api.binance.vision 端點，無需 API Key
Rate Limit: 6000 weight/分鐘，K 線請求 weight = 2
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
