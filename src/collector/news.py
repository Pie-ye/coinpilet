"""
新聞採集客戶端 - 從 Google News RSS 抓取比特幣相關新聞
"""

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import feedparser
import requests

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """新聞項目資料結構"""

    title: str  # 新聞標題
    link: str  # 新聞連結
    source: str  # 來源媒體
    published: str  # 發布時間
    summary: Optional[str] = None  # 摘要 (如有)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "published": self.published,
            "summary": self.summary,
        }


class NewsClient:
    """Google News RSS 新聞採集客戶端"""

    # Google News RSS 搜尋 URL
    GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
    TIMEOUT = 30

    def __init__(self, language: str = "en", country: str = "US"):
        """
        初始化新聞客戶端

        Args:
            language: 語言代碼 (en, zh-TW, etc.)
            country: 國家代碼 (US, TW, etc.)
        """
        self.language = language
        self.country = country
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "CoinPilot-AI/0.1.0",
            }
        )

    def _clean_title(self, title: str) -> str:
        """清理新聞標題中的 HTML 實體和多餘空白"""
        # 解碼 HTML 實體
        title = html.unescape(title)
        # 移除多餘空白
        title = re.sub(r"\s+", " ", title).strip()
        return title

    def _extract_source(self, title: str) -> tuple[str, str]:
        """
        從標題中提取來源媒體
        Google News 格式: "新聞標題 - 來源媒體"
        """
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            return self._clean_title(parts[0]), parts[1].strip()
        return self._clean_title(title), "Unknown"

    def _parse_date(self, date_str: str) -> str:
        """解析 RSS 日期格式並轉換為 ISO 格式"""
        try:
            # feedparser 已經解析過的時間結構
            if hasattr(date_str, "tm_year"):
                return datetime(*date_str[:6]).isoformat()
            # RFC 2822 格式
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(date_str)
            return dt.isoformat()
        except Exception:
            return datetime.now().isoformat()

    def get_bitcoin_news(self, limit: int = 3) -> list[NewsItem]:
        """
        獲取比特幣相關新聞

        Args:
            limit: 返回的新聞數量

        Returns:
            list[NewsItem]: 新聞列表

        Raises:
            requests.RequestException: RSS 請求失敗
        """
        # 建構搜尋查詢
        query = "Bitcoin OR BTC cryptocurrency"
        params = {
            "q": query,
            "hl": self.language,
            "gl": self.country,
            "ceid": f"{self.country}:{self.language}",
        }

        url = f"{self.GOOGLE_NEWS_RSS}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

        logger.info(f"正在從 Google News 獲取比特幣新聞 (限制: {limit} 則)...")

        try:
            response = self.session.get(url, timeout=self.TIMEOUT)
            response.raise_for_status()

            # 使用 feedparser 解析 RSS
            feed = feedparser.parse(response.content)

            if feed.bozo and not feed.entries:
                raise ValueError(f"RSS 解析失敗: {feed.bozo_exception}")

            news_items = []
            for entry in feed.entries[:limit]:
                title, source = self._extract_source(entry.get("title", ""))

                # 解析發布時間
                published = entry.get("published_parsed") or entry.get("published", "")
                if hasattr(published, "tm_year"):
                    published = datetime(*published[:6]).isoformat()
                elif isinstance(published, str) and published:
                    published = self._parse_date(published)
                else:
                    published = datetime.now().isoformat()

                news_item = NewsItem(
                    title=title,
                    link=entry.get("link", ""),
                    source=source,
                    published=published,
                    summary=entry.get("summary", None),
                )
                news_items.append(news_item)

            logger.info(f"成功獲取 {len(news_items)} 則新聞")
            for i, item in enumerate(news_items, 1):
                logger.debug(f"  {i}. {item.title[:50]}... ({item.source})")

            return news_items

        except requests.RequestException as e:
            logger.error(f"Google News RSS 請求失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"新聞解析失敗: {e}")
            raise

    def get_crypto_news(self, keywords: list[str] = None, limit: int = 3) -> list[NewsItem]:
        """
        獲取自訂關鍵字的加密貨幣新聞

        Args:
            keywords: 搜尋關鍵字列表
            limit: 返回的新聞數量

        Returns:
            list[NewsItem]: 新聞列表
        """
        if keywords is None:
            keywords = ["Bitcoin", "BTC", "cryptocurrency"]

        query = " OR ".join(keywords)
        params = {
            "q": query,
            "hl": self.language,
            "gl": self.country,
            "ceid": f"{self.country}:{self.language}",
        }

        url = f"{self.GOOGLE_NEWS_RSS}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

        try:
            response = self.session.get(url, timeout=self.TIMEOUT)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            news_items = []
            for entry in feed.entries[:limit]:
                title, source = self._extract_source(entry.get("title", ""))
                published = entry.get("published_parsed")
                if hasattr(published, "tm_year"):
                    published = datetime(*published[:6]).isoformat()
                else:
                    published = datetime.now().isoformat()

                news_items.append(
                    NewsItem(
                        title=title,
                        link=entry.get("link", ""),
                        source=source,
                        published=published,
                    )
                )

            return news_items

        except Exception as e:
            logger.error(f"新聞獲取失敗: {e}")
            raise


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(level=logging.INFO)
    client = NewsClient()
    news = client.get_bitcoin_news(limit=3)
    for item in news:
        print(f"- {item.title}")
        print(f"  來源: {item.source}")
        print(f"  連結: {item.link}")
        print()
