"""
採集器整合模組 - 整合所有資料來源並輸出標準化 JSON
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .binance import BinanceClient, FuturesDerivativesData, OHLCData
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
    derivatives: Optional[dict] = None  # 籌碼面指標 (OI, 多空比, 交易所流量)
    metadata: dict = field(default_factory=dict)  # 元資料

    def to_dict(self) -> dict:
        return {
            "collected_at": self.collected_at,
            "price": self.price,
            "sentiment": self.sentiment,
            "news": self.news,
            "technical": self.technical,
            "market_structure": self.market_structure,
            "derivatives": self.derivatives,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class Collector:
    """
    資料採集器 - 整合 CoinGecko、Fear & Greed Index、Google News、Binance K線/期貨、技術指標

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

    def collect_news(self, limit: int = 3, fetch_content: bool = True) -> list[NewsItem]:
        """
        採集加密貨幣新聞 (包含文章內容)
        
        Args:
            limit: 每個新聞來源的新聞數量
            fetch_content: 是否爬取文章全文
        
        Returns:
            list[NewsItem]: 新聞列表
        """
        return self.news.get_crypto_news_from_sources(
            sources=["coindesk", "cointelegraph"],
            limit=limit,
            fetch_content=fetch_content,
        )

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

        # 採集籌碼面指標 (OI, 多空比, 資金費率) - 使用 Binance Futures
        derivatives_data = None
        try:
            derivatives_data = self.binance.get_derivatives_data()
        except Exception as e:
            logger.warning(f"籌碼面指標採集失敗 (非致命): {e}")
            errors.append(f"derivatives: {e}")

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
            derivatives=derivatives_data.to_dict() if derivatives_data else None,
            metadata={
                "version": "2.1.0",
                "sources": {
                    "price": "CoinGecko",
                    "sentiment": "Alternative.me",
                    "news": "Google News RSS",
                    "klines": "Binance",
                    "technical": "pandas-ta",
                    "market_structure": "CoinGecko Global",
                    "derivatives": "Binance Futures" if derivatives_data else None,
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
        if derivatives_data:
            logger.info(f"  籌碼: 已採集 (OI/多空比/交易所流量)")
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

    def collect_multi_day(
        self,
        days: int = 3,
        news_limit_per_day: int = 3,
        include_today: bool = True,
    ) -> list[DailyContext]:
        """
        採集多日市場資料（用於綜合投資報告）

        Args:
            days: 要採集的天數（包含今天）
            news_limit_per_day: 每天的新聞數量限制
            include_today: 是否包含今天的即時資料

        Returns:
            list[DailyContext]: 按日期排序的每日市場上下文列表（最舊到最新）
        """
        from datetime import date, timedelta
        
        logger.info("=" * 50)
        logger.info(f"開始採集過去 {days} 天的市場資料...")
        logger.info("=" * 50)
        
        contexts = []
        today = date.today()
        
        # 1. 首先採集今天的即時資料
        if include_today:
            try:
                logger.info(f"[1/{days}] 採集今日 ({today}) 即時資料...")
                today_context = self.collect_all(news_limit=news_limit_per_day)
                contexts.append((today, today_context))
            except Exception as e:
                logger.error(f"今日資料採集失敗: {e}")
        
        # 2. 從快取中提取歷史 K 線數據
        logger.info("載入歷史 K 線快取...")
        cached_klines = self.cache.get_cached_klines("1d")
        klines_by_date = {}
        for kline in cached_klines:
            # 支援兩種格式: 'datetime' (新格式) 或 'open_time' (舊格式)
            time_key = kline.get("datetime") or kline.get("open_time")
            if time_key:
                try:
                    kline_date = datetime.fromisoformat(time_key.replace("Z", "+00:00")).date()
                    klines_by_date[kline_date] = kline
                except Exception:
                    pass
        
        # 3. 採集歷史新聞
        historical_days = days - 1 if include_today else days
        today_news_as_fallback = []  # 如果歷史新聞不可用，使用今天的新聞作為替代
        
        if historical_days > 0:
            start_date = today - timedelta(days=historical_days)
            end_date = today - timedelta(days=1)
            
            logger.info(f"採集 {start_date} 至 {end_date} 的歷史新聞...")
            try:
                historical_news = self.news.get_historical_news_batch(
                    start_date=start_date,
                    end_date=end_date,
                    limit_per_day=news_limit_per_day,
                    delay_between_days=1.0,
                )
                
                # 檢查是否所有歷史日期都沒有新聞
                total_historical_news = sum(len(v) for v in historical_news.values())
                if total_historical_news == 0:
                    logger.warning("歷史新聞獲取為空，將使用今日新聞作為替代")
                    # 使用今天的新聞作為 fallback
                    if contexts and contexts[0][1].news:
                        today_news_as_fallback = contexts[0][1].news
                        logger.info(f"將使用 {len(today_news_as_fallback)} 則今日新聞作為歷史參考")
                    
            except Exception as e:
                logger.warning(f"歷史新聞採集失敗: {e}")
                historical_news = {}
            
            # 4. 為每個歷史日期組裝 DailyContext
            for i in range(historical_days, 0, -1):
                target_date = today - timedelta(days=i)
                date_str = target_date.strftime("%Y-%m-%d")
                
                logger.info(f"組裝 {date_str} 的市場上下文...")
                
                try:
                    # 從快取取得該日的 K 線數據
                    kline = klines_by_date.get(target_date)
                    if kline:
                        # 用 K 線數據構建價格資訊
                        price_data = {
                            "price_usd": kline["close"],
                            "change_24h": ((kline["close"] - kline["open"]) / kline["open"]) * 100 if kline["open"] > 0 else 0,
                            "volume_24h": kline["volume"],
                            "high_24h": kline["high"],
                            "low_24h": kline["low"],
                            "market_cap": 0,  # 歷史資料無法取得
                        }
                    else:
                        logger.warning(f"找不到 {date_str} 的 K 線資料")
                        price_data = {"price_usd": 0, "change_24h": 0}
                    
                    # 取得該日新聞 (如果沒有歷史新聞，使用今日新聞作為參考)
                    day_news = historical_news.get(date_str, [])
                    if day_news:
                        news_list = [item.to_dict() for item in day_news]
                    elif today_news_as_fallback:
                        # 使用今天的新聞但標記為參考
                        news_list = today_news_as_fallback.copy()
                        for n in news_list:
                            n["_note"] = "使用今日新聞作為歷史參考"
                    else:
                        news_list = []
                    
                    # 計算技術指標（使用到該日為止的 K 線）
                    def get_kline_date(k):
                        time_key = k.get("datetime") or k.get("open_time")
                        if time_key:
                            try:
                                return datetime.fromisoformat(time_key.replace("Z", "+00:00")).date()
                            except Exception:
                                return None
                        return None
                    
                    historical_klines = [
                        k for k in cached_klines 
                        if get_kline_date(k) is not None and get_kline_date(k) <= target_date
                    ]
                    technical_data = {}
                    if len(historical_klines) >= 50:
                        try:
                            indicators = self.technical_analyzer.calculate(historical_klines[-200:])
                            technical_data = indicators.to_dict()
                        except Exception as e:
                            logger.warning(f"技術指標計算失敗: {e}")
                    
                    # 組裝 DailyContext
                    historical_context = DailyContext(
                        collected_at=f"{date_str}T23:59:59",
                        price=price_data,
                        sentiment={"value": 50, "label": "Neutral", "sentiment_zh": "中性", "emoji": "😐"},  # 歷史情緒無法取得
                        news=news_list,
                        technical=technical_data,
                        market_structure={},
                        derivatives=None,
                        metadata={
                            "version": "2.1.0",
                            "type": "historical",
                            "date": date_str,
                        },
                    )
                    
                    contexts.append((target_date, historical_context))
                    
                except Exception as e:
                    logger.error(f"組裝 {date_str} 上下文失敗: {e}")
        
        # 5. 按日期排序（最舊到最新）
        contexts.sort(key=lambda x: x[0])
        result = [ctx for _, ctx in contexts]
        
        logger.info("=" * 50)
        logger.info(f"多日資料採集完成！共 {len(result)} 天")
        for target_date, ctx in contexts:
            price = ctx.price.get("price_usd", 0)
            news_count = len(ctx.news)
            logger.info(f"  {target_date}: ${price:,.2f} | {news_count} 則新聞")
        logger.info("=" * 50)
        
        return result


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
