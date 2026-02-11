"""
繪圖 Agent (Analyst) - 使用 yfinance + mplfinance 生成 BTC K 線圖

特點:
    - 白底簡約風格
    - 綠漲紅跌 K 線
    - 自動取得最新價格與漲跌幅
    - 支援自我修復機制
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ChartResult:
    """圖表生成結果"""
    success: bool
    chart_path: Optional[Path] = None
    current_price: float = 0.0
    price_change_24h: float = 0.0
    price_high_24h: float = 0.0
    price_low_24h: float = 0.0
    volume_24h: float = 0.0
    error_message: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "chart_path": str(self.chart_path) if self.chart_path else None,
            "current_price": self.current_price,
            "price_change_24h": self.price_change_24h,
            "price_high_24h": self.price_high_24h,
            "price_low_24h": self.price_low_24h,
            "volume_24h": self.volume_24h,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }

    def format_price_summary(self) -> str:
        """格式化價格摘要"""
        direction = "📈" if self.price_change_24h >= 0 else "📉"
        change_sign = "+" if self.price_change_24h >= 0 else ""
        return (
            f"{direction} BTC 現價: ${self.current_price:,.2f} "
            f"({change_sign}{self.price_change_24h:.2f}%)"
        )


class AnalystAgent:
    """
    繪圖 Agent - 生成 BTC K 線走勢圖
    
    使用 yfinance 取得數據，mplfinance 繪製圖表。
    圖表風格：白底、綠漲紅跌。
    
    使用方式:
        analyst = AnalystAgent()
        result = await analyst.generate_chart()
        print(result.chart_path)
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        max_retries: int = 3,
    ):
        """
        初始化繪圖 Agent
        
        Args:
            working_dir: 工作目錄
            output_dir: 圖表輸出目錄 (預設: site/static/images)
            max_retries: 最大重試次數
        """
        self.working_dir = working_dir or Path.cwd()
        self.output_dir = output_dir or self.working_dir / "site" / "static" / "images"
        self.max_retries = max_retries
        self.log = logger.bind(component="AnalystAgent")

    async def generate_chart(
        self,
        symbol: str = "BTC-USD",
        period: str = "5d",
        interval: str = "1h",
        filename: str = "btc_daily.png",
    ) -> ChartResult:
        """
        生成 K 線走勢圖
        
        Args:
            symbol: 交易對符號 (預設: BTC-USD)
            period: 數據週期 (預設: 5d = 過去 5 天，避免無數據問題)
            interval: K 線間隔 (預設: 1h = 1 小時)
            filename: 輸出檔名
            
        Returns:
            ChartResult: 圖表生成結果
        """
        self.log.info(
            "開始生成 K 線圖",
            symbol=symbol,
            period=period,
            interval=interval,
        )

        retry_count = 0
        last_error = None

        while retry_count <= self.max_retries:
            try:
                # 首先嘗試 yfinance
                result = await self._generate_chart_impl(
                    symbol=symbol,
                    period=period,
                    interval=interval,
                    filename=filename,
                )
                result.retry_count = retry_count
                return result

            except Exception as e:
                retry_count += 1
                last_error = str(e)
                
                self.log.warning(
                    "圖表生成失敗，嘗試重試",
                    retry_count=retry_count,
                    error=last_error,
                )

                # 嘗試修復常見問題
                if "No module named" in last_error:
                    await self._install_missing_module(last_error)
                elif "無法取得" in last_error or "No data found" in last_error:
                    # yfinance 無數據時，嘗試使用 Binance
                    self.log.info("嘗試使用 Binance 數據作為備用...")
                    try:
                        result = await self._generate_chart_from_binance(filename)
                        result.retry_count = retry_count
                        return result
                    except Exception as binance_error:
                        self.log.warning(f"Binance 備用方案也失敗: {binance_error}")
                elif retry_count <= self.max_retries:
                    # 等待後重試
                    import asyncio
                    await asyncio.sleep(1)

        return ChartResult(
            success=False,
            error_message=f"達到最大重試次數: {last_error}",
            retry_count=retry_count,
        )

    async def _generate_chart_from_binance(self, filename: str) -> ChartResult:
        """使用 Binance 數據生成圖表 (備用方案)"""
        import pandas as pd
        import mplfinance as mpf
        from src.collector.binance import BinanceClient
        
        self.log.info("正在從 Binance 取得數據...")
        client = BinanceClient()
        klines = client.get_klines(interval="1h", limit=24)  # 過去 24 小時
        
        if not klines:
            raise ValueError("無法從 Binance 取得數據")
        
        # 轉換為 DataFrame
        data = []
        for k in klines:
            data.append({
                "Date": k.datetime,
                "Open": k.open,
                "High": k.high,
                "Low": k.low,
                "Close": k.close,
                "Volume": k.volume,
            })
        
        df = pd.DataFrame(data)
        df.set_index("Date", inplace=True)
        
        self.log.info(f"取得 {len(df)} 筆 Binance K 線數據")
        
        # 計算價格資訊
        current_price = float(df["Close"].iloc[-1])
        open_price = float(df["Open"].iloc[0])
        price_change_24h = ((current_price - open_price) / open_price) * 100
        price_high_24h = float(df["High"].max())
        price_low_24h = float(df["Low"].min())
        volume_24h = float(df["Volume"].sum())
        
        # 繪製圖表
        return await self._render_chart(
            df, filename, current_price, price_change_24h,
            price_high_24h, price_low_24h, volume_24h
        )

    async def _generate_chart_impl(
        self,
        symbol: str,
        period: str,
        interval: str,
        filename: str,
    ) -> ChartResult:
        """實際的圖表生成邏輯"""
        import yfinance as yf
        import mplfinance as mpf
        import pandas as pd

        # 取得數據
        self.log.info("正在從 Yahoo Finance 取得數據...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            raise ValueError(f"無法取得 {symbol} 的數據")

        self.log.info(f"取得 {len(df)} 筆 K 線數據")

        # 計算價格資訊
        current_price = float(df["Close"].iloc[-1])
        open_price = float(df["Open"].iloc[0])
        price_change_24h = ((current_price - open_price) / open_price) * 100
        price_high_24h = float(df["High"].max())
        price_low_24h = float(df["Low"].min())
        volume_24h = float(df["Volume"].sum())

        # 繪製圖表
        return await self._render_chart(
            df, filename, current_price, price_change_24h,
            price_high_24h, price_low_24h, volume_24h
        )

    async def _render_chart(
        self,
        df,
        filename: str,
        current_price: float,
        price_change_24h: float,
        price_high_24h: float,
        price_low_24h: float,
        volume_24h: float,
    ) -> ChartResult:
        """共用的圖表繪製邏輯"""
        import mplfinance as mpf
        import matplotlib.pyplot as plt

        # 確保輸出目錄存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / filename

        # 設定白底簡約風格 + 綠漲紅跌
        mc = mpf.make_marketcolors(
            up="green",      # 漲 = 綠色
            down="red",      # 跌 = 紅色
            edge="inherit",
            wick="inherit",
            volume="inherit",
        )

        style = mpf.make_mpf_style(
            base_mpf_style="classic",
            marketcolors=mc,
            facecolor="white",
            edgecolor="white",
            figcolor="white",
            gridcolor="#E5E5E5",
            gridstyle="--",
            gridaxis="both",
            y_on_right=True,
            rc={
                "font.size": 10,
                "axes.labelsize": 10,
                "axes.titlesize": 12,
            },
        )

        # 生成標題
        direction = "▲" if price_change_24h >= 0 else "▼"
        change_sign = "+" if price_change_24h >= 0 else ""
        title = (
            f"BTC/USD | ${current_price:,.2f} "
            f"{direction} {change_sign}{price_change_24h:.2f}% | "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        # 繪製 K 線圖
        self.log.info("正在繪製 K 線圖...")
        
        fig, axes = mpf.plot(
            df,
            type="candle",
            style=style,
            title=title,
            volume=True,
            figsize=(12, 8),
            tight_layout=True,
            returnfig=True,
            panel_ratios=(3, 1),
            datetime_format="%H:%M",
            xrotation=0,
        )

        # 儲存圖片
        fig.savefig(
            output_path,
            dpi=150,
            bbox_inches="tight",
            facecolor="white",
            edgecolor="none",
        )
        
        # 關閉 figure 釋放記憶體
        plt.close(fig)

        self.log.info("K 線圖已儲存", path=str(output_path))

        return ChartResult(
            success=True,
            chart_path=output_path,
            current_price=current_price,
            price_change_24h=price_change_24h,
            price_high_24h=price_high_24h,
            price_low_24h=price_low_24h,
            volume_24h=volume_24h,
        )

    async def _install_missing_module(self, error_message: str) -> None:
        """嘗試安裝缺少的模組"""
        import subprocess
        import sys

        # 解析模組名稱
        if "No module named '" in error_message:
            module = error_message.split("No module named '")[1].split("'")[0]
        elif 'No module named "' in error_message:
            module = error_message.split('No module named "')[1].split('"')[0]
        else:
            return

        # 模組名稱對應 pip 套件名稱
        module_to_package = {
            "yfinance": "yfinance",
            "mplfinance": "mplfinance",
            "matplotlib": "matplotlib",
            "pandas": "pandas",
            "numpy": "numpy",
        }

        package = module_to_package.get(module.split(".")[0], module)

        self.log.info(f"嘗試安裝缺少的套件: {package}")

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True,
                timeout=60,
            )
            self.log.info(f"套件 {package} 安裝完成")
        except Exception as e:
            self.log.error(f"套件安裝失敗: {e}")

    async def generate_chart_with_agent(
        self,
        agent_core,
        custom_prompt: Optional[str] = None,
    ) -> ChartResult:
        """
        使用 Agent Core 生成圖表 (具備完整自我修復能力)
        
        這個方法讓 AI Agent 自己撰寫繪圖程式碼，
        適用於需要更複雜自訂圖表的場景。
        
        Args:
            agent_core: AgentCore 實例
            custom_prompt: 自訂提示詞
            
        Returns:
            ChartResult: 圖表生成結果
        """
        default_prompt = f"""你是數據分析師。請執行以下任務：

1. 使用 yfinance 獲取 BTC-USD 過去一天的 15 分鐘 K 線數據
2. 使用 mplfinance 繪製 K 線圖，要求：
   - 白底簡約風格
   - 綠漲紅跌 (up='green', down='red')
   - 標題包含當前價格和漲跌幅
   - 包含成交量圖
3. 圖片存檔至: {self.output_dir / 'btc_daily.png'}
4. 回報當前價格和 24h 漲跌幅

請使用 python_repl 工具執行 Python 程式碼。"""

        prompt = custom_prompt or default_prompt

        result = await agent_core.execute(prompt)

        if result.success and result.output:
            # 嘗試解析輸出中的價格資訊
            try:
                output = result.output
                current_price = self._extract_price_from_text(output)
                price_change = self._extract_change_from_text(output)
                
                return ChartResult(
                    success=True,
                    chart_path=self.output_dir / "btc_daily.png",
                    current_price=current_price,
                    price_change_24h=price_change,
                    retry_count=result.total_retries,
                )
            except Exception:
                pass

        return ChartResult(
            success=result.success,
            chart_path=self.output_dir / "btc_daily.png" if result.success else None,
            error_message=result.error_message,
            retry_count=result.total_retries,
        )

    def _extract_price_from_text(self, text: str) -> float:
        """從文字中提取價格"""
        import re
        # 匹配 $XX,XXX.XX 或 $XXXXX.XX 格式
        match = re.search(r"\$[\d,]+\.?\d*", text)
        if match:
            price_str = match.group().replace("$", "").replace(",", "")
            return float(price_str)
        return 0.0

    def _extract_change_from_text(self, text: str) -> float:
        """從文字中提取漲跌幅"""
        import re
        # 匹配 +X.XX% 或 -X.XX% 格式
        match = re.search(r"[+-]?\d+\.?\d*%", text)
        if match:
            change_str = match.group().replace("%", "")
            return float(change_str)
        return 0.0
