"""
Fear & Greed Index API 客戶端 - 抓取加密貨幣市場情緒指數
API 來源: https://alternative.me/crypto/fear-and-greed-index/
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class FearGreedData:
    """恐慌貪婪指數資料結構"""

    value: int  # 指數值 (0-100)
    value_classification: str  # 分類 (Extreme Fear, Fear, Neutral, Greed, Extreme Greed)
    timestamp: str  # 時間戳記
    time_until_update: Optional[int]  # 距離下次更新的秒數

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "classification": self.value_classification,
            "timestamp": self.timestamp,
            "time_until_update": self.time_until_update,
        }

    @property
    def sentiment_emoji(self) -> str:
        """根據指數值返回對應的表情符號"""
        if self.value <= 25:
            return "😱"  # Extreme Fear
        elif self.value <= 45:
            return "😰"  # Fear
        elif self.value <= 55:
            return "😐"  # Neutral
        elif self.value <= 75:
            return "😊"  # Greed
        else:
            return "🤑"  # Extreme Greed

    @property
    def sentiment_zh(self) -> str:
        """返回中文情緒分類"""
        if self.value <= 25:
            return "極度恐慌"
        elif self.value <= 45:
            return "恐慌"
        elif self.value <= 55:
            return "中性"
        elif self.value <= 75:
            return "貪婪"
        else:
            return "極度貪婪"


class FearGreedClient:
    """Alternative.me Fear & Greed Index API 客戶端"""

    BASE_URL = "https://api.alternative.me/fng/"
    TIMEOUT = 30

    def __init__(self):
        """初始化客戶端"""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "CoinPilot-AI/0.1.0",
            }
        )

    def get_current_index(self) -> FearGreedData:
        """
        獲取當前恐慌貪婪指數

        Returns:
            FearGreedData: 包含指數值和分類的資料

        Raises:
            requests.RequestException: API 請求失敗
            KeyError: 回應格式異常
        """
        params = {"limit": 1, "format": "json"}

        logger.info("正在從 Alternative.me 獲取恐慌貪婪指數...")

        try:
            response = self.session.get(
                self.BASE_URL, params=params, timeout=self.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            if data.get("metadata", {}).get("error"):
                raise ValueError(f"API 錯誤: {data['metadata']['error']}")

            index_data = data["data"][0]

            # 將 Unix timestamp 轉換為 ISO 格式
            timestamp = datetime.fromtimestamp(int(index_data["timestamp"]))

            result = FearGreedData(
                value=int(index_data["value"]),
                value_classification=index_data["value_classification"],
                timestamp=timestamp.isoformat(),
                time_until_update=int(index_data.get("time_until_update", 0)) or None,
            )

            logger.info(
                f"恐慌貪婪指數: {result.value} ({result.value_classification}) {result.sentiment_emoji}"
            )
            return result

        except requests.RequestException as e:
            logger.error(f"Fear & Greed API 請求失敗: {e}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Fear & Greed API 回應格式異常: {e}")
            raise

    def get_historical(self, days: int = 7) -> list[FearGreedData]:
        """
        獲取歷史恐慌貪婪指數

        Args:
            days: 獲取的天數

        Returns:
            list[FearGreedData]: 歷史指數列表
        """
        params = {"limit": days, "format": "json"}

        try:
            response = self.session.get(
                self.BASE_URL, params=params, timeout=self.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data["data"]:
                timestamp = datetime.fromtimestamp(int(item["timestamp"]))
                results.append(
                    FearGreedData(
                        value=int(item["value"]),
                        value_classification=item["value_classification"],
                        timestamp=timestamp.isoformat(),
                        time_until_update=None,
                    )
                )

            return results

        except requests.RequestException as e:
            logger.error(f"Fear & Greed API 請求失敗: {e}")
            raise


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(level=logging.INFO)
    client = FearGreedClient()
    current = client.get_current_index()
    print(current.to_dict())
    print(f"情緒: {current.sentiment_zh} {current.sentiment_emoji}")
