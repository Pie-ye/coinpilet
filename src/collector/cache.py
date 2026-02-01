"""
本地快取模組 - 儲存歷史 K 線數據避免過度請求 API

快取策略:
- 日線 (1d): 儲存 365 天
- 4 小時線 (4h): 儲存 90 天
- 每日增量更新，只抓取缺失的新數據
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """快取配置"""

    interval: str  # K 線週期 (1d, 4h)
    max_days: int  # 最大保留天數
    filename: str  # 快取檔案名稱


# 預設快取配置
CACHE_CONFIGS = {
    "1d": CacheConfig(interval="1d", max_days=365, filename="ohlc_daily.json"),
    "4h": CacheConfig(interval="4h", max_days=90, filename="ohlc_4h.json"),
}


class OHLCCache:
    """
    K 線數據快取管理器

    使用方式:
        cache = OHLCCache(data_dir="data")

        # 讀取快取
        daily_data = cache.load("1d")

        # 儲存快取
        cache.save("1d", klines_data)

        # 取得需要更新的時間範圍
        start_time = cache.get_update_start_time("1d")
    """

    def __init__(self, data_dir: str = "data"):
        """
        初始化快取管理器

        Args:
            data_dir: 資料目錄路徑
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, interval: str) -> Path:
        """取得快取檔案路徑"""
        if interval not in CACHE_CONFIGS:
            raise ValueError(f"不支援的時間週期: {interval}")
        config = CACHE_CONFIGS[interval]
        return self.data_dir / config.filename

    def load(self, interval: str) -> Optional[dict]:
        """
        讀取快取數據

        Args:
            interval: K 線週期

        Returns:
            dict: 快取數據，包含 metadata 和 data 欄位
            None: 快取不存在
        """
        cache_path = self._get_cache_path(interval)

        if not cache_path.exists():
            logger.info(f"快取檔案不存在: {cache_path}")
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            logger.info(
                f"讀取 {interval} 快取: {len(cache_data.get('data', []))} 根 K 線"
            )
            return cache_data

        except json.JSONDecodeError as e:
            logger.error(f"快取檔案格式錯誤: {e}")
            return None

    def save(self, interval: str, klines: list[dict], merge: bool = True):
        """
        儲存 K 線數據到快取

        Args:
            interval: K 線週期
            klines: K 線數據列表 (dict 格式)
            merge: 是否與現有快取合併
        """
        cache_path = self._get_cache_path(interval)
        config = CACHE_CONFIGS[interval]

        if merge:
            # 讀取現有快取並合併
            existing = self.load(interval)
            if existing and existing.get("data"):
                # 使用 timestamp 作為 key 去重
                existing_map = {k["timestamp"]: k for k in existing["data"]}
                for kline in klines:
                    existing_map[kline["timestamp"]] = kline

                # 轉回列表並排序
                klines = sorted(existing_map.values(), key=lambda x: x["timestamp"])

        # 清理過期數據
        cutoff_time = datetime.now() - timedelta(days=config.max_days)
        cutoff_ms = int(cutoff_time.timestamp() * 1000)
        klines = [k for k in klines if k["timestamp"] >= cutoff_ms]

        # 建立快取結構
        cache_data = {
            "metadata": {
                "interval": interval,
                "symbol": "BTCUSDT",
                "last_updated": datetime.now().isoformat(),
                "count": len(klines),
                "start_date": klines[0]["datetime"] if klines else None,
                "end_date": klines[-1]["datetime"] if klines else None,
            },
            "data": klines,
        }

        # 寫入檔案
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        logger.info(f"已儲存 {interval} 快取: {len(klines)} 根 K 線 -> {cache_path}")

    def get_last_timestamp(self, interval: str) -> Optional[int]:
        """
        取得快取中最後一根 K 線的時間戳

        Args:
            interval: K 線週期

        Returns:
            int: 最後時間戳 (毫秒)
            None: 快取為空
        """
        cache_data = self.load(interval)
        if not cache_data or not cache_data.get("data"):
            return None

        return cache_data["data"][-1]["timestamp"]

    def get_update_start_time(self, interval: str) -> Optional[int]:
        """
        取得需要更新的起始時間

        返回最後一根 K 線的收盤時間 + 1ms，
        這樣可以從下一根 K 線開始抓取

        Args:
            interval: K 線週期

        Returns:
            int: 起始時間戳 (毫秒)
            None: 快取為空，需要完整抓取
        """
        cache_data = self.load(interval)
        if not cache_data or not cache_data.get("data"):
            return None

        last_kline = cache_data["data"][-1]
        # 使用收盤時間 + 1ms 作為下一次起始時間
        # 如果快取中沒有 close_time，用 timestamp + interval 估算
        if "close_time" in last_kline:
            return last_kline["close_time"] + 1
        else:
            # 估算: 日線 = 86400000ms, 4H = 14400000ms
            interval_ms = {
                "1d": 86400000,
                "4h": 14400000,
                "1h": 3600000,
            }
            return last_kline["timestamp"] + interval_ms.get(interval, 86400000)

    def get_cached_klines(self, interval: str) -> list[dict]:
        """
        取得快取的 K 線數據列表

        Args:
            interval: K 線週期

        Returns:
            list[dict]: K 線數據列表
        """
        cache_data = self.load(interval)
        if not cache_data:
            return []
        return cache_data.get("data", [])

    def is_cache_fresh(self, interval: str, max_age_hours: int = 24) -> bool:
        """
        檢查快取是否新鮮

        Args:
            interval: K 線週期
            max_age_hours: 最大快取年齡 (小時)

        Returns:
            bool: 快取是否仍然新鮮
        """
        cache_data = self.load(interval)
        if not cache_data or not cache_data.get("metadata"):
            return False

        last_updated = cache_data["metadata"].get("last_updated")
        if not last_updated:
            return False

        try:
            update_time = datetime.fromisoformat(last_updated)
            age = datetime.now() - update_time
            return age.total_seconds() < max_age_hours * 3600
        except (ValueError, TypeError):
            return False

    def get_cache_info(self, interval: str) -> dict:
        """
        取得快取資訊摘要

        Args:
            interval: K 線週期

        Returns:
            dict: 快取資訊
        """
        cache_data = self.load(interval)
        if not cache_data:
            return {
                "exists": False,
                "interval": interval,
                "count": 0,
            }

        metadata = cache_data.get("metadata", {})
        return {
            "exists": True,
            "interval": interval,
            "count": metadata.get("count", 0),
            "start_date": metadata.get("start_date"),
            "end_date": metadata.get("end_date"),
            "last_updated": metadata.get("last_updated"),
            "is_fresh": self.is_cache_fresh(interval),
        }

    def clear(self, interval: str):
        """
        清除指定週期的快取

        Args:
            interval: K 線週期
        """
        cache_path = self._get_cache_path(interval)
        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"已清除 {interval} 快取: {cache_path}")

    def clear_all(self):
        """清除所有快取"""
        for interval in CACHE_CONFIGS:
            self.clear(interval)
