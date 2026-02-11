"""
ChronosSimulator - 時光回溯投資模擬引擎

核心功能：
- 逐日遍歷歷史數據
- 為每位投資者組裝專屬的 Context
- 呼叫 AI 決策並執行交易
- 生成每日辯論
- 產出績效報告
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """模擬配置"""
    
    # 時間範圍
    start_date: date = date(2024, 1, 1)
    end_date: date = date(2024, 12, 31)
    
    # 資金設定
    initial_capital: float = 1_000_000.0
    
    # AI 模型
    model: str = "gemini-3-flash"
    
    # 執行模式
    use_ai: bool = True  # False 時使用規則決策
    generate_debates: bool = True  # 是否生成辯論
    
    # 輸出設定
    output_dir: str = "output/chronos"
    
    # 快取目錄
    news_cache_dir: str = "data/chronos_news"
    fear_greed_cache_file: str = "data/chronos_fear_greed.json"


@dataclass
class DailyResult:
    """每日模擬結果"""
    date: str
    btc_price: float
    btc_change_pct: float
    decisions: dict[str, dict]  # investor_id -> decision
    portfolio_values: dict[str, float]  # investor_id -> value
    debate_file: Optional[str] = None


class ChronosSimulator:
    """
    時光回溯投資模擬引擎
    
    使用方式：
        config = SimulationConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        
        simulator = ChronosSimulator(config)
        await simulator.run()
        
        # 或同步模式（使用規則決策）
        simulator.run_sync()
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None):
        """
        初始化模擬器
        
        Args:
            config: 模擬配置
        """
        self.config = config or SimulationConfig()
        
        # 初始化輸出目錄
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 組件 (延遲初始化)
        self.personas: dict = {}
        self.portfolios: dict = {}
        self.trade_executor = None
        self.debate_generator = None
        
        # 主 Agent (共用的 Copilot Client)
        self._main_agent = None
        
        # 數據緩存
        self._price_data: dict = {}
        self._technical_data: dict = {}
        self._news_cache = None
        self._fear_greed_cache = None
        
        # 結果記錄
        self.daily_results: list[DailyResult] = []
        self.btc_prices: dict[str, float] = {}
        
        # 統計信息（用於跟蹤超時和降級）
        self.stats = {
            "ai_decisions": 0,
            "rule_decisions": 0,
            "timeout_fallbacks": 0,
            "error_fallbacks": 0,
        }
        
        logger.info(f"ChronosSimulator 初始化完成")
        logger.info(f"  回測範圍: {self.config.start_date} ~ {self.config.end_date}")
        logger.info(f"  初始資金: ${self.config.initial_capital:,.0f}")
    
    def _init_components(self):
        """初始化所有組件"""
        from .portfolio import Portfolio
        from .trade import TradeExecutor
        from .debate import DebateGenerator
        from .personas import create_all_personas
        from .data.news_cache import NewsCache, NewsCacheConfig
        from .data.fear_greed_cache import FearGreedCache
        
        # 初始化投資者角色
        self.personas = create_all_personas(model=self.config.model)
        
        # 初始化投資組合
        self.portfolios = {
            persona_id: Portfolio(
                investor_id=persona_id,
                initial_capital=self.config.initial_capital,
            )
            for persona_id in self.personas.keys()
        }
        
        # 初始化交易執行器
        self.trade_executor = TradeExecutor()
        
        # 初始化辯論生成器
        if self.config.generate_debates:
            self.debate_generator = DebateGenerator(
                model=self.config.model,
                output_dir=str(self.output_dir / "debates"),
            )
        
        # 初始化數據緩存
        self._news_cache = NewsCache(NewsCacheConfig(
            data_dir=self.config.news_cache_dir,
        ))
        self._fear_greed_cache = FearGreedCache(
            cache_file=self.config.fear_greed_cache_file,
        )
        
        logger.info(f"已初始化 {len(self.personas)} 位投資者")
    
    def _load_price_data(self):
        """載入價格數據"""
        from src.collector.binance import BinanceClient
        from src.collector.cache import OHLCCache
        
        logger.info("載入 BTC 歷史價格數據...")
        
        # 嘗試從快取載入
        cache = OHLCCache(data_dir="data")
        cached_data = cache.load("1d")
        
        need_fetch = True
        
        if cached_data and cached_data.get("data"):
            # 建立日期到價格的映射
            for kline in cached_data["data"]:
                dt = datetime.fromisoformat(kline["datetime"])
                date_str = dt.strftime("%Y-%m-%d")
                self._price_data[date_str] = kline
            
            logger.info(f"從快取載入 {len(self._price_data)} 根 K 線")
            
            # 檢查快取日期範圍是否涵蓋回測需求
            start_str = self.config.start_date.strftime("%Y-%m-%d")
            end_str = self.config.end_date.strftime("%Y-%m-%d")
            
            if start_str in self._price_data and end_str in self._price_data:
                need_fetch = False
                logger.info(f"快取數據涵蓋回測範圍: {start_str} ~ {end_str}")
            else:
                logger.info(f"快取數據不涵蓋回測範圍，需要重新獲取...")
                self._price_data = {}  # 清空快取數據
        
        if need_fetch:
            # 從 Binance 獲取指定日期範圍
            logger.info(f"從 Binance 獲取 {self.config.start_date} ~ {self.config.end_date} 歷史數據...")
            client = BinanceClient()
            
            # 提前幾天抓取，確保技術指標計算有足夠數據
            fetch_start = datetime.combine(self.config.start_date, datetime.min.time()) - timedelta(days=250)
            fetch_end = datetime.combine(self.config.end_date, datetime.max.time())
            
            klines = client.get_historical_klines(
                interval="1d",
                start_date=fetch_start,
                end_date=fetch_end,
            )
            
            for kline in klines:
                date_str = kline.date_str
                self._price_data[date_str] = kline.to_dict()
            
            logger.info(f"獲取 {len(self._price_data)} 根 K 線")
    
    def _get_price_for_date(self, target_date: date) -> Optional[dict]:
        """取得特定日期的價格數據"""
        date_str = target_date.strftime("%Y-%m-%d")
        return self._price_data.get(date_str)
    
    def _calculate_technical_indicators(self, target_date: date) -> dict:
        """計算特定日期的技術指標"""
        from src.collector.technical import TechnicalAnalyzer
        
        date_str = target_date.strftime("%Y-%m-%d")
        
        # 檢查快取
        if date_str in self._technical_data:
            return self._technical_data[date_str]
        
        # 收集該日期之前的所有 K 線
        klines = []
        for d_str in sorted(self._price_data.keys()):
            if d_str <= date_str:
                klines.append(self._price_data[d_str])
        
        if len(klines) < 50:  # 需要足夠數據計算指標
            return {}
        
        # 計算技術指標
        try:
            analyzer = TechnicalAnalyzer()
            # 轉換為 OHLCData 格式
            from src.collector.binance import OHLCData
            ohlc_list = [
                OHLCData(
                    timestamp=k.get("timestamp", 0),
                    open=float(k.get("open", 0)),
                    high=float(k.get("high", 0)),
                    low=float(k.get("low", 0)),
                    close=float(k.get("close", 0)),
                    volume=float(k.get("volume", 0)),
                    close_time=k.get("close_time", 0),
                    quote_volume=float(k.get("quote_volume", 0)),
                    trades=k.get("trades", 0),
                )
                for k in klines
            ]
            
            indicators = analyzer.calculate(ohlc_list)
            
            result = {
                "rsi": indicators.rsi.value if indicators.rsi else None,
                "rsi_signal": indicators.rsi.signal if indicators.rsi else None,
                "macd_signal": indicators.macd.trend_signal if indicators.macd else None,
                "ma_50": indicators.moving_averages.sma_50 if indicators.moving_averages else None,
                "ma_200": indicators.moving_averages.sma_200 if indicators.moving_averages else None,
                "bb_position": indicators.bollinger_bands.position if indicators.bollinger_bands else None,
                "overall_signal": indicators.overall_signal,
            }
            
            self._technical_data[date_str] = result
            return result
            
        except Exception as e:
            logger.warning(f"計算技術指標失敗 ({date_str}): {e}")
            return {}
    
    def _build_context_for_persona(
        self,
        persona_id: str,
        target_date: date,
        price_data: dict,
        tech_indicators: dict,
    ):
        """為特定投資者建構市場上下文"""
        from .personas.base import MarketContext
        
        persona = self.personas[persona_id]
        portfolio = self.portfolios[persona_id]
        config = persona.config
        
        # 基本價格資訊
        btc_price = price_data.get("close", 0)
        btc_open = price_data.get("open", btc_price)
        btc_change_pct = ((btc_price - btc_open) / btc_open * 100) if btc_open > 0 else 0
        
        # 取得新聞（如果角色需要）
        news_headlines = []
        if config.use_news:
            news_items = self._news_cache.load_date(target_date)
            news_headlines = [item.title for item in news_items]
        
        # 取得 Fear & Greed（如果角色需要）
        fear_greed_value = None
        fear_greed_label = None
        if config.use_fear_greed:
            fg_item = self._fear_greed_cache.get_by_date(target_date)
            if fg_item:
                fear_greed_value = fg_item.value
                fear_greed_label = fg_item.sentiment_zh
        
        # 建構上下文
        context = MarketContext(
            current_date=target_date.strftime("%Y-%m-%d"),
            btc_price=btc_price,
            btc_change_pct=btc_change_pct,
            # 技術指標
            rsi=tech_indicators.get("rsi") if config.use_technical else None,
            rsi_signal=tech_indicators.get("rsi_signal") if config.use_technical else None,
            macd_signal=tech_indicators.get("macd_signal") if config.use_technical else None,
            ma_50=tech_indicators.get("ma_50") if config.use_technical else None,
            ma_200=tech_indicators.get("ma_200") if config.use_technical else None,
            bb_position=tech_indicators.get("bb_position") if config.use_technical else None,
            overall_technical=tech_indicators.get("overall_signal") if config.use_technical else None,
            # 市場情緒
            fear_greed_value=fear_greed_value,
            fear_greed_label=fear_greed_label,
            # 新聞
            news_headlines=news_headlines,
            # 投資組合狀態
            portfolio_value=portfolio.get_total_value(btc_price),
            usd_balance=portfolio.usd_balance,
            btc_quantity=portfolio.btc_position.quantity,
            return_pct=portfolio.get_return_pct(btc_price),
        )
        
        return context
    
    async def _init_main_agent(self):
        """初始化主 Agent (共用的 Copilot Client)"""
        try:
            from copilot import CopilotClient
            
            self._main_agent = CopilotClient()
            await self._main_agent.start()
            logger.info(f"主 Agent 已啟動 (模型: {self.config.model})")
            
        except ImportError:
            logger.error("找不到 github-copilot-sdk，請執行: pip install github-copilot-sdk")
            raise
        except Exception as e:
            logger.error(f"主 Agent 啟動失敗: {e}", exc_info=True)
            raise
    
    async def _get_decision_from_main_agent(
        self, 
        persona, 
        context,
    ) -> str:
        """
        使用主 Agent 為特定投資人取得決策
        
        Args:
            persona: 投資人角色
            context: 市場上下文
            
        Returns:
            str: AI 回應 (JSON 格式)
        """
        if not self._main_agent:
            raise RuntimeError("主 Agent 未啟動")
        
        # 建構 prompt（使用簡化版，降低超時風險）
        system_prompt = persona.build_system_prompt(context.current_date)
        user_prompt = persona.build_decision_prompt_compact(context)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            session = await self._main_agent.create_session({
                "model": self.config.model,
            })
            
            logger.debug(f"{persona.config.name_zh} 開始 AI 決策 (日期: {context.current_date})")
            
            response = await session.send_and_wait(
                {"prompt": full_prompt},
                timeout=300.0  # 5 分鐘超時（與 main.py 保持一致）
            )
            
            logger.debug(f"{persona.config.name_zh} AI 決策完成")
            self.stats["ai_decisions"] += 1
            return response.data.content
            
        except asyncio.TimeoutError:
            self.stats["timeout_fallbacks"] += 1
            logger.error(
                f"⏰ {persona.config.name_zh} AI 決策超時 (>300s) "
                f"[日期: {context.current_date}, 模型: {self.config.model}]"
            )
            # 降級到規則決策而不是終止模擬
            logger.info(f"   ↳ 降級為規則決策以繼續模擬 (超時次數: {self.stats['timeout_fallbacks']})")
            self.stats["rule_decisions"] += 1
            return persona.make_decision_sync(context)
        except Exception as e:
            self.stats["error_fallbacks"] += 1
            logger.error(
                f"❌ {persona.config.name_zh} AI 決策失敗: {type(e).__name__}: {e} "
                f"[日期: {context.current_date}]"
            )
            # 降級到規則決策而不是終止模擬
            logger.info(f"   ↳ 降級為規則決策以繼續模擬 (錯誤次數: {self.stats['error_fallbacks']})")
            self.stats["rule_decisions"] += 1
            return persona.make_decision_sync(context)
            logger.info(f"   ↳ 降級為規則決策以繼續模擬")
            return persona.make_decision_sync(context)
        except Exception as e:
            logger.error(
                f"❌ {persona.config.name_zh} AI 決策失敗: {type(e).__name__}: {e} "
                f"[日期: {context.current_date}]"
            )
            # 降級到規則決策而不是終止模擬
            logger.info(f"   ↳ 降級為規則決策以繼續模擬")
            return persona.make_decision_sync(context)
    
    async def run(self, progress_callback: Optional[Callable] = None):
        """
        執行完整模擬 (異步版本，使用 AI)
        
        Args:
            progress_callback: 進度回調 (current_day, total_days, date)
        """
        self._init_components()
        self._load_price_data()
        
        # 確保 Fear & Greed 數據已載入
        self._fear_greed_cache.ensure_loaded()
        
        # 啟動主 Agent (共用的 Copilot Client)
        if self.config.use_ai:
            await self._init_main_agent()
            
            if self.debate_generator:
                await self.debate_generator.start()
        
        try:
            await self._run_simulation(progress_callback)
        finally:
            # 停止主 Agent
            if self.config.use_ai and self._main_agent:
                try:
                    await self._main_agent.stop()
                except Exception:
                    pass
                self._main_agent = None
                
                if self.debate_generator:
                    await self.debate_generator.stop()
        
        # 生成報告
        self._generate_reports()
    
    def run_sync(self, progress_callback: Optional[Callable] = None):
        """
        執行完整模擬 (同步版本，使用規則決策)
        
        Args:
            progress_callback: 進度回調 (current_day, total_days, date)
        """
        self._init_components()
        self._load_price_data()
        
        # 確保 Fear & Greed 數據已載入
        self._fear_greed_cache.ensure_loaded()
        
        # 執行模擬
        self._run_simulation_sync(progress_callback)
        
        # 生成報告
        self._generate_reports()
    
    async def _run_simulation(self, progress_callback: Optional[Callable] = None):
        """執行模擬主迴圈 (異步)"""
        total_days = (self.config.end_date - self.config.start_date).days + 1
        current_date = self.config.start_date
        day_count = 0
        
        logger.info("=" * 60)
        logger.info("開始回測模擬")
        logger.info("=" * 60)
        
        while current_date <= self.config.end_date:
            day_count += 1
            date_str = current_date.strftime("%Y-%m-%d")
            
            if progress_callback:
                progress_callback(day_count, total_days, current_date)
            
            # 取得價格數據
            price_data = self._get_price_for_date(current_date)
            if not price_data:
                logger.warning(f"[{date_str}] 無價格數據，跳過")
                current_date += timedelta(days=1)
                continue
            
            btc_price = price_data.get("close", 0)
            btc_open = price_data.get("open", btc_price)
            btc_change_pct = ((btc_price - btc_open) / btc_open * 100) if btc_open > 0 else 0
            
            # 記錄 BTC 價格
            self.btc_prices[date_str] = btc_price
            
            logger.info(f"[{day_count}/{total_days}] {date_str} | BTC ${btc_price:,.0f} ({btc_change_pct:+.2f}%)")
            
            # 計算技術指標
            tech_indicators = self._calculate_technical_indicators(current_date)
            
            # 收集所有決策 - 使用主 Agent 依序為每位投資人決策
            decisions = {}
            portfolio_values = {}
            
            if self.config.use_ai:
                # 使用主 Agent 為每位投資人取得決策
                for persona_id, persona in self.personas.items():
                    context = self._build_context_for_persona(
                        persona_id, current_date, price_data, tech_indicators
                    )
                    
                    # 取得決策（內部已處理超時和降級）
                    response = await self._get_decision_from_main_agent(
                        persona, context
                    )
                    
                    # 解析並執行決策
                    decision = self.trade_executor.parse_decision(response)
                    self.trade_executor.execute(
                        decision,
                        self.portfolios[persona_id],
                        date_str,
                        btc_price,
                    )
                    
                    # 記錄快照
                    self.portfolios[persona_id].take_snapshot(date_str, btc_price)
                    
                    decisions[persona_id] = decision.to_dict()
                    portfolio_values[persona_id] = self.portfolios[persona_id].get_total_value(btc_price)
                    
                    logger.info(f"  {persona.config.emoji} {persona.config.name_zh}: {decision.action.value} | ${portfolio_values[persona_id]:,.0f}")
            else:
                # 同步模式：順序執行
                for persona_id, persona in self.personas.items():
                    context = self._build_context_for_persona(
                        persona_id, current_date, price_data, tech_indicators
                    )
                    response = persona.make_decision_sync(context)
                    
                    # 解析並執行決策
                    decision = self.trade_executor.parse_decision(response)
                    self.trade_executor.execute(
                        decision,
                        self.portfolios[persona_id],
                        date_str,
                        btc_price,
                    )
                    
                    # 記錄快照
                    self.portfolios[persona_id].take_snapshot(date_str, btc_price)
                    
                    decisions[persona_id] = decision.to_dict()
                    portfolio_values[persona_id] = self.portfolios[persona_id].get_total_value(btc_price)
            
            # 生成辯論
            debate_file = None
            if self.config.generate_debates and self.debate_generator:
                trades_summary = {
                    pid: {
                        **decisions[pid],
                        "portfolio_value": portfolio_values[pid],
                        "return_pct": self.portfolios[pid].get_return_pct(btc_price),
                    }
                    for pid in self.personas.keys()
                }
                
                if self.config.use_ai:
                    debate = await self.debate_generator.generate(
                        date=date_str,
                        btc_price=btc_price,
                        btc_change_pct=btc_change_pct,
                        trades_summary=trades_summary,
                    )
                else:
                    debate = self.debate_generator.generate_sync(
                        date=date_str,
                        btc_price=btc_price,
                        btc_change_pct=btc_change_pct,
                        trades_summary=trades_summary,
                    )
                
                debate_file = str(debate.save())
            
            # 記錄每日結果
            self.daily_results.append(DailyResult(
                date=date_str,
                btc_price=btc_price,
                btc_change_pct=btc_change_pct,
                decisions=decisions,
                portfolio_values=portfolio_values,
                debate_file=debate_file,
            ))
            
            current_date += timedelta(days=1)
        
        logger.info("=" * 60)
        logger.info("回測模擬完成")
        logger.info("=" * 60)
    
    def _run_simulation_sync(self, progress_callback: Optional[Callable] = None):
        """執行模擬主迴圈 (同步)"""
        total_days = (self.config.end_date - self.config.start_date).days + 1
        current_date = self.config.start_date
        day_count = 0
        
        logger.info("=" * 60)
        logger.info("開始回測模擬 (同步模式)")
        logger.info("=" * 60)
        
        while current_date <= self.config.end_date:
            day_count += 1
            date_str = current_date.strftime("%Y-%m-%d")
            
            if progress_callback:
                progress_callback(day_count, total_days, current_date)
            
            # 取得價格數據
            price_data = self._get_price_for_date(current_date)
            if not price_data:
                logger.warning(f"[{date_str}] 無價格數據，跳過")
                current_date += timedelta(days=1)
                continue
            
            btc_price = price_data.get("close", 0)
            btc_open = price_data.get("open", btc_price)
            btc_change_pct = ((btc_price - btc_open) / btc_open * 100) if btc_open > 0 else 0
            
            # 記錄 BTC 價格
            self.btc_prices[date_str] = btc_price
            
            if day_count % 30 == 0 or day_count == 1:  # 每 30 天輸出一次進度
                logger.info(f"[{day_count}/{total_days}] {date_str} | BTC ${btc_price:,.0f}")
            
            # 計算技術指標
            tech_indicators = self._calculate_technical_indicators(current_date)
            
            # 收集所有決策
            decisions = {}
            portfolio_values = {}
            
            for persona_id, persona in self.personas.items():
                # 建構上下文
                context = self._build_context_for_persona(
                    persona_id, current_date, price_data, tech_indicators
                )
                
                # 取得決策（使用規則）
                response = persona.make_decision_sync(context)
                
                # 解析並執行決策
                decision = self.trade_executor.parse_decision(response)
                self.trade_executor.execute(
                    decision,
                    self.portfolios[persona_id],
                    date_str,
                    btc_price,
                )
                
                # 記錄快照
                self.portfolios[persona_id].take_snapshot(date_str, btc_price)
                
                decisions[persona_id] = decision.to_dict()
                portfolio_values[persona_id] = self.portfolios[persona_id].get_total_value(btc_price)
            
            # 生成辯論（使用預設模板）
            debate_file = None
            if self.config.generate_debates and self.debate_generator:
                trades_summary = {
                    pid: {
                        **decisions[pid],
                        "portfolio_value": portfolio_values[pid],
                        "return_pct": self.portfolios[pid].get_return_pct(btc_price),
                    }
                    for pid in self.personas.keys()
                }
                
                debate = self.debate_generator.generate_sync(
                    date=date_str,
                    btc_price=btc_price,
                    btc_change_pct=btc_change_pct,
                    trades_summary=trades_summary,
                )
                debate_file = str(debate.save())
            
            # 記錄每日結果
            self.daily_results.append(DailyResult(
                date=date_str,
                btc_price=btc_price,
                btc_change_pct=btc_change_pct,
                decisions=decisions,
                portfolio_values=portfolio_values,
                debate_file=debate_file,
            ))
            
            current_date += timedelta(days=1)
        
        logger.info("=" * 60)
        logger.info("回測模擬完成")
        logger.info("=" * 60)
    
    def _generate_reports(self):
        """生成績效報告"""
        logger.info("生成績效報告...")
        
        # 1. 儲存每日結果 JSON
        results_file = self.output_dir / "daily_results.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "date": r.date,
                        "btc_price": r.btc_price,
                        "btc_change_pct": r.btc_change_pct,
                        "decisions": r.decisions,
                        "portfolio_values": r.portfolio_values,
                    }
                    for r in self.daily_results
                ],
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"每日結果已儲存: {results_file}")
        
        # 2. 儲存交易日誌 CSV
        for persona_id, portfolio in self.portfolios.items():
            csv_file = self.output_dir / f"transactions_{persona_id}.csv"
            with open(csv_file, "w", encoding="utf-8") as f:
                f.write(portfolio.export_trades_csv())
            logger.info(f"交易日誌已儲存: {csv_file}")
        
        # 3. 生成績效摘要
        self._print_performance_summary()
        
        # 4. 生成績效圖表
        self._generate_performance_chart()
    
    def _print_performance_summary(self):
        """輸出績效摘要"""
        if not self.daily_results:
            return
        
        last_result = self.daily_results[-1]
        first_price = self.daily_results[0].btc_price
        last_price = last_result.btc_price
        btc_return = ((last_price - first_price) / first_price) * 100
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 績效摘要")
        logger.info("=" * 60)
        logger.info(f"回測期間: {self.config.start_date} ~ {self.config.end_date}")
        logger.info(f"BTC 漲跌: ${first_price:,.0f} → ${last_price:,.0f} ({btc_return:+.2f}%)")
        
        # 顯示決策統計
        if self.config.use_ai:
            total_decisions = self.stats["ai_decisions"] + self.stats["rule_decisions"]
            if total_decisions > 0:
                ai_pct = (self.stats["ai_decisions"] / total_decisions) * 100
                logger.info("")
                logger.info(f"🤖 AI 決策統計:")
                logger.info(f"   成功: {self.stats['ai_decisions']} 次 ({ai_pct:.1f}%)")
                logger.info(f"   降級: {self.stats['rule_decisions']} 次 ({100-ai_pct:.1f}%)")
                if self.stats["timeout_fallbacks"] > 0:
                    logger.info(f"   超時: {self.stats['timeout_fallbacks']} 次")
                if self.stats["error_fallbacks"] > 0:
                    logger.info(f"   錯誤: {self.stats['error_fallbacks']} 次")
        
        logger.info("")
        
        # 各投資者績效
        results = []
        for persona_id, portfolio in self.portfolios.items():
            final_value = last_result.portfolio_values.get(persona_id, 0)
            return_pct = ((final_value - self.config.initial_capital) / self.config.initial_capital) * 100
            
            results.append({
                "id": persona_id,
                "emoji": self.personas[persona_id].config.emoji,
                "name": self.personas[persona_id].config.name_zh,
                "final_value": final_value,
                "return_pct": return_pct,
                "beat_btc": return_pct > btc_return,
            })
        
        # 按報酬率排序
        results.sort(key=lambda x: x["return_pct"], reverse=True)
        
        for i, r in enumerate(results, 1):
            beat_emoji = "✅" if r["beat_btc"] else "❌"
            logger.info(
                f"#{i} {r['emoji']} {r['name']}: "
                f"${r['final_value']:,.0f} ({r['return_pct']:+.2f}%) {beat_emoji}"
            )
        
        logger.info("")
        logger.info("✅ = 跑贏 BTC | ❌ = 輸給 BTC")
        logger.info("=" * 60)
    
    def _generate_performance_chart(self):
        """生成績效圖表"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            
            # 設定中文字體
            plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial Unicode MS']
            plt.rcParams['axes.unicode_minus'] = False
            
            fig, ax = plt.subplots(figsize=(14, 8))
            
            # 準備數據
            dates = [datetime.strptime(r.date, "%Y-%m-%d") for r in self.daily_results]
            
            # BTC 價格變化率（正規化到初始資金）
            first_price = self.daily_results[0].btc_price
            btc_values = [
                (r.btc_price / first_price) * self.config.initial_capital
                for r in self.daily_results
            ]
            
            # 繪製 BTC 基準線
            ax.plot(dates, btc_values, label="BTC (HODL)", color="gold", linewidth=2.5, linestyle="--")
            
            # 繪製各投資者的淨值曲線
            colors = {
                "guardian": "#2196F3",  # 藍色
                "degen": "#FF5722",  # 橙色
                "quant": "#9C27B0",  # 紫色
                "strategist": "#4CAF50",  # 綠色
            }
            
            # 使用純文字標籤避免 emoji 字型問題
            display_names = {
                "guardian": "Guardian 保守派",
                "degen": "Degen 激進派",
                "quant": "Quant 量化派",
                "strategist": "Strategist 宏觀派",
            }
            
            for persona_id in self.personas.keys():
                values = [r.portfolio_values.get(persona_id, 0) for r in self.daily_results]
                label = display_names.get(persona_id, persona_id)
                
                ax.plot(
                    dates, values,
                    label=label,
                    color=colors.get(persona_id, "gray"),
                    linewidth=1.8,
                )
            
            # 設定圖表
            ax.set_title("Project Chronos - 投資績效對決", fontsize=16, fontweight="bold")
            ax.set_xlabel("日期", fontsize=12)
            ax.set_ylabel("資產淨值 (USD)", fontsize=12)
            
            # 格式化 Y 軸
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x/1e6:.2f}M"))
            
            # 格式化 X 軸
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            plt.xticks(rotation=45)
            
            # 添加網格
            ax.grid(True, alpha=0.3)
            
            # 添加圖例
            ax.legend(loc="upper left", fontsize=10)
            
            # 添加初始資金參考線
            ax.axhline(y=self.config.initial_capital, color="gray", linestyle=":", alpha=0.5)
            
            plt.tight_layout()
            
            # 儲存圖表
            chart_file = self.output_dir / "performance.png"
            plt.savefig(chart_file, dpi=150, bbox_inches="tight")
            plt.close()
            
            logger.info(f"績效圖表已儲存: {chart_file}")
            
        except ImportError:
            logger.warning("matplotlib 未安裝，跳過圖表生成")
        except Exception as e:
            logger.error(f"生成圖表失敗: {e}")


# 便捷函數
def run_simulation(
    start_date: date = date(2024, 1, 1),
    end_date: date = date(2024, 12, 31),
    use_ai: bool = False,
    **kwargs,
):
    """
    執行模擬的便捷函數
    
    Args:
        start_date: 開始日期
        end_date: 結束日期
        use_ai: 是否使用 AI (False 則使用規則決策)
        **kwargs: 其他配置參數
    """
    config = SimulationConfig(
        start_date=start_date,
        end_date=end_date,
        use_ai=use_ai,
        **kwargs,
    )
    
    simulator = ChronosSimulator(config)
    
    if use_ai:
        asyncio.run(simulator.run())
    else:
        simulator.run_sync()
    
    return simulator
