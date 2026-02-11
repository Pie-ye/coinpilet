"""
Project Chronos - 時光回溯投資模擬系統

基於多重人格 AI 代理的加密貨幣歷史投資模擬 MVP

模組結構:
- simulator: 回測模擬引擎
- portfolio: 資產組合追蹤
- trade: 交易執行
- debate: 辯論生成
- personas: 4 大投資人角色
- data: 歷史數據快取
- scripts: 執行腳本
"""

from .simulator import ChronosSimulator, SimulationConfig, run_simulation
from .portfolio import Portfolio, Position, PortfolioSnapshot, TradeRecord
from .trade import TradeExecutor, TradeDecision, TradeAction
from .debate import DebateGenerator, DailyDebate, DebateEntry

__all__ = [
    # Simulator
    "ChronosSimulator",
    "SimulationConfig",
    "run_simulation",
    # Portfolio
    "Portfolio",
    "Position",
    "PortfolioSnapshot",
    "TradeRecord",
    # Trade
    "TradeExecutor",
    "TradeDecision",
    "TradeAction",
    # Debate
    "DebateGenerator",
    "DailyDebate",
    "DebateEntry",
]
