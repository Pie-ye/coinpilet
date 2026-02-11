"""
GitHub 推送模組 - 將網站內容推送到 GitHub 倉庫

用於 Cloudflare Pages 自動部署
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """取得專案根目錄"""
    return Path(__file__).parent.parent.parent.resolve()


def push_to_github(
    commit_message: Optional[str] = None,
    branch: str = "main",
) -> dict:
    """
    將變更推送到 GitHub

    Args:
        commit_message: 提交訊息（預設為自動生成）
        branch: 目標分支（預設為 main）

    Returns:
        dict: 包含 success, message, details 的結果
    """
    root = get_project_root()
    site_dir = root / "site"
    
    # 預設提交訊息
    if not commit_message:
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_message = f"🚀 Auto publish: {today}"
    
    try:
        # 檢查 Git 是否可用
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return {
                "success": False,
                "message": "Git 未安裝或不可用",
                "details": None,
            }
        
        # 檢查是否為 Git 倉庫
        git_dir = root / ".git"
        if not git_dir.exists():
            return {
                "success": False,
                "message": "此目錄不是 Git 倉庫",
                "details": None,
            }
        
        # 設定 Git 使用者資訊（如果環境變數有提供）
        git_user_name = os.getenv("GIT_USER_NAME")
        git_user_email = os.getenv("GIT_USER_EMAIL")
        
        if git_user_name:
            subprocess.run(
                ["git", "config", "user.name", git_user_name],
                cwd=str(root),
                capture_output=True,
            )
        
        if git_user_email:
            subprocess.run(
                ["git", "config", "user.email", git_user_email],
                cwd=str(root),
                capture_output=True,
            )
        
        # 添加變更的檔案
        # 只添加 site/public 和 site/content 目錄
        paths_to_add = [
            "site/public",
            "site/content/posts",
            "site/static/images",
            "data/daily_context.json",
            "README.md",
        ]
        
        for path in paths_to_add:
            full_path = root / path
            if full_path.exists():
                result = subprocess.run(
                    ["git", "add", path],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                logger.debug(f"git add {path}: {result.returncode}")
        
        # 檢查是否有變更
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        if not result.stdout.strip():
            return {
                "success": True,
                "message": "沒有變更需要提交",
                "details": {"status": "no_changes"},
            }
        
        # 提交變更
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        if result.returncode != 0:
            # 檢查是否只是沒有變更
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                return {
                    "success": True,
                    "message": "沒有變更需要提交",
                    "details": {"status": "no_changes"},
                }
            return {
                "success": False,
                "message": f"提交失敗: {result.stderr}",
                "details": {"stderr": result.stderr, "stdout": result.stdout},
            }
        
        commit_output = result.stdout
        
        # 推送到遠端
        result = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "message": f"推送失敗: {result.stderr}",
                "details": {"stderr": result.stderr, "stdout": result.stdout},
            }
        
        logger.info(f"成功推送到 GitHub: {commit_message}")
        
        return {
            "success": True,
            "message": f"成功推送到 {branch} 分支",
            "details": {
                "status": "pushed",
                "branch": branch,
                "commit_message": commit_message,
                "commit_output": commit_output,
                "push_output": result.stdout,
            },
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "推送超時（60秒）",
            "details": None,
        }
    except Exception as e:
        logger.error(f"GitHub 推送失敗: {e}")
        return {
            "success": False,
            "message": f"推送失敗: {str(e)}",
            "details": None,
        }


def setup_github_remote(
    repo_url: str,
    remote_name: str = "origin",
) -> dict:
    """
    設定 GitHub 遠端倉庫

    Args:
        repo_url: GitHub 倉庫 URL
        remote_name: 遠端名稱（預設 origin）

    Returns:
        dict: 結果
    """
    root = get_project_root()
    
    try:
        # 檢查遠端是否已存在
        result = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        if result.returncode == 0:
            current_url = result.stdout.strip()
            if current_url == repo_url:
                return {
                    "success": True,
                    "message": f"遠端 {remote_name} 已設定為 {repo_url}",
                }
            
            # 更新遠端 URL
            result = subprocess.run(
                ["git", "remote", "set-url", remote_name, repo_url],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            # 添加新遠端
            result = subprocess.run(
                ["git", "remote", "add", remote_name, repo_url],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        
        if result.returncode != 0:
            return {
                "success": False,
                "message": f"設定遠端失敗: {result.stderr}",
            }
        
        return {
            "success": True,
            "message": f"已設定遠端 {remote_name} 為 {repo_url}",
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
        }
