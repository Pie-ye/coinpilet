"""
CoinPilot AI - FastAPI Web 伺服器

提供簡易 Web GUI 控制介面：
- 資料採集
- 查看報告
- 發布到 GitHub
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# 設定路徑
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# ============================================
# FastAPI App
# ============================================

app = FastAPI(
    title="CoinPilot AI",
    description="加密貨幣分析與出版系統 Web 控制台",
    version="1.0.0",
)

# ============================================
# 資料模型
# ============================================

class TaskStatus(BaseModel):
    """任務狀態"""
    task: str
    status: str  # running, success, error
    message: str
    timestamp: str
    details: Optional[dict] = None


class SystemStatus(BaseModel):
    """系統狀態"""
    data_exists: bool
    data_collected_at: Optional[str] = None
    btc_price: Optional[float] = None
    article_exists: bool
    article_date: Optional[str] = None
    site_built: bool
    last_task: Optional[TaskStatus] = None


# 全域狀態追蹤
_last_task_status: Optional[TaskStatus] = None
_task_running: bool = False


def get_project_root() -> Path:
    """取得專案根目錄"""
    return PROJECT_ROOT


def set_task_status(task: str, status: str, message: str, details: dict = None):
    """設定任務狀態"""
    global _last_task_status
    _last_task_status = TaskStatus(
        task=task,
        status=status,
        message=message,
        timestamp=datetime.now().isoformat(),
        details=details,
    )


# ============================================
# API 端點
# ============================================

@app.get("/api/status", response_model=SystemStatus)
async def get_status():
    """取得系統狀態"""
    root = get_project_root()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 檢查資料檔案
    data_path = root / "data" / "daily_context.json"
    data_exists = data_path.exists()
    data_collected_at = None
    btc_price = None
    
    if data_exists:
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data_collected_at = data.get("collected_at")
            btc_price = data.get("price", {}).get("price_usd")
        except Exception:
            pass
    
    # 檢查文章
    article_path = root / "site" / "content" / "posts" / f"{today}.md"
    article_exists = article_path.exists()
    
    # 檢查網站輸出
    output_dir = root / "site" / "public"
    site_built = output_dir.exists() and any(output_dir.iterdir())
    
    return SystemStatus(
        data_exists=data_exists,
        data_collected_at=data_collected_at,
        btc_price=btc_price,
        article_exists=article_exists,
        article_date=today if article_exists else None,
        site_built=site_built,
        last_task=_last_task_status,
    )


@app.get("/api/report")
async def get_report():
    """取得最新採集報告"""
    data_path = get_project_root() / "data" / "daily_context.json"
    
    if not data_path.exists():
        raise HTTPException(status_code=404, detail="尚未採集資料，請先執行採集")
    
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取報告失敗: {str(e)}")


@app.post("/api/collect")
async def collect_data(background_tasks: BackgroundTasks):
    """執行資料採集"""
    global _task_running
    
    if _task_running:
        raise HTTPException(status_code=409, detail="另一個任務正在執行中")
    
    _task_running = True
    set_task_status("collect", "running", "正在採集資料...")
    
    try:
        # 執行採集指令
        result = subprocess.run(
            [sys.executable, "main.py", "collect"],
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode == 0:
            set_task_status("collect", "success", "資料採集完成", {
                "stdout": result.stdout[-2000:] if result.stdout else "",
            })
            return {"status": "success", "message": "資料採集完成"}
        else:
            set_task_status("collect", "error", f"採集失敗: {result.stderr}", {
                "stderr": result.stderr[-2000:] if result.stderr else "",
            })
            raise HTTPException(status_code=500, detail=f"採集失敗: {result.stderr}")
    
    except subprocess.TimeoutExpired:
        set_task_status("collect", "error", "採集超時")
        raise HTTPException(status_code=504, detail="採集超時")
    except Exception as e:
        set_task_status("collect", "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _task_running = False


@app.post("/api/publish")
async def publish_site():
    """執行完整發布流程 (採集 → 生成 → 建置 → 推送)"""
    global _task_running
    
    if _task_running:
        raise HTTPException(status_code=409, detail="另一個任務正在執行中")
    
    _task_running = True
    steps = []
    
    try:
        # Step 1: 採集資料
        set_task_status("publish", "running", "Step 1/4: 正在採集資料...")
        result = subprocess.run(
            [sys.executable, "main.py", "collect"],
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise Exception(f"資料採集失敗: {result.stderr}")
        steps.append("✅ 資料採集完成")
        
        # Step 2: 生成文章 (使用 mock 模式以避免需要 API)
        set_task_status("publish", "running", "Step 2/4: 正在生成文章...")
        
        # 檢查是否有 GITHUB_TOKEN，決定使用真實還是 mock 模式
        use_mock = not os.getenv("GITHUB_TOKEN")
        write_cmd = [sys.executable, "main.py", "write"]
        if use_mock:
            write_cmd.append("--mock")
        
        result = subprocess.run(
            write_cmd,
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise Exception(f"文章生成失敗: {result.stderr}")
        steps.append("✅ 文章生成完成" + (" (Mock模式)" if use_mock else ""))
        
        # Step 3: 建置網站
        set_task_status("publish", "running", "Step 3/4: 正在建置網站...")
        result = subprocess.run(
            [sys.executable, "main.py", "build"],
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise Exception(f"網站建置失敗: {result.stderr}")
        steps.append("✅ 網站建置完成")
        
        # Step 4: 推送到 GitHub
        set_task_status("publish", "running", "Step 4/4: 正在推送到 GitHub...")
        from src.publisher.github import push_to_github
        push_result = push_to_github()
        
        if push_result["success"]:
            steps.append(f"✅ GitHub 推送完成: {push_result['message']}")
        else:
            steps.append(f"⚠️ GitHub 推送: {push_result['message']}")
        
        set_task_status("publish", "success", "發布流程完成", {"steps": steps})
        return {
            "status": "success",
            "message": "發布流程完成",
            "steps": steps,
        }
    
    except Exception as e:
        steps.append(f"❌ 錯誤: {str(e)}")
        set_task_status("publish", "error", str(e), {"steps": steps})
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _task_running = False


@app.post("/api/github/push")
async def github_push():
    """僅推送到 GitHub (不執行其他步驟)"""
    global _task_running
    
    if _task_running:
        raise HTTPException(status_code=409, detail="另一個任務正在執行中")
    
    _task_running = True
    set_task_status("push", "running", "正在推送到 GitHub...")
    
    try:
        from src.publisher.github import push_to_github
        result = push_to_github()
        
        if result["success"]:
            set_task_status("push", "success", result["message"])
            return {"status": "success", "message": result["message"]}
        else:
            set_task_status("push", "error", result["message"])
            raise HTTPException(status_code=500, detail=result["message"])
    
    except Exception as e:
        set_task_status("push", "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _task_running = False


# ============================================
# 靜態檔案與首頁
# ============================================

# 掛載靜態檔案目錄
static_dir = Path(__file__).parent.parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """首頁 - 返回 Web GUI"""
    index_path = Path(__file__).parent.parent / "web" / "static" / "index.html"
    
    if index_path.exists():
        return FileResponse(index_path)
    else:
        return HTMLResponse("""
        <html>
            <head><title>CoinPilot AI</title></head>
            <body>
                <h1>CoinPilot AI</h1>
                <p>Web GUI 尚未安裝。請確認 src/web/static/index.html 存在。</p>
                <p>API 端點可用：</p>
                <ul>
                    <li>GET /api/status - 系統狀態</li>
                    <li>GET /api/report - 查看報告</li>
                    <li>POST /api/collect - 採集資料</li>
                    <li>POST /api/publish - 完整發布</li>
                </ul>
            </body>
        </html>
        """)


# ============================================
# 啟動函數
# ============================================

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """啟動 Web 伺服器"""
    import uvicorn
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    
    logger.info(f"啟動 CoinPilot AI Web GUI: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
