"""
新聞快取模組 - 按月分割的歷史新聞快取

支援：
- 按日期載入/儲存新聞
- 自動檢測缺失日期
- 避免重複爬取
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CachedNewsItem:
    """快取的新聞項目"""
    title: str
    link: str
    source: str
    published: str
    summary: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "published": self.published,
            "summary": self.summary,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CachedNewsItem":
        return cls(
            title=data.get("title", ""),
            link=data.get("link", ""),
            source=data.get("source", ""),
            published=data.get("published", ""),
            summary=data.get("summary"),
        )


@dataclass
class NewsCacheConfig:
    """新聞快取配置"""
    data_dir: str = "data/chronos_news"
    max_news_per_day: int = 5
    request_delay: float = 1.5  # 請求間隔（秒）


class NewsCache:
    """
    日期為基礎的新聞快取管理器
    
    檔案結構：
    data/chronos_news/
    ├── index.json         # 索引檔，記錄已快取的日期
    ├── 2024-01.json       # 1 月新聞
    ├── 2024-02.json       # 2 月新聞
    └── ...
    
    月份檔案格式：
    {
        "metadata": {
            "month": "2024-01",
            "last_updated": "2026-02-05T12:00:00",
            "count": 155
        },
        "data": {
            "2024-01-01": [
                {"title": "...", "link": "...", "source": "...", ...},
                ...
            ],
            "2024-01-02": [...],
            ...
        }
    }
    """
    
    def __init__(self, config: Optional[NewsCacheConfig] = None):
        """
        初始化新聞快取管理器
        
        Args:
            config: 快取配置
        """
        self.config = config or NewsCacheConfig()
        self.data_dir = Path(self.config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 內存快取索引
        self._cached_dates: Optional[set[str]] = None
        
        logger.info(f"新聞快取目錄: {self.data_dir}")
    
    def _get_month_file(self, target_date: date) -> Path:
        """取得指定日期對應的月份檔案"""
        return self.data_dir / f"{target_date.strftime('%Y-%m')}.json"
    
    def _get_index_file(self) -> Path:
        """取得索引檔案路徑"""
        return self.data_dir / "index.json"
    
    def _load_month_data(self, month_file: Path) -> dict:
        """載入月份資料"""
        if not month_file.exists():
            return {
                "metadata": {
                    "month": month_file.stem,
                    "last_updated": None,
                    "count": 0,
                },
                "data": {},
            }
        
        try:
            with open(month_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"載入月份資料失敗 {month_file}: {e}")
            return {
                "metadata": {"month": month_file.stem, "last_updated": None, "count": 0},
                "data": {},
            }
    
    def _save_month_data(self, month_file: Path, data: dict):
        """儲存月份資料"""
        # 更新 metadata
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        data["metadata"]["count"] = sum(len(v) for v in data.get("data", {}).values())
        
        with open(month_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"已儲存月份資料: {month_file}")
    
    def _update_index(self):
        """更新索引檔案"""
        index_file = self._get_index_file()
        
        # 掃描所有月份檔案
        cached_dates = set()
        months = []
        
        for month_file in sorted(self.data_dir.glob("????-??.json")):
            month_data = self._load_month_data(month_file)
            cached_dates.update(month_data.get("data", {}).keys())
            months.append({
                "month": month_file.stem,
                "count": month_data.get("metadata", {}).get("count", 0),
            })
        
        # 儲存索引
        index_data = {
            "last_updated": datetime.now().isoformat(),
            "total_dates": len(cached_dates),
            "total_news": sum(m["count"] for m in months),
            "months": months,
        }
        
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        # 更新內存快取
        self._cached_dates = cached_dates
        
        logger.info(f"索引已更新: {len(cached_dates)} 天, {index_data['total_news']} 則新聞")
    
    def get_cached_dates(self) -> set[str]:
        """
        取得所有已快取的日期
        
        Returns:
            set[str]: 已快取的日期集合 (格式: YYYY-MM-DD)
        """
        if self._cached_dates is not None:
            return self._cached_dates
        
        cached = set()
        
        for month_file in self.data_dir.glob("????-??.json"):
            try:
                month_data = self._load_month_data(month_file)
                cached.update(month_data.get("data", {}).keys())
            except Exception as e:
                logger.warning(f"讀取月份檔案失敗 {month_file}: {e}")
        
        self._cached_dates = cached
        return cached
    
    def get_missing_dates(self, start_date: date, end_date: date) -> list[date]:
        """
        取得指定範圍內缺失的日期
        
        Args:
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            list[date]: 缺失的日期列表
        """
        cached = self.get_cached_dates()
        missing = []
        
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            if date_str not in cached:
                missing.append(current)
            current += timedelta(days=1)
        
        return missing
    
    def load_date(self, target_date: date) -> list[CachedNewsItem]:
        """
        載入特定日期的新聞
        
        Args:
            target_date: 目標日期
            
        Returns:
            list[CachedNewsItem]: 新聞列表
        """
        month_file = self._get_month_file(target_date)
        
        if not month_file.exists():
            return []
        
        month_data = self._load_month_data(month_file)
        date_str = target_date.strftime("%Y-%m-%d")
        
        news_list = month_data.get("data", {}).get(date_str, [])
        return [CachedNewsItem.from_dict(item) for item in news_list]
    
    def save_date(self, target_date: date, news_items: list[dict]):
        """
        儲存特定日期的新聞
        
        Args:
            target_date: 目標日期
            news_items: 新聞項目列表 (dict 格式)
        """
        month_file = self._get_month_file(target_date)
        month_data = self._load_month_data(month_file)
        
        date_str = target_date.strftime("%Y-%m-%d")
        
        # 限制每天最多 N 則新聞
        if len(news_items) > self.config.max_news_per_day:
            news_items = news_items[:self.config.max_news_per_day]
        
        month_data["data"][date_str] = news_items
        
        self._save_month_data(month_file, month_data)
        
        # 清除快取索引，下次讀取時重新建立
        self._cached_dates = None
        
        logger.debug(f"已儲存 {date_str} 的 {len(news_items)} 則新聞")
    
    def has_date(self, target_date: date) -> bool:
        """
        檢查特定日期是否已有快取
        
        Args:
            target_date: 目標日期
            
        Returns:
            bool: 是否已有快取
        """
        date_str = target_date.strftime("%Y-%m-%d")
        return date_str in self.get_cached_dates()
    
    def get_summary(self) -> dict:
        """
        取得快取摘要
        
        Returns:
            dict: 快取摘要資訊
        """
        index_file = self._get_index_file()
        
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        
        # 重新計算
        cached_dates = self.get_cached_dates()
        total_news = 0
        
        for month_file in self.data_dir.glob("????-??.json"):
            month_data = self._load_month_data(month_file)
            total_news += sum(len(v) for v in month_data.get("data", {}).values())
        
        return {
            "total_dates": len(cached_dates),
            "total_news": total_news,
            "date_range": {
                "start": min(cached_dates) if cached_dates else None,
                "end": max(cached_dates) if cached_dates else None,
            },
        }
    
    def clear(self):
        """清除所有快取"""
        import shutil
        
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir)
            self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._cached_dates = None
        logger.info("新聞快取已清除")


# 便捷函數
def load_news_for_date(target_date: date, cache_dir: str = "data/chronos_news") -> list[dict]:
    """
    載入特定日期的新聞（便捷函數）
    
    Args:
        target_date: 目標日期
        cache_dir: 快取目錄
        
    Returns:
        list[dict]: 新聞列表
    """
    cache = NewsCache(NewsCacheConfig(data_dir=cache_dir))
    items = cache.load_date(target_date)
    return [item.to_dict() for item in items]


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(level=logging.DEBUG)
    
    cache = NewsCache()
    
    # 測試儲存
    test_date = date(2024, 1, 15)
    test_news = [
        {
            "title": "Bitcoin Surges Past $45,000",
            "link": "https://example.com/news1",
            "source": "CoinDesk",
            "published": "2024-01-15T10:00:00",
            "summary": "BTC price reaches new highs...",
        },
        {
            "title": "ETF Approval Expected Soon",
            "link": "https://example.com/news2",
            "source": "CoinTelegraph",
            "published": "2024-01-15T12:00:00",
            "summary": "SEC decision imminent...",
        },
    ]
    
    cache.save_date(test_date, test_news)
    
    # 測試載入
    loaded = cache.load_date(test_date)
    print(f"載入 {len(loaded)} 則新聞")
    for item in loaded:
        print(f"  - {item.title}")
    
    # 測試摘要
    print(f"\n快取摘要: {cache.get_summary()}")
