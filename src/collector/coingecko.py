"""
CoinGecko API 客戶端 - 抓取 BTC 價格資料
API 文件: https://www.coingecko.com/en/api/documentation
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class BTCPriceData:
    """比特幣價格資料結構"""

    price_usd: float  # 現價 (USD)
    price_change_24h: float  # 24 小時漲跌幅 (%)
    volume_24h: float  # 24 小時交易量 (USD)
    market_cap: float  # 市值 (USD)
    last_updated: str  # 最後更新時間

    def to_dict(self) -> dict:
        return {
            "price_usd": self.price_usd,
            "price_change_24h": self.price_change_24h,
            "volume_24h": self.volume_24h,
            "market_cap": self.market_cap,
            "last_updated": self.last_updated,
        }


class CoinGeckoClient:
    """CoinGecko API 客戶端"""

    BASE_URL = "https://api.coingecko.com/api/v3"
    PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"
    TIMEOUT = 30

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 CoinGecko 客戶端

        Args:
            api_key: CoinGecko API Key (可選)
                     - Demo Key: 免費，每月 10,000 次請求
                     - Pro Key: 付費，更高限額
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "CoinPilot-AI/0.1.0",
            }
        )

        if api_key:
            logger.info("CoinGecko: 使用 API Key 認證")
        else:
            logger.warning("CoinGecko: 未提供 API Key，可能受到 Rate Limit 限制")

    def _add_api_key_to_params(self, params: dict) -> dict:
        """將 API Key 加入查詢參數 (返回新的 dict)"""
        if self.api_key:
            # 創建副本避免修改原 dict
            new_params = params.copy()
            new_params["x_cg_demo_api_key"] = self.api_key
            return new_params
        return params

    def get_btc_price(self) -> BTCPriceData:
        """
        獲取比特幣當前價格資料

        Returns:
            BTCPriceData: 包含價格、漲跌幅、交易量等資訊

        Raises:
            requests.RequestException: API 請求失敗
            KeyError: 回應格式異常
        """
        endpoint = f"{self.BASE_URL}/coins/bitcoin"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        }
        params = self._add_api_key_to_params(params)

        logger.info("正在從 CoinGecko 獲取 BTC 價格資料...")

        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()

            market_data = data["market_data"]

            result = BTCPriceData(
                price_usd=market_data["current_price"]["usd"],
                price_change_24h=market_data["price_change_percentage_24h"],
                volume_24h=market_data["total_volume"]["usd"],
                market_cap=market_data["market_cap"]["usd"],
                last_updated=data["last_updated"],
            )

            logger.info(
                f"BTC 價格: ${result.price_usd:,.2f} ({result.price_change_24h:+.2f}%)"
            )
            return result

        except requests.RequestException as e:
            logger.error(f"CoinGecko API 請求失敗: {e}")
            raise
        except KeyError as e:
            logger.error(f"CoinGecko API 回應格式異常: {e}")
            raise

    def get_global_data(self) -> "GlobalMarketData":
        """
        獲取全球加密貨幣市場數據

        包含 BTC Dominance、總市值、24H 交易量等

        Returns:
            GlobalMarketData: 全球市場數據

        Raises:
            requests.RequestException: API 請求失敗
        """
        endpoint = f"{self.BASE_URL}/global"
        params = self._add_api_key_to_params({})

        logger.info("正在從 CoinGecko 獲取全球市場數據...")

        try:
            response = self.session.get(endpoint, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()["data"]

            result = GlobalMarketData(
                total_market_cap_usd=data["total_market_cap"]["usd"],
                total_volume_24h_usd=data["total_volume"]["usd"],
                btc_dominance=data["market_cap_percentage"]["btc"],
                eth_dominance=data["market_cap_percentage"]["eth"],
                market_cap_change_24h=data["market_cap_change_percentage_24h_usd"],
                active_cryptocurrencies=data["active_cryptocurrencies"],
                markets=data["markets"],
                last_updated=data["updated_at"],
            )

            logger.info(
                f"BTC Dominance: {result.btc_dominance:.2f}% | "
                f"總市值: ${result.total_market_cap_usd / 1e12:.2f}T"
            )
            return result

        except requests.RequestException as e:
            logger.error(f"CoinGecko Global API 請求失敗: {e}")
            raise
        except KeyError as e:
            logger.error(f"CoinGecko Global API 回應格式異常: {e}")
            raise


@dataclass
class GlobalMarketData:
    """全球加密貨幣市場數據"""

    total_market_cap_usd: float  # 總市值 (USD)
    total_volume_24h_usd: float  # 24H 總交易量 (USD)
    btc_dominance: float  # BTC 市佔率 (%)
    eth_dominance: float  # ETH 市佔率 (%)
    market_cap_change_24h: float  # 24H 市值變化 (%)
    active_cryptocurrencies: int  # 活躍加密貨幣數量
    markets: int  # 交易所數量
    last_updated: int  # 最後更新時間 (Unix timestamp)

    @property
    def btc_dominance_signal(self) -> str:
        """BTC Dominance 趨勢信號"""
        if self.btc_dominance > 60:
            return "high"  # BTC 高度主導
        elif self.btc_dominance < 40:
            return "low"  # 山寨幣季節
        else:
            return "normal"  # 正常區間

    @property
    def signal_zh(self) -> str:
        """中文信號描述"""
        signals = {
            "high": f"BTC.D {self.btc_dominance:.1f}% 📈 資金回流比特幣，山寨幣可能吸血下跌",
            "low": f"BTC.D {self.btc_dominance:.1f}% 📉 比特幣橫盤，資金流向山寨幣 (Altcoin Season)",
            "normal": f"BTC.D {self.btc_dominance:.1f}% ⚖️ 市場結構正常",
        }
        return signals[self.btc_dominance_signal]

    def to_dict(self) -> dict:
        return {
            "total_market_cap_usd": self.total_market_cap_usd,
            "total_volume_24h_usd": self.total_volume_24h_usd,
            "btc_dominance": round(self.btc_dominance, 2),
            "eth_dominance": round(self.eth_dominance, 2),
            "market_cap_change_24h": round(self.market_cap_change_24h, 2),
            "active_cryptocurrencies": self.active_cryptocurrencies,
            "markets": self.markets,
            "btc_dominance_signal": self.btc_dominance_signal,
            "signal_zh": self.signal_zh,
            "last_updated": self.last_updated,
        }


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(level=logging.INFO)
    client = CoinGeckoClient()
    price_data = client.get_btc_price()
    print("=== BTC Price ===")
    print(price_data.to_dict())

    print("\n=== Global Market ===")
    global_data = client.get_global_data()
    print(global_data.to_dict())
