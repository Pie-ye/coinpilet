"""
Agent 工具層 - 提供 Shell 執行、Python REPL、檔案操作能力

這些工具供 Agent Core 調用，支援程式碼執行與自我修復機制。
"""

import os
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ToolResult:
    """工具執行結果"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error_type: Optional[str] = None
    execution_time: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "error_type": self.error_type,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
        }


class AgentTools:
    """
    Agent 工具箱 - 提供執行環境操作能力
    
    工具列表:
        - run_shell_command: 執行 Shell 指令
        - python_repl: 執行 Python 程式碼
        - read_file: 讀取檔案內容
        - write_file: 寫入檔案內容
        - list_directory: 列出目錄內容
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 30,
        max_output_size: int = 50000,
    ):
        """
        初始化工具箱
        
        Args:
            working_dir: 工作目錄 (預設為當前目錄)
            timeout: 指令執行超時秒數 (預設 30 秒)
            max_output_size: 最大輸出字元數 (預設 50000)
        """
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.log = logger.bind(component="AgentTools")

    def run_shell_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[Path] = None,
    ) -> ToolResult:
        """
        執行 Shell 指令
        
        Args:
            command: 要執行的指令
            timeout: 超時秒數 (覆蓋預設值)
            cwd: 工作目錄 (覆蓋預設值)
            
        Returns:
            ToolResult: 執行結果
        """
        import time
        start_time = time.time()
        timeout = timeout or self.timeout
        cwd = cwd or self.working_dir

        self.log.info("執行 Shell 指令", command=command, cwd=str(cwd))

        try:
            # Windows 使用 PowerShell
            if sys.platform == "win32":
                result = subprocess.run(
                    ["powershell", "-Command", command],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
            else:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                )

            execution_time = time.time() - start_time
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)

            success = result.returncode == 0

            if success:
                self.log.info("Shell 指令執行成功", return_code=result.returncode)
            else:
                self.log.warning(
                    "Shell 指令執行失敗",
                    return_code=result.returncode,
                    stderr=stderr[:200],
                )

            return ToolResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                return_code=result.returncode,
                execution_time=execution_time,
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            self.log.error("Shell 指令超時", timeout=timeout)
            return ToolResult(
                success=False,
                stderr=f"指令執行超時 ({timeout} 秒)",
                error_type="TimeoutError",
                execution_time=execution_time,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            self.log.error("Shell 指令執行異常", error=str(e))
            return ToolResult(
                success=False,
                stderr=str(e),
                error_type=type(e).__name__,
                execution_time=execution_time,
            )

    def python_repl(
        self,
        code: str,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        """
        執行 Python 程式碼
        
        Args:
            code: Python 程式碼
            timeout: 超時秒數
            
        Returns:
            ToolResult: 執行結果，包含 stdout/stderr
        """
        import time
        start_time = time.time()
        timeout = timeout or self.timeout

        self.log.info("執行 Python 程式碼", code_length=len(code))

        # 建立暫存檔案
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(code)
            temp_file = f.name

        try:
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            execution_time = time.time() - start_time
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)

            success = result.returncode == 0

            if success:
                self.log.info("Python 程式碼執行成功")
            else:
                # 解析錯誤類型
                error_type = self._parse_python_error(stderr)
                self.log.warning(
                    "Python 程式碼執行失敗",
                    error_type=error_type,
                    stderr=stderr[:300],
                )
                return ToolResult(
                    success=False,
                    stdout=stdout,
                    stderr=stderr,
                    return_code=result.returncode,
                    error_type=error_type,
                    execution_time=execution_time,
                )

            return ToolResult(
                success=True,
                stdout=stdout,
                stderr=stderr,
                return_code=result.returncode,
                execution_time=execution_time,
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            self.log.error("Python 程式碼超時", timeout=timeout)
            return ToolResult(
                success=False,
                stderr=f"程式碼執行超時 ({timeout} 秒)",
                error_type="TimeoutError",
                execution_time=execution_time,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            self.log.error("Python 程式碼執行異常", error=str(e))
            return ToolResult(
                success=False,
                stderr=traceback.format_exc(),
                error_type=type(e).__name__,
                execution_time=execution_time,
            )
        finally:
            # 清理暫存檔案
            try:
                os.unlink(temp_file)
            except Exception:
                pass

    def read_file(self, file_path: str | Path) -> ToolResult:
        """
        讀取檔案內容
        
        Args:
            file_path: 檔案路徑
            
        Returns:
            ToolResult: 執行結果，stdout 為檔案內容
        """
        file_path = Path(file_path)
        self.log.info("讀取檔案", file_path=str(file_path))

        try:
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    stderr=f"檔案不存在: {file_path}",
                    error_type="FileNotFoundError",
                )

            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    stderr=f"路徑不是檔案: {file_path}",
                    error_type="IsADirectoryError",
                )

            content = file_path.read_text(encoding="utf-8")
            content = self._truncate_output(content)

            self.log.info("檔案讀取成功", size=len(content))
            return ToolResult(
                success=True,
                stdout=content,
                metadata={"file_path": str(file_path), "size": len(content)},
            )

        except UnicodeDecodeError:
            # 嘗試用二進制讀取
            try:
                content = file_path.read_bytes()
                return ToolResult(
                    success=True,
                    stdout=f"[二進制檔案, 大小: {len(content)} bytes]",
                    metadata={"file_path": str(file_path), "binary": True},
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    stderr=str(e),
                    error_type="UnicodeDecodeError",
                )
        except Exception as e:
            self.log.error("檔案讀取失敗", error=str(e))
            return ToolResult(
                success=False,
                stderr=str(e),
                error_type=type(e).__name__,
            )

    def write_file(
        self,
        file_path: str | Path,
        content: str,
        create_dirs: bool = True,
    ) -> ToolResult:
        """
        寫入檔案內容
        
        Args:
            file_path: 檔案路徑
            content: 檔案內容
            create_dirs: 是否自動建立目錄
            
        Returns:
            ToolResult: 執行結果
        """
        file_path = Path(file_path)
        self.log.info("寫入檔案", file_path=str(file_path), content_length=len(content))

        try:
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding="utf-8")

            self.log.info("檔案寫入成功", size=len(content))
            return ToolResult(
                success=True,
                stdout=f"已寫入 {len(content)} 字元至 {file_path}",
                metadata={"file_path": str(file_path), "size": len(content)},
            )

        except Exception as e:
            self.log.error("檔案寫入失敗", error=str(e))
            return ToolResult(
                success=False,
                stderr=str(e),
                error_type=type(e).__name__,
            )

    def list_directory(self, dir_path: str | Path) -> ToolResult:
        """
        列出目錄內容
        
        Args:
            dir_path: 目錄路徑
            
        Returns:
            ToolResult: 執行結果，stdout 為目錄內容列表
        """
        dir_path = Path(dir_path)
        self.log.info("列出目錄", dir_path=str(dir_path))

        try:
            if not dir_path.exists():
                return ToolResult(
                    success=False,
                    stderr=f"目錄不存在: {dir_path}",
                    error_type="FileNotFoundError",
                )

            if not dir_path.is_dir():
                return ToolResult(
                    success=False,
                    stderr=f"路徑不是目錄: {dir_path}",
                    error_type="NotADirectoryError",
                )

            items = []
            for item in sorted(dir_path.iterdir()):
                if item.is_dir():
                    items.append(f"{item.name}/")
                else:
                    items.append(item.name)

            output = "\n".join(items)
            self.log.info("目錄列出成功", item_count=len(items))

            return ToolResult(
                success=True,
                stdout=output,
                metadata={"dir_path": str(dir_path), "item_count": len(items)},
            )

        except Exception as e:
            self.log.error("目錄列出失敗", error=str(e))
            return ToolResult(
                success=False,
                stderr=str(e),
                error_type=type(e).__name__,
            )

    def _truncate_output(self, text: str) -> str:
        """截斷過長的輸出"""
        if len(text) > self.max_output_size:
            half = self.max_output_size // 2
            return (
                text[:half]
                + f"\n\n... [已截斷 {len(text) - self.max_output_size} 字元] ...\n\n"
                + text[-half:]
            )
        return text

    def _parse_python_error(self, stderr: str) -> Optional[str]:
        """解析 Python 錯誤類型"""
        common_errors = [
            "ModuleNotFoundError",
            "ImportError",
            "SyntaxError",
            "NameError",
            "TypeError",
            "ValueError",
            "AttributeError",
            "KeyError",
            "IndexError",
            "FileNotFoundError",
            "PermissionError",
            "ZeroDivisionError",
            "RuntimeError",
        ]
        for error in common_errors:
            if error in stderr:
                return error
        return "UnknownError"


# 工具定義 (供 Copilot SDK Tool Calling 使用)
TOOL_DEFINITIONS = [
    {
        "name": "run_shell_command",
        "description": "執行 Shell/PowerShell 指令。用於安裝套件、執行系統命令、操作 Git 等。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要執行的 Shell 指令",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "python_repl",
        "description": "執行 Python 程式碼。用於數據分析、繪圖、計算等任務。程式碼會在獨立進程中執行。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要執行的 Python 程式碼",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "read_file",
        "description": "讀取檔案內容。支援文字檔案，二進制檔案會回傳大小資訊。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "檔案的絕對或相對路徑",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "寫入內容到檔案。會自動建立不存在的目錄。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "檔案的絕對或相對路徑",
                },
                "content": {
                    "type": "string",
                    "description": "要寫入的檔案內容",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "列出目錄中的所有檔案和子目錄。",
        "parameters": {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "目錄的絕對或相對路徑",
                },
            },
            "required": ["dir_path"],
        },
    },
]
