"""
Fear & Greed Index 歷史快取模組

使用 Alternative.me API 的 limit=0 參數一次性取得全部歷史資料
快取至本地 JSON 避免重複請求
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class FearGreedHistoryItem:
    """歷史 Fear & Greed 資料"""
    date: str  # YYYY-MM-DD
    value: int  # 0-100
    classification: str  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "value": self.value,
            "classification": self.classification,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FearGreedHistoryItem":
        return cls(
            date=data.get("date", ""),
            value=int(data.get("value", 50)),
            classification=data.get("classification", "Neutral"),
        )
    
    @property
    def sentiment_zh(self) -> str:
        """中文情緒分類"""
        mapping = {
            "Extreme Fear": "極度恐慌",
            "Fear": "恐慌",
            "Neutral": "中性",
            "Greed": "貪婪",
            "Extreme Greed": "極度貪婪",
        }
        return mapping.get(self.classification, "中性")
    
    @property
    def emoji(self) -> str:
        """情緒表情符號"""
        if self.value <= 25:
            return "😱"
        elif self.value <= 45:
            return "😰"
        elif self.value <= 55:
            return "😐"
        elif self.value <= 75:
            return "😊"
        else:
            return "🤑"


class FearGreedCache:
    """
    Fear & Greed Index 歷史快取管理器
    
    使用 Alternative.me 免費 API，一次性抓取所有歷史資料後快取
    """
    
    API_URL = "https://api.alternative.me/fng/"
    CACHE_FILE = "data/chronos_fear_greed.json"
    TIMEOUT = 60
    
    def __init__(self, cache_file: Optional[str] = None):
        """
        初始化 Fear & Greed 快取
        
        Args:
            cache_file: 快取檔案路徑
        """
        self.cache_file = Path(cache_file or self.CACHE_FILE)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 內存快取
        self._data: Optional[dict[str, FearGreedHistoryItem]] = None
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CoinPilot-Chronos/0.1.0",
            "Accept": "application/json",
        })
    
    def _load_cache(self) -> dict[str, FearGreedHistoryItem]:
        """從檔案載入快取"""
        if self._data is not None:
            return self._data
        
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            self._data = {
                item["date"]: FearGreedHistoryItem.from_dict(item)
                for item in cache_data.get("data", [])
            }
            
            logger.info(f"載入 Fear & Greed 快取: {len(self._data)} 天")
            return self._data
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"載入 Fear & Greed 快取失敗: {e}")
            return {}
    
    def _save_cache(self, data: dict[str, FearGreedHistoryItem]):
        """儲存快取至檔案"""
        cache_data = {
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "count": len(data),
                "source": "alternative.me",
            },
            "data": [item.to_dict() for item in sorted(data.values(), key=lambda x: x.date)],
        }
        
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已儲存 Fear & Greed 快取: {len(data)} 天")
    
    def fetch_all_history(self, force: bool = False) -> int:
        """
        從 API 抓取所有歷史資料
        
        使用 limit=0 參數取得所有歷史資料 (從 2018 年至今)
        
        Args:
            force: 是否強制重新抓取
            
        Returns:
            int: 抓取的資料筆數
        """
        if not force and self.cache_file.exists():
            # 檢查快取是否已經足夠新
            cache_data = self._load_cache()
            if cache_data:
                # 如果快取的最新日期是昨天或今天，跳過更新
                latest_date = max(cache_data.keys())
                if latest_date >= (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"):
                    logger.info(f"快取已是最新 (最新日期: {latest_date})")
                    return len(cache_data)
        
        logger.info("正在從 Alternative.me 抓取 Fear & Greed 歷史資料...")
        
        try:
            # limit=0 取得所有歷史資料
            params = {"limit": 0, "format": "json", "date_format": "world"}
            response = self.session.get(self.API_URL, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            
            api_data = response.json()
            
            if api_data.get("metadata", {}).get("error"):
                raise ValueError(f"API 錯誤: {api_data['metadata']['error']}")
            
            # 解析資料
            data = {}
            for item in api_data.get("data", []):
                # timestamp 格式: "05-02-2024" (DD-MM-YYYY)
                timestamp = item.get("timestamp", "")
                
                # 轉換日期格式
                try:
                    # 嘗試解析 DD-MM-YYYY 格式
                    dt = datetime.strptime(timestamp, "%d-%m-%Y")
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    # 嘗試 Unix timestamp
                    try:
                        dt = datetime.fromtimestamp(int(timestamp))
                        date_str = dt.strftime("%Y-%m-%d")
                    except:
                        continue
                
                data[date_str] = FearGreedHistoryItem(
                    date=date_str,
                    value=int(item.get("value", 50)),
                    classification=item.get("value_classification", "Neutral"),
                )
            
            # 儲存快取
            self._data = data
            self._save_cache(data)
            
            logger.info(f"成功抓取 Fear & Greed 歷史: {len(data)} 天")
            return len(data)
            
        except requests.RequestException as e:
            logger.error(f"Fear & Greed API 請求失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"處理 Fear & Greed 資料失敗: {e}")
            raise
    
    def get_by_date(self, target_date: date) -> Optional[FearGreedHistoryItem]:
        """
        取得特定日期的 Fear & Greed Index
        
        Args:
            target_date: 目標日期
            
        Returns:
            FearGreedHistoryItem: 資料項目，若無資料則返回 None
        """
        cache = self._load_cache()
        date_str = target_date.strftime("%Y-%m-%d")
        return cache.get(date_str)
    
    def get_range(self, start_date: date, end_date: date) -> list[FearGreedHistoryItem]:
        """
        取得日期範圍內的 Fear & Greed Index
        
        Args:
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            list[FearGreedHistoryItem]: 資料列表
        """
        cache = self._load_cache()
        results = []
        
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            if date_str in cache:
                results.append(cache[date_str])
            current += timedelta(days=1)
        
        return results
    
    def get_summary(self) -> dict:
        """取得快取摘要"""
        cache = self._load_cache()
        
        if not cache:
            return {"status": "empty", "count": 0}
        
        dates = list(cache.keys())
        return {
            "status": "loaded",
            "count": len(cache),
            "date_range": {
                "start": min(dates),
                "end": max(dates),
            },
        }
    
    def ensure_loaded(self):
        """確保資料已載入 (若無快取則自動抓取)"""
        cache = self._load_cache()
        
        if not cache:
            self.fetch_all_history()


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(level=logging.INFO)
    
    cache = FearGreedCache()
    
    # 抓取歷史資料
    count = cache.fetch_all_history()
    print(f"已快取 {count} 天資料")
    
    # 查詢特定日期
    test_date = date(2024, 1, 15)
    item = cache.get_by_date(test_date)
    if item:
        print(f"\n{test_date}: {item.value} - {item.sentiment_zh} {item.emoji}")
    
    # 摘要
    print(f"\n快取摘要: {cache.get_summary()}")
