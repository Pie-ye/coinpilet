"""
採集器整合模組 - 整合所有資料來源並輸出標準化 JSON
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .binance import BinanceClient, OHLCData
from .cache import OHLCCache
from .coingecko import BTCPriceData, CoinGeckoClient, GlobalMarketData
from .fear_greed import FearGreedClient, FearGreedData
from .news import NewsClient, NewsItem
from .technical import TechnicalAnalyzer, TechnicalIndicators

logger = logging.getLogger(__name__)


@dataclass
class DailyContext:
    """每日市場資料完整上下文"""

    collected_at: str  # 資料採集時間
    price: dict  # BTC 價格資料
    sentiment: dict  # 恐慌貪婪指數
    news: list[dict]  # 新聞列表
    technical: dict = field(default_factory=dict)  # 技術指標
    market_structure: dict = field(default_factory=dict)  # 市場結構 (BTC Dominance 等)
    metadata: dict = field(default_factory=dict)  # 元資料

    def to_dict(self) -> dict:
        return {
            "collected_at": self.collected_at,
            "price": self.price,
            "sentiment": self.sentiment,
            "news": self.news,
            "technical": self.technical,
            "market_structure": self.market_structure,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class Collector:
    """
    資料採集器 - 整合 CoinGecko、Fear & Greed Index、Google News、Binance K線、技術指標

    使用方式:
        collector = Collector()
        context = collector.collect_all()
        collector.save_to_file(context, "data/daily_context.json")
    """

    def __init__(
        self,
        coingecko_api_key: Optional[str] = None,
        news_language: str = "en",
        news_country: str = "US",
        data_dir: str = "data",
    ):
        """
        初始化採集器

        Args:
            coingecko_api_key: CoinGecko Pro API Key (可選)
            news_language: 新聞語言
            news_country: 新聞國家
            data_dir: 資料目錄 (用於 K 線快取)
        """
        self.coingecko = CoinGeckoClient(api_key=coingecko_api_key)
        self.fear_greed = FearGreedClient()
        self.news = NewsClient(language=news_language, country=news_country)
        self.binance = BinanceClient()
        self.cache = OHLCCache(data_dir=data_dir)
        self.technical_analyzer = TechnicalAnalyzer()

    def collect_price(self) -> BTCPriceData:
        """採集 BTC 價格資料"""
        return self.coingecko.get_btc_price()

    def collect_sentiment(self) -> FearGreedData:
        """採集恐慌貪婪指數"""
        return self.fear_greed.get_current_index()

    def collect_news(self, limit: int = 3) -> list[NewsItem]:
        """採集新聞標題"""
        return self.news.get_bitcoin_news(limit=limit)

    def collect_global_market(self) -> GlobalMarketData:
        """採集全球市場數據 (BTC Dominance)"""
        return self.coingecko.get_global_data()

    def collect_klines(self, interval: str = "1d", use_cache: bool = True) -> list[dict]:
        """
        採集 K 線數據 (支援快取)

        Args:
            interval: K 線週期 (1d, 4h)
            use_cache: 是否使用快取

        Returns:
            list[dict]: K 線數據列表
        """
        if use_cache:
            # 檢查快取是否需要更新
            start_time = self.cache.get_update_start_time(interval)

            if start_time:
                # 增量更新
                logger.info(f"從快取增量更新 {interval} K 線...")
                new_klines = self.binance.get_klines(
                    interval=interval,
                    start_time=start_time,
                    limit=1000,
                )
                if new_klines:
                    new_klines_dict = [k.to_dict() for k in new_klines]
                    self.cache.save(interval, new_klines_dict, merge=True)
            else:
                # 完整抓取
                logger.info(f"初始化 {interval} K 線快取...")
                days = 365 if interval == "1d" else 90
                klines = self.binance.get_daily_klines(days) if interval == "1d" else self.binance.get_4h_klines(days)
                klines_dict = [k.to_dict() for k in klines]
                self.cache.save(interval, klines_dict, merge=False)

            return self.cache.get_cached_klines(interval)
        else:
            # 不使用快取，直接抓取
            days = 365 if interval == "1d" else 90
            klines = self.binance.get_daily_klines(days) if interval == "1d" else self.binance.get_4h_klines(days)
            return [k.to_dict() for k in klines]

    def collect_technical(self, klines: list[dict] = None) -> TechnicalIndicators:
        """
        採集技術指標

        Args:
            klines: K 線數據 (可選，不提供則自動採集)

        Returns:
            TechnicalIndicators: 技術指標集合
        """
        if klines is None:
            klines = self.collect_klines(interval="1d", use_cache=True)

        return self.technical_analyzer.calculate(klines)

    def collect_all(self, news_limit: int = 3) -> DailyContext:
        """
        採集所有資料來源

        Args:
            news_limit: 新聞數量限制

        Returns:
            DailyContext: 完整的每日市場上下文

        Raises:
            Exception: 任一資料來源採集失敗時拋出
        """
        logger.info("=" * 50)
        logger.info("開始採集每日市場資料...")
        logger.info("=" * 50)

        errors = []

        # 採集價格資料
        price_data = None
        try:
            price_data = self.collect_price()
        except Exception as e:
            logger.error(f"價格資料採集失敗: {e}")
            errors.append(f"price: {e}")

        # 採集情緒指數
        sentiment_data = None
        try:
            sentiment_data = self.collect_sentiment()
        except Exception as e:
            logger.error(f"情緒指數採集失敗: {e}")
            errors.append(f"sentiment: {e}")

        # 採集新聞
        news_data = []
        try:
            news_data = self.collect_news(limit=news_limit)
        except Exception as e:
            logger.error(f"新聞採集失敗: {e}")
            errors.append(f"news: {e}")

        # 採集 K 線數據並計算技術指標
        technical_data = None
        try:
            klines = self.collect_klines(interval="1d", use_cache=True)
            technical_data = self.collect_technical(klines)
        except Exception as e:
            logger.error(f"技術指標採集失敗: {e}")
            errors.append(f"technical: {e}")

        # 採集全球市場數據 (BTC Dominance)
        global_market_data = None
        try:
            global_market_data = self.collect_global_market()
        except Exception as e:
            logger.error(f"全球市場數據採集失敗: {e}")
            errors.append(f"market_structure: {e}")

        # 檢查是否有關鍵資料缺失
        if price_data is None or sentiment_data is None:
            raise RuntimeError(f"關鍵資料採集失敗: {errors}")

        # 組裝完整上下文
        context = DailyContext(
            collected_at=datetime.now().isoformat(),
            price=price_data.to_dict(),
            sentiment={
                **sentiment_data.to_dict(),
                "sentiment_zh": sentiment_data.sentiment_zh,
                "emoji": sentiment_data.sentiment_emoji,
            },
            news=[item.to_dict() for item in news_data],
            technical=technical_data.to_dict() if technical_data else {},
            market_structure=global_market_data.to_dict() if global_market_data else {},
            metadata={
                "version": "2.0.0",
                "sources": {
                    "price": "CoinGecko",
                    "sentiment": "Alternative.me",
                    "news": "Google News RSS",
                    "klines": "Binance",
                    "technical": "pandas-ta",
                    "market_structure": "CoinGecko Global",
                },
                "errors": errors if errors else None,
            },
        )

        logger.info("=" * 50)
        logger.info("資料採集完成！")
        logger.info(f"  價格: ${price_data.price_usd:,.2f}")
        logger.info(f"  情緒: {sentiment_data.sentiment_zh} ({sentiment_data.value})")
        logger.info(f"  新聞: {len(news_data)} 則")
        if technical_data:
            logger.info(f"  技術: {technical_data.overall_signal_zh}")
        if global_market_data:
            logger.info(f"  BTC.D: {global_market_data.btc_dominance:.1f}%")
        logger.info("=" * 50)

        return context

    def save_to_file(self, context: DailyContext, filepath: str | Path) -> Path:
        """
        將採集資料保存為 JSON 檔案

        Args:
            context: 每日市場上下文
            filepath: 輸出檔案路徑

        Returns:
            Path: 實際保存的檔案路徑
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(context.to_json())

        logger.info(f"資料已保存至: {filepath}")
        return filepath


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    collector = Collector()
    context = collector.collect_all()
    print("\n" + "=" * 50)
    print("完整 JSON 輸出:")
    print("=" * 50)
    print(context.to_json())
