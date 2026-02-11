"""
BAIA Agent 模組 - Bitcoin Autonomous Intelligence Agent

提供程式碼執行、自我修復、專案維護能力的自主代理系統。

模組結構:
    - tools: Agent 工具層 (Shell, REPL, File)
    - core: Agent 核心框架 (Loop, Self-Healing)
    - analyst: 繪圖 Agent (K 線圖生成)
    - maintainer: 專案管家 (README 維護)
"""

from .tools import AgentTools, ToolResult
from .core import AgentCore
from .analyst import AnalystAgent, ChartResult
from .maintainer import MaintainerAgent

__all__ = [
    "AgentTools",
    "ToolResult",
    "AgentCore",
    "AnalystAgent",
    "ChartResult",
    "MaintainerAgent",
]
