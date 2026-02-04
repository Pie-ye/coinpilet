"""
新聞採集客戶端 - 從 Google News RSS 抓取比特幣相關新聞並爬取文章內容
"""

import html
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import feedparser
import requests

# 嘗試導入 newspaper3k，提供 fallback
try:
    from newspaper import Article, Config as ArticleConfig
    NEWSPAPER_AVAILABLE = True
except ImportError:
    NEWSPAPER_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """新聞項目資料結構"""

    title: str  # 新聞標題
    link: str  # 新聞連結
    source: str  # 來源媒體
    published: str  # 發布時間
    summary: Optional[str] = None  # RSS 摘要 (如有)
    content: Optional[str] = None  # 文章全文
    content_summary: Optional[str] = None  # 文章內容摘要 (前500字)
    keywords: list[str] = field(default_factory=list)  # 文章關鍵字
    fetch_error: Optional[str] = None  # 內容獲取錯誤訊息

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "published": self.published,
            "summary": self.summary,
            "content": self.content,
            "content_summary": self.content_summary,
            "keywords": self.keywords,
            "fetch_error": self.fetch_error,
        }
    
    def has_content(self) -> bool:
        """檢查是否有成功抓取文章內容"""
        return self.content is not None and len(self.content) > 100


class NewsClient:
    """加密貨幣新聞採集客戶端 - 支援多個新聞來源"""

    # 新聞來源 RSS URLs
    NEWS_SOURCES = {
        "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "cointelegraph": "https://cointelegraph.com/rss",
        "bitcoin_magazine": "https://bitcoinmagazine.com/feed",
        "decrypt": "https://decrypt.co/feed",
    }
    
    # Google News RSS (備用)
    GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
    TIMEOUT = 30
    
    # 新聞去重歷史天數
    DEDUP_HISTORY_DAYS = 7

    def __init__(self, language: str = "en", country: str = "US", history_file: str = "data/news_history.json"):
        """
        初始化新聞客戶端

        Args:
            language: 語言代碼 (en, zh-TW, etc.)
            country: 國家代碼 (US, TW, etc.)
            history_file: 新聞歷史記錄檔案路徑 (用於去重)
        """
        self.language = language
        self.country = country
        self.history_file = history_file
        self._news_history: set[str] = set()
        self._load_news_history()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )
    
    def _load_news_history(self):
        """載入新聞歷史記錄 (用於去重)"""
        from pathlib import Path
        import json
        from datetime import datetime, timedelta
        
        history_path = Path(self.history_file)
        if not history_path.exists():
            self._news_history = set()
            return
        
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 過濾掉超過 7 天的舊新聞
            cutoff_date = datetime.now() - timedelta(days=self.DEDUP_HISTORY_DAYS)
            valid_news = []
            for item in data.get("news", []):
                try:
                    news_date = datetime.fromisoformat(item.get("date", ""))
                    if news_date > cutoff_date:
                        valid_news.append(item)
                except (ValueError, TypeError):
                    pass
            
            self._news_history = {item.get("title_hash", "") for item in valid_news if item.get("title_hash")}
            logger.info(f"載入新聞歷史: {len(self._news_history)} 則 (最近 {self.DEDUP_HISTORY_DAYS} 天)")
            
        except Exception as e:
            logger.warning(f"載入新聞歷史失敗: {e}")
            self._news_history = set()
    
    def _save_news_history(self, new_titles: list[str]):
        """保存新聞歷史記錄"""
        from pathlib import Path
        import json
        import hashlib
        from datetime import datetime, timedelta
        
        history_path = Path(self.history_file)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 載入現有歷史
        existing_news = []
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                existing_news = data.get("news", [])
            except Exception:
                pass
        
        # 過濾掉過期的新聞
        cutoff_date = datetime.now() - timedelta(days=self.DEDUP_HISTORY_DAYS)
        valid_news = []
        for item in existing_news:
            try:
                news_date = datetime.fromisoformat(item.get("date", ""))
                if news_date > cutoff_date:
                    valid_news.append(item)
            except (ValueError, TypeError):
                pass
        
        # 添加新的新聞標題
        now = datetime.now().isoformat()
        for title in new_titles:
            title_hash = hashlib.md5(title.lower().encode()).hexdigest()
            if title_hash not in self._news_history:
                valid_news.append({
                    "title_hash": title_hash,
                    "title": title[:100],  # 只保留前 100 字元
                    "date": now,
                })
                self._news_history.add(title_hash)
        
        # 保存
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump({"news": valid_news, "updated_at": now}, f, ensure_ascii=False, indent=2)
            logger.debug(f"保存新聞歷史: {len(valid_news)} 則")
        except Exception as e:
            logger.warning(f"保存新聞歷史失敗: {e}")
    
    def _is_duplicate_news(self, title: str) -> bool:
        """檢查新聞是否重複"""
        import hashlib
        title_hash = hashlib.md5(title.lower().encode()).hexdigest()
        return title_hash in self._news_history

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

    def _decode_google_news_url(self, google_url: str) -> str:
        """
        解碼 Google News RSS 的 Base64 編碼 URL
        
        Google News 使用 protobuf + Base64 編碼
        格式: CBMi{length}{url}...
        """
        import base64
        
        try:
            # 從 URL 提取 Base64 部分
            if "/articles/" not in google_url:
                return None
                
            encoded_part = google_url.split("/articles/")[1].split("?")[0]
            
            # 嘗試不同的解碼方式
            # 方法1: 直接解碼整個部分
            try:
                # 補齊 padding
                padded = encoded_part + "=" * (4 - len(encoded_part) % 4)
                decoded = base64.urlsafe_b64decode(padded)
                
                # 從解碼結果中查找 URL
                decoded_str = decoded.decode("latin-1")  # 使用 latin-1 避免 UTF-8 錯誤
                
                # 查找所有 http(s) URL
                urls = re.findall(r'https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+', decoded_str)
                
                # 過濾掉無效 URL
                for url in urls:
                    # 清理尾部可能的亂碼
                    clean_url = url.rstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r')
                    # 移除尾部的非 URL 字元
                    clean_url = re.sub(r'[\x00-\x1f]+.*$', '', clean_url)
                    
                    if clean_url and len(clean_url) > 20 and "google.com" not in clean_url:
                        logger.debug(f"Base64 解碼成功: {clean_url[:60]}...")
                        return clean_url
                        
            except Exception as e:
                logger.debug(f"Base64 解碼嘗試失敗: {e}")
            
            # 方法2: 使用 requests 模擬瀏覽器訪問
            # Google News 某些情況下會直接重定向
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            
            response = requests.get(google_url, headers=headers, allow_redirects=True, timeout=10)
            if response.url != google_url and "google.com" not in response.url:
                logger.debug(f"重定向解析成功: {response.url[:60]}...")
                return response.url
                
            # 從返回的 HTML 中提取
            content = response.text
            
            # 嘗試從 script 中提取實際 URL
            # Google News 使用 c 參數傳遞實際 URL
            script_url_match = re.search(r'"(https?://[^"]+)"', content)
            if script_url_match:
                url = script_url_match.group(1)
                if "google.com" not in url and len(url) > 30:
                    return url
                    
        except Exception as e:
            logger.debug(f"URL 解碼失敗: {e}")
        
        return None

    def _resolve_google_news_url(self, google_url: str) -> str:
        """
        解析 Google News 重定向 URL，獲取真實文章連結
        
        Google News 的 URL 格式：
        https://news.google.com/rss/articles/CBMi...
        需要跟隨重定向獲取實際 URL
        """
        # 使用更真實的 User-Agent
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        try:
            # 使用 GET 請求來獲取重定向
            response = requests.get(
                google_url, 
                headers=headers,
                allow_redirects=True, 
                timeout=15
            )
            
            final_url = response.url
            
            # 如果還是 Google News URL，嘗試從 HTML 中提取實際連結
            if "news.google.com" in final_url:
                # 嘗試從 meta refresh 或 JavaScript 中提取 URL
                content = response.text
                
                # 尋找 meta refresh
                import re
                meta_match = re.search(r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\'][^"\']*url=([^"\'\s>]+)', content, re.IGNORECASE)
                if meta_match:
                    return meta_match.group(1)
                
                # 尋找 data-n-au 屬性（Google News 的實際 URL）
                au_match = re.search(r'data-n-au="([^"]+)"', content)
                if au_match:
                    return au_match.group(1)
                    
                # 嘗試從 window.location 提取
                loc_match = re.search(r'window\.location\s*=\s*["\']([^"\']+)["\']', content)
                if loc_match:
                    return loc_match.group(1)
            
            return final_url
            
        except Exception as e:
            logger.debug(f"URL 解析失敗: {e}")
            return google_url

    def fetch_article_content(self, url: str) -> tuple[str, str, list[str]]:
        """
        爬取文章全文內容
        
        Args:
            url: 文章 URL（可以是 Google News URL 或直接 URL）
        
        Returns:
            tuple: (文章全文, 摘要前500字, 關鍵字列表)
        """
        if not NEWSPAPER_AVAILABLE:
            logger.warning("newspaper3k 未安裝，無法爬取文章內容")
            return None, None, []
        
        try:
            # 解析 Google News URL
            if "news.google.com" in url:
                # 優先嘗試 Base64 解碼
                real_url = self._decode_google_news_url(url)
                if not real_url:
                    # 退回到重定向解析
                    real_url = self._resolve_google_news_url(url)
                logger.debug(f"解析 Google News URL -> {real_url[:80] if real_url else 'Failed'}...")
            else:
                real_url = url
            
            if not real_url or "news.google.com" in real_url:
                logger.warning(f"無法解析實際 URL: {url[:60]}...")
                return None, None, []
            
            # 配置 newspaper
            config = ArticleConfig()
            config.browser_user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            config.request_timeout = 15
            config.fetch_images = False  # 不下載圖片
            config.memoize_articles = False
            
            # 下載並解析文章
            article = Article(real_url, config=config)
            article.download()
            article.parse()
            
            # 獲取文章內容
            content = article.text
            if not content or len(content) < 50:
                logger.warning(f"文章內容過短或為空: {real_url[:50]}...")
                return None, None, []
            
            # 清理內容
            content = self._clean_article_content(content)
            
            # 生成摘要 (完整內容，供後續精煉總結使用)
            summary = content
            
            # 嘗試提取關鍵字
            try:
                article.nlp()
                keywords = article.keywords[:5]  # 最多5個關鍵字
            except Exception:
                keywords = []
            
            logger.info(f"成功爬取文章: {len(content)} 字元")
            return content, summary, keywords
            
        except Exception as e:
            logger.warning(f"爬取文章失敗 ({url[:50]}...): {e}")
            return None, None, []
    
    def _clean_article_content(self, content: str) -> str:
        """清理文章內容"""
        # 移除多餘空行
        content = re.sub(r"\n{3,}", "\n\n", content)
        # 移除行首行尾空白
        lines = [line.strip() for line in content.split("\n")]
        content = "\n".join(lines)
        # 移除可能的廣告文字
        ad_patterns = [
            r"Advertisement\s*",
            r"ADVERTISEMENT\s*",
            r"Sponsored\s+Content\s*",
            r"Click here to subscribe\s*",
            r"Sign up for our newsletter\s*",
        ]
        for pattern in ad_patterns:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)
        return content.strip()

    def get_crypto_news_from_sources(
        self, 
        sources: list[str] = None, 
        limit: int = 5, 
        fetch_content: bool = True,
        skip_duplicates: bool = True
    ) -> list[NewsItem]:
        """
        從專業加密貨幣新聞網站獲取新聞
        
        這個方法直接從 CoinDesk、CoinTelegraph 等網站的 RSS 獲取新聞，
        URL 可以直接訪問，不需要解析 Google News 的加密連結。
        
        Args:
            sources: 要使用的新聞來源列表，可選值: coindesk, cointelegraph, bitcoin_magazine, decrypt
            limit: 每個來源返回的新聞數量
            fetch_content: 是否爬取文章全文內容
            skip_duplicates: 是否跳過重複新聞 (比對最近 7 天歷史)
        
        Returns:
            list[NewsItem]: 新聞列表
        """
        if sources is None:
            sources = ["coindesk", "cointelegraph"]
        
        all_news = []
        new_titles = []
        skipped_count = 0
        
        for source_name in sources:
            rss_url = self.NEWS_SOURCES.get(source_name)
            if not rss_url:
                logger.warning(f"未知的新聞來源: {source_name}")
                continue
            
            logger.info(f"正在從 {source_name} 獲取新聞...")
            
            try:
                response = self.session.get(rss_url, timeout=self.TIMEOUT)
                response.raise_for_status()
                
                feed = feedparser.parse(response.content)
                
                if feed.bozo and not feed.entries:
                    logger.warning(f"{source_name} RSS 解析失敗")
                    continue
                
                added_count = 0
                for entry in feed.entries:
                    if added_count >= limit:
                        break
                    
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "")
                    
                    # 檢查是否為重複新聞
                    if skip_duplicates and self._is_duplicate_news(title):
                        logger.debug(f"    跳過重複新聞: {title[:40]}...")
                        skipped_count += 1
                        continue
                    
                    # 解析發布時間
                    published = entry.get("published_parsed") or entry.get("published", "")
                    if hasattr(published, "tm_year"):
                        published = datetime(*published[:6]).isoformat()
                    elif isinstance(published, str) and published:
                        published = self._parse_date(published)
                    else:
                        published = datetime.now().isoformat()
                    
                    # 獲取 RSS 中的摘要
                    summary = entry.get("summary", "") or entry.get("description", "")
                    # 清理 HTML 標籤
                    if summary:
                        summary = re.sub(r'<[^>]+>', '', summary).strip()[:500]
                    
                    news_item = NewsItem(
                        title=title,
                        link=link,
                        source=source_name.replace("_", " ").title(),
                        published=published,
                        summary=summary if summary else None,
                    )
                    all_news.append(news_item)
                    new_titles.append(title)
                    added_count += 1
                
                logger.info(f"  從 {source_name} 獲取 {added_count} 則新聞" + (f" (跳過 {skipped_count} 則重複)" if skipped_count > 0 else ""))
                
            except Exception as e:
                logger.warning(f"從 {source_name} 獲取新聞失敗: {e}")
                continue
        
        # 保存新聞歷史 (用於下次去重)
        if new_titles:
            self._save_news_history(new_titles)
        
        if skipped_count > 0:
            logger.info(f"共跳過 {skipped_count} 則重複新聞")
        
        # 按發布時間排序
        all_news.sort(key=lambda x: x.published, reverse=True)
        
        # 爬取文章內容
        if fetch_content and NEWSPAPER_AVAILABLE and all_news:
            logger.info(f"開始爬取 {len(all_news)} 篇新聞文章內容...")
            
            for i, item in enumerate(all_news):
                logger.info(f"  [{i+1}/{len(all_news)}] 爬取: {item.title[:40]}...")
                try:
                    content, summary, keywords = self.fetch_article_content(item.link)
                    item.content = content
                    item.content_summary = summary
                    item.keywords = keywords
                    
                    if content:
                        logger.debug(f"    ✓ 成功 ({len(content)} 字元)")
                    else:
                        item.fetch_error = "內容解析失敗"
                except Exception as e:
                    item.fetch_error = str(e)
                    logger.warning(f"    ✗ 錯誤: {e}")
                
                # 避免請求過快
                if i < len(all_news) - 1:
                    time.sleep(0.8)
            
            successful = sum(1 for item in all_news if item.has_content())
            logger.info(f"文章內容爬取完成: {successful}/{len(all_news)} 成功")
        
        return all_news

    def get_bitcoin_news(self, limit: int = 3, fetch_content: bool = True) -> list[NewsItem]:
        """
        獲取比特幣相關新聞

        Args:
            limit: 返回的新聞數量
            fetch_content: 是否爬取文章全文內容

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

            logger.info(f"成功獲取 {len(news_items)} 則新聞標題")
            
            # 爬取文章內容
            if fetch_content and NEWSPAPER_AVAILABLE:
                logger.info("開始爬取新聞文章內容...")
                for i, item in enumerate(news_items):
                    logger.info(f"  [{i+1}/{len(news_items)}] 爬取: {item.title[:40]}...")
                    try:
                        content, summary, keywords = self.fetch_article_content(item.link)
                        item.content = content
                        item.content_summary = summary
                        item.keywords = keywords
                        
                        if content:
                            logger.debug(f"    ✓ 成功 ({len(content)} 字元)")
                        else:
                            item.fetch_error = "內容解析失敗"
                            logger.debug(f"    ✗ 內容為空")
                    except Exception as e:
                        item.fetch_error = str(e)
                        logger.warning(f"    ✗ 錯誤: {e}")
                    
                    # 避免請求過快
                    if i < len(news_items) - 1:
                        time.sleep(1.0)
                
                successful = sum(1 for item in news_items if item.has_content())
                logger.info(f"文章內容爬取完成: {successful}/{len(news_items)} 成功")
            elif fetch_content and not NEWSPAPER_AVAILABLE:
                logger.warning("newspaper3k 未安裝，跳過文章內容爬取")

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
