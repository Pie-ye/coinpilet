"""
Agent 核心框架 - 實現 Agent Loop 與自我修復機制

整合 GitHub Copilot SDK 的 Tool Calling 能力，提供：
- 感知 → 規劃 → 執行 → 反思 的 Agent 循環
- 錯誤分析與自動重試 (最多 3 次)
- 結構化日誌記錄
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

from .tools import AgentTools, ToolResult, TOOL_DEFINITIONS

logger = structlog.get_logger(__name__)


class AgentStatus(Enum):
    """Agent 執行狀態"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ExecutionStep:
    """執行步驟記錄"""
    step_id: int
    action: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    result: Optional[ToolResult] = None
    thought: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_retry: bool = False
    retry_count: int = 0


@dataclass
class AgentResult:
    """Agent 執行結果"""
    success: bool
    output: Any = None
    steps: list[ExecutionStep] = field(default_factory=list)
    total_retries: int = 0
    error_message: Optional[str] = None
    execution_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "tool_name": s.tool_name,
                    "thought": s.thought,
                    "is_retry": s.is_retry,
                }
                for s in self.steps
            ],
            "total_retries": self.total_retries,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
        }


class AgentCore:
    """
    Agent 核心 - 具備自我修復能力的執行引擎
    
    特點:
        - 整合 Copilot SDK Tool Calling
        - 錯誤分析與自動修復 (最多 3 次重試)
        - 結構化執行日誌
        - 支援自訂工具擴展
    
    使用方式:
        agent = AgentCore()
        await agent.start()
        result = await agent.execute("繪製 BTC 過去 24 小時走勢圖")
        await agent.stop()
    """

    def __init__(
        self,
        model: str = "gemini-3-flash",
        max_retries: int = 3,
        working_dir: Optional[Path] = None,
        github_token: Optional[str] = None,
    ):
        """
        初始化 Agent Core
        
        Args:
            model: 使用的 AI 模型
            max_retries: 最大重試次數
            working_dir: 工作目錄
            github_token: GitHub Token
        """
        self.model = model
        self.max_retries = max_retries
        self.working_dir = working_dir or Path.cwd()
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        
        self.tools = AgentTools(working_dir=self.working_dir)
        self.client = None
        self.status = AgentStatus.IDLE
        self.log = logger.bind(component="AgentCore")

    async def start(self):
        """啟動 Agent (初始化 Copilot SDK)"""
        try:
            from copilot import CopilotClient

            self.log.info("正在初始化 Agent Core...", model=self.model)

            config = {
                "log_level": os.getenv("LOG_LEVEL", "info"),
                "auto_start": True,
                "auto_restart": True,
            }

            if self.github_token:
                config["github_token"] = self.github_token

            self.client = CopilotClient(config)
            await self.client.start()

            self.status = AgentStatus.IDLE
            self.log.info("Agent Core 已啟動")

        except ImportError:
            self.log.error("找不到 github-copilot-sdk")
            raise
        except Exception as e:
            self.log.error("Agent Core 啟動失敗", error=str(e))
            raise

    async def stop(self):
        """停止 Agent"""
        if self.client:
            await self.client.stop()
            self.status = AgentStatus.IDLE
            self.log.info("Agent Core 已停止")

    async def execute(
        self,
        task: str,
        context: Optional[dict] = None,
    ) -> AgentResult:
        """
        執行任務 (具備自我修復能力)
        
        Args:
            task: 任務描述
            context: 額外上下文資訊
            
        Returns:
            AgentResult: 執行結果
        """
        import time
        start_time = time.time()
        
        if not self.client:
            raise RuntimeError("Agent 尚未啟動，請先調用 start()")

        self.log.info("開始執行任務", task=task[:100])
        self.status = AgentStatus.THINKING

        steps: list[ExecutionStep] = []
        total_retries = 0
        step_id = 0

        try:
            # 建立會話
            session = await self.client.create_session(
                {
                    "model": self.model,
                    "streaming": False,
                    "system_prompt": self._build_system_prompt(),
                    "tools": TOOL_DEFINITIONS,
                }
            )

            # 建構初始訊息
            user_message = self._build_user_message(task, context)
            
            # Agent Loop
            max_iterations = 10
            iteration = 0
            last_error: Optional[str] = None
            retry_count = 0

            while iteration < max_iterations:
                iteration += 1
                step_id += 1

                # 如果有錯誤，加入重試上下文
                if last_error and retry_count < self.max_retries:
                    retry_count += 1
                    total_retries += 1
                    self.status = AgentStatus.RETRYING
                    
                    self.log.warning(
                        "嘗試自我修復",
                        retry_count=retry_count,
                        error=last_error[:200],
                    )
                    
                    user_message = self._build_retry_message(last_error, retry_count)
                    last_error = None

                # 發送請求
                self.status = AgentStatus.THINKING
                response = await session.send_and_wait({"prompt": user_message})

                # 檢查是否有 Tool Call
                if hasattr(response.data, "tool_calls") and response.data.tool_calls:
                    for tool_call in response.data.tool_calls:
                        step_id += 1
                        self.status = AgentStatus.EXECUTING
                        
                        tool_name = tool_call.name
                        tool_args = tool_call.arguments
                        
                        self.log.info(
                            "執行工具",
                            tool=tool_name,
                            args=str(tool_args)[:100],
                        )

                        # 執行工具
                        result = await self._execute_tool(tool_name, tool_args)
                        
                        step = ExecutionStep(
                            step_id=step_id,
                            action="tool_call",
                            tool_name=tool_name,
                            tool_args=tool_args,
                            result=result,
                            is_retry=retry_count > 0,
                            retry_count=retry_count,
                        )
                        steps.append(step)

                        # 檢查執行結果
                        if not result.success:
                            last_error = f"工具 {tool_name} 執行失敗:\n{result.stderr}"
                            
                            if retry_count >= self.max_retries:
                                self.status = AgentStatus.FAILED
                                return AgentResult(
                                    success=False,
                                    steps=steps,
                                    total_retries=total_retries,
                                    error_message=f"達到最大重試次數 ({self.max_retries}): {last_error}",
                                    execution_time=time.time() - start_time,
                                )
                        else:
                            # 成功，回傳結果給 AI
                            user_message = f"工具執行成功:\n```\n{result.stdout}\n```"
                            retry_count = 0  # 重置重試計數

                # 檢查是否完成
                elif hasattr(response.data, "content") and response.data.content:
                    content = response.data.content
                    
                    # 檢查是否為最終回應
                    if self._is_task_complete(content):
                        self.status = AgentStatus.SUCCESS
                        self.log.info("任務執行完成", steps=len(steps))
                        
                        return AgentResult(
                            success=True,
                            output=content,
                            steps=steps,
                            total_retries=total_retries,
                            execution_time=time.time() - start_time,
                        )
                    else:
                        # 繼續對話
                        step = ExecutionStep(
                            step_id=step_id,
                            action="thinking",
                            thought=content[:500],
                        )
                        steps.append(step)
                        user_message = "請繼續執行任務。"

            # 達到最大迭代
            self.status = AgentStatus.FAILED
            return AgentResult(
                success=False,
                steps=steps,
                total_retries=total_retries,
                error_message=f"達到最大迭代次數 ({max_iterations})",
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            self.status = AgentStatus.FAILED
            self.log.error("任務執行異常", error=str(e))
            return AgentResult(
                success=False,
                steps=steps,
                total_retries=total_retries,
                error_message=str(e),
                execution_time=time.time() - start_time,
            )

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> ToolResult:
        """執行指定工具"""
        tool_map = {
            "run_shell_command": lambda args: self.tools.run_shell_command(args["command"]),
            "python_repl": lambda args: self.tools.python_repl(args["code"]),
            "read_file": lambda args: self.tools.read_file(args["file_path"]),
            "write_file": lambda args: self.tools.write_file(args["file_path"], args["content"]),
            "list_directory": lambda args: self.tools.list_directory(args["dir_path"]),
        }

        if tool_name not in tool_map:
            return ToolResult(
                success=False,
                stderr=f"未知工具: {tool_name}",
                error_type="UnknownToolError",
            )

        try:
            return tool_map[tool_name](tool_args)
        except Exception as e:
            return ToolResult(
                success=False,
                stderr=str(e),
                error_type=type(e).__name__,
            )

    def _build_system_prompt(self) -> str:
        """建構 System Prompt"""
        return """你是 BAIA (Bitcoin Autonomous Intelligence Agent)，一個具備程式碼執行能力的自主代理。

## 你的能力
1. **程式碼執行**: 使用 python_repl 工具執行 Python 程式碼
2. **Shell 指令**: 使用 run_shell_command 執行系統指令
3. **檔案操作**: 使用 read_file / write_file 讀寫檔案
4. **自我修復**: 遇到錯誤時分析原因並修正程式碼

## 執行原則
1. 先規劃再執行：思考需要哪些步驟
2. 逐步執行：一次執行一個工具
3. 檢查結果：驗證每步執行是否成功
4. 錯誤處理：遇到錯誤時分析 stderr 並修正
5. 任務完成後明確回報結果

## 錯誤處理策略
- ModuleNotFoundError: 使用 pip install 安裝缺少的套件
- FileNotFoundError: 檢查路徑是否正確，必要時建立目錄
- SyntaxError: 檢查程式碼語法並修正
- 其他錯誤: 分析錯誤訊息，嘗試替代方案

## 輸出格式
任務完成時，請明確說明：
1. 執行了哪些步驟
2. 產出了哪些檔案
3. 最終結果摘要
"""

    def _build_user_message(self, task: str, context: Optional[dict] = None) -> str:
        """建構使用者訊息"""
        message = f"請執行以下任務：\n\n{task}"
        
        if context:
            message += f"\n\n## 額外上下文\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
        
        return message

    def _build_retry_message(self, error: str, retry_count: int) -> str:
        """建構重試訊息"""
        return f"""執行失敗，請分析錯誤並修正：

## 錯誤訊息 (第 {retry_count} 次重試)
```
{error}
```

請分析錯誤原因，修正程式碼後重新執行。"""

    def _is_task_complete(self, content: str) -> bool:
        """判斷任務是否完成"""
        completion_indicators = [
            "任務完成",
            "已完成",
            "執行成功",
            "圖片已生成",
            "檔案已保存",
            "已更新",
            "Task completed",
            "Successfully",
        ]
        return any(indicator in content for indicator in completion_indicators)


class MockAgentCore(AgentCore):
    """
    模擬 Agent Core - 用於測試
    
    不需要 Copilot SDK，直接執行預定義的操作
    """

    async def start(self):
        self.log.info("使用 MockAgentCore (模擬模式)")
        self.status = AgentStatus.IDLE

    async def stop(self):
        self.status = AgentStatus.IDLE

    async def execute(
        self,
        task: str,
        context: Optional[dict] = None,
    ) -> AgentResult:
        """模擬執行任務"""
        import time
        start_time = time.time()
        
        self.log.info("模擬執行任務", task=task[:100])
        
        # 簡單的任務路由
        if "K線" in task or "走勢圖" in task or "chart" in task.lower():
            # 直接執行繪圖
            from .analyst import AnalystAgent
            analyst = AnalystAgent(working_dir=self.working_dir)
            chart_result = await analyst.generate_chart()
            
            return AgentResult(
                success=chart_result.success,
                output={
                    "chart_path": str(chart_result.chart_path),
                    "current_price": chart_result.current_price,
                    "price_change_24h": chart_result.price_change_24h,
                },
                steps=[
                    ExecutionStep(
                        step_id=1,
                        action="generate_chart",
                        tool_name="python_repl",
                        thought="生成 BTC K 線圖",
                    )
                ],
                execution_time=time.time() - start_time,
            )
        
        # 預設回應
        return AgentResult(
            success=True,
            output="任務已完成（模擬模式）",
            execution_time=time.time() - start_time,
        )


def get_agent(
    model: str = "gemini-3-flash",
    use_mock: bool = False,
    **kwargs,
) -> AgentCore:
    """
    獲取 Agent 實例
    
    Args:
        model: AI 模型
        use_mock: 是否使用模擬模式
        **kwargs: 其他參數
        
    Returns:
        AgentCore 實例
    """
    if use_mock:
        return MockAgentCore(model=model, **kwargs)
    return AgentCore(model=model, **kwargs)
