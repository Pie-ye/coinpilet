"""
Hugo 網站建置模組 - 使用 subprocess 調用 Hugo CLI
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class HugoBuilder:
    """
    Hugo 網站建置器

    使用方式:
        builder = HugoBuilder(site_dir="site")
        builder.build()
        builder.serve()  # 開發模式
    """

    def __init__(
        self,
        site_dir: str | Path = "site",
        output_dir: str = "public",
        base_url: Optional[str] = None,
    ):
        """
        初始化 Hugo 建置器

        Args:
            site_dir: Hugo 網站根目錄
            output_dir: 輸出目錄 (相對於 site_dir)
            base_url: 網站基礎 URL (可選，覆蓋 config 設定)
        """
        self.site_dir = Path(site_dir).resolve()
        self.output_dir = output_dir
        self.base_url = base_url or os.getenv("HUGO_BASE_URL", "")
        self.hugo_path = self._find_hugo()

    def _find_hugo(self) -> str:
        """
        尋找 Hugo 執行檔路徑

        Returns:
            str: Hugo 執行檔路徑

        Raises:
            FileNotFoundError: 找不到 Hugo
        """
        # 優先使用環境變數
        hugo_path = os.getenv("HUGO_PATH")
        if hugo_path and Path(hugo_path).exists():
            return hugo_path

        # 嘗試從 PATH 中尋找
        hugo_in_path = shutil.which("hugo")
        if hugo_in_path:
            return hugo_in_path

        # 常見安裝路徑
        common_paths = [
            "/usr/local/bin/hugo",
            "/usr/bin/hugo",
            "C:\\Hugo\\bin\\hugo.exe",
            "C:\\ProgramData\\chocolatey\\bin\\hugo.exe",
        ]

        for path in common_paths:
            if Path(path).exists():
                return path

        raise FileNotFoundError(
            "找不到 Hugo 執行檔。請安裝 Hugo Extended 版本:\n"
            "  Windows: choco install hugo-extended\n"
            "  macOS: brew install hugo\n"
            "  Linux: snap install hugo --channel=extended"
        )

    def check_version(self) -> dict:
        """
        檢查 Hugo 版本資訊

        Returns:
            dict: 包含版本資訊的字典
        """
        try:
            result = subprocess.run(
                [self.hugo_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            version_str = result.stdout.strip()
            is_extended = "extended" in version_str.lower()

            return {
                "path": self.hugo_path,
                "version": version_str,
                "extended": is_extended,
                "available": True,
            }

        except subprocess.TimeoutExpired:
            logger.error("Hugo 版本檢查超時")
            return {"available": False, "error": "timeout"}
        except Exception as e:
            logger.error(f"Hugo 版本檢查失敗: {e}")
            return {"available": False, "error": str(e)}

    def build(
        self,
        minify: bool = True,
        environment: str = "production",
        clean: bool = True,
    ) -> bool:
        """
        建置 Hugo 網站

        Args:
            minify: 是否壓縮輸出
            environment: 建置環境 (production, development)
            clean: 是否先清理輸出目錄

        Returns:
            bool: 建置是否成功

        Raises:
            RuntimeError: 建置失敗
        """
        # 檢查網站目錄是否存在
        if not self.site_dir.exists():
            raise FileNotFoundError(f"Hugo 網站目錄不存在: {self.site_dir}")

        # 清理輸出目錄
        output_path = self.site_dir / self.output_dir
        if clean and output_path.exists():
            logger.info(f"清理輸出目錄: {output_path}")
            shutil.rmtree(output_path)

        # 建構命令
        cmd = [
            self.hugo_path,
            "--destination",
            self.output_dir,
            "--environment",
            environment,
        ]

        if minify:
            cmd.append("--minify")

        if self.base_url:
            cmd.extend(["--baseURL", self.base_url])

        logger.info(f"執行 Hugo 建置: {' '.join(cmd)}")
        logger.info(f"工作目錄: {self.site_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.site_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,  # 5 分鐘超時
            )

            if result.returncode != 0:
                logger.error(f"Hugo 建置失敗:\n{result.stderr}")
                raise RuntimeError(f"Hugo 建置失敗: {result.stderr}")

            # 解析輸出統計
            output = result.stdout
            logger.info("Hugo 建置完成!")
            if output:
                for line in output.strip().split("\n"):
                    logger.info(f"  {line}")

            return True

        except subprocess.TimeoutExpired:
            logger.error("Hugo 建置超時 (5 分鐘)")
            raise RuntimeError("Hugo 建置超時")
        except Exception as e:
            logger.error(f"Hugo 建置錯誤: {e}")
            raise

    def serve(
        self,
        port: int = 1313,
        bind: str = "127.0.0.1",
        open_browser: bool = False,
    ) -> subprocess.Popen:
        """
        啟動 Hugo 開發伺服器

        Args:
            port: 伺服器埠號
            bind: 綁定位址
            open_browser: 是否自動開啟瀏覽器

        Returns:
            subprocess.Popen: 伺服器程序
        """
        cmd = [
            self.hugo_path,
            "server",
            "--port",
            str(port),
            "--bind",
            bind,
            "--disableFastRender",
        ]

        if open_browser:
            cmd.append("--navigateToChanged")

        logger.info(f"啟動 Hugo 開發伺服器: http://{bind}:{port}")

        process = subprocess.Popen(
            cmd,
            cwd=self.site_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return process

    def new_content(self, path: str, kind: str = "posts") -> Path:
        """
        創建新內容頁面

        Args:
            path: 內容路徑 (如 "posts/2026-02-01.md")
            kind: 內容類型 (對應 archetypes)

        Returns:
            Path: 創建的檔案路徑
        """
        cmd = [
            self.hugo_path,
            "new",
            f"{kind}/{path}",
        ]

        result = subprocess.run(
            cmd,
            cwd=self.site_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.warning(f"Hugo new 失敗: {result.stderr}")

        return self.site_dir / "content" / kind / path

    def get_stats(self) -> dict:
        """
        獲取網站統計資訊

        Returns:
            dict: 網站統計
        """
        content_dir = self.site_dir / "content"
        posts_dir = content_dir / "posts"

        stats = {
            "site_dir": str(self.site_dir),
            "content_exists": content_dir.exists(),
            "posts_count": 0,
            "total_pages": 0,
        }

        if posts_dir.exists():
            stats["posts_count"] = len(list(posts_dir.glob("*.md")))

        if content_dir.exists():
            stats["total_pages"] = len(list(content_dir.rglob("*.md")))

        return stats


if __name__ == "__main__":
    # 測試用
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        builder = HugoBuilder(site_dir="site")
        version = builder.check_version()
        print(f"Hugo 版本: {version}")

        stats = builder.get_stats()
        print(f"網站統計: {stats}")

        # builder.build()
    except FileNotFoundError as e:
        print(f"錯誤: {e}")
