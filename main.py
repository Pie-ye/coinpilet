#!/usr/bin/env python3
"""
CoinPilot AI - 自動化加密貨幣分析與出版系統

主入口程式，提供 CLI 介面執行各項功能。

使用方式:
    python main.py run       # 執行完整流程
    python main.py collect   # 僅採集資料
    python main.py write     # 僅生成文章
    python main.py build     # 僅建置網站
    python main.py serve     # 啟動開發伺服器
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 將 src 加入路徑
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# 載入環境變數
load_dotenv()


def setup_logging(level: str = "INFO") -> None:
    """設定日誌格式"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_project_root() -> Path:
    """獲取專案根目錄"""
    return Path(__file__).parent.resolve()


def cmd_collect(args: argparse.Namespace) -> int:
    """執行資料採集"""
    from src.collector import Collector

    logger = logging.getLogger("collect")
    logger.info("開始執行資料採集...")

    try:
        # 從環境變數讀取 CoinGecko API Key (可選)
        coingecko_api_key = os.getenv("COINGECKO_API_KEY")

        collector = Collector(
            coingecko_api_key=coingecko_api_key if coingecko_api_key else None,
            news_language=args.lang,
            news_country=args.country,
        )
        context = collector.collect_all(news_limit=args.news_limit)

        # 保存資料
        output_path = get_project_root() / "data" / "daily_context.json"
        collector.save_to_file(context, output_path)

        logger.info(f"資料採集完成，已保存至 {output_path}")
        return 0

    except Exception as e:
        logger.error(f"資料採集失敗: {e}")
        return 1


async def cmd_write_async(args: argparse.Namespace) -> int:
    """執行 AI 文章生成 (非同步)"""
    from src.writer import Writer
    from src.writer.writer import get_writer

    logger = logging.getLogger("write")
    logger.info("開始執行 AI 文章生成...")

    # 讀取資料
    data_path = get_project_root() / "data" / "daily_context.json"
    if not data_path.exists():
        logger.error(f"找不到資料檔案: {data_path}")
        logger.error("請先執行 'python main.py collect' 採集資料")
        return 1

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            context_data = json.load(f)

        # 取得 writer
        model = args.model or os.getenv("COPILOT_MODEL", "gemini-3-flash")
        writer = get_writer(
            model=model,
            use_mock=args.mock,
            github_token=os.getenv("GITHUB_TOKEN"),
        )

        await writer.start()

        # 生成文章
        article = await writer.generate_article(context_data)

        # 保存文章
        output_dir = get_project_root() / "site" / "content" / "posts"
        filename = datetime.now().strftime("%Y-%m-%d") + ".md"
        filepath = await writer.save_article(article, output_dir, filename)

        await writer.stop()

        logger.info(f"文章生成完成，已保存至 {filepath}")
        return 0

    except Exception as e:
        logger.error(f"文章生成失敗: {e}")
        return 1


def cmd_write(args: argparse.Namespace) -> int:
    """執行 AI 文章生成"""
    return asyncio.run(cmd_write_async(args))


def cmd_build(args: argparse.Namespace) -> int:
    """執行 Hugo 網站建置"""
    from src.publisher import HugoBuilder

    logger = logging.getLogger("build")
    logger.info("開始執行 Hugo 網站建置...")

    try:
        site_dir = get_project_root() / "site"
        builder = HugoBuilder(
            site_dir=site_dir,
            base_url=args.base_url or os.getenv("HUGO_BASE_URL", ""),
        )

        # 檢查 Hugo 版本
        version = builder.check_version()
        if not version.get("available"):
            logger.error(f"Hugo 不可用: {version.get('error')}")
            return 1

        logger.info(f"使用 Hugo: {version.get('version')}")

        if not version.get("extended"):
            logger.warning("建議使用 Hugo Extended 版本以支援 Stack 主題的完整功能")

        # 建置網站
        builder.build(
            minify=not args.no_minify,
            environment=args.env,
            clean=not args.no_clean,
        )

        logger.info(f"網站建置完成，輸出目錄: {site_dir / 'public'}")
        return 0

    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"網站建置失敗: {e}")
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """啟動 Hugo 開發伺服器"""
    from src.publisher import HugoBuilder

    logger = logging.getLogger("serve")

    try:
        site_dir = get_project_root() / "site"
        builder = HugoBuilder(site_dir=site_dir)

        logger.info(f"啟動開發伺服器: http://localhost:{args.port}")
        logger.info("按 Ctrl+C 停止伺服器")

        process = builder.serve(port=args.port, bind=args.bind)

        # 等待程序結束
        try:
            while True:
                output = process.stdout.readline()
                if output:
                    print(output.decode().strip())
                if process.poll() is not None:
                    break
        except KeyboardInterrupt:
            logger.info("停止開發伺服器...")
            process.terminate()

        return 0

    except Exception as e:
        logger.error(f"伺服器啟動失敗: {e}")
        return 1


async def cmd_run_async(args: argparse.Namespace) -> int:
    """執行完整流程 (採集 → 生成 → 建置)"""
    logger = logging.getLogger("run")
    logger.info("=" * 60)
    logger.info("CoinPilot AI - 開始執行完整流程")
    logger.info("=" * 60)

    # Step 1: 採集資料
    logger.info("\n📊 Step 1/3: 資料採集")
    logger.info("-" * 40)
    result = cmd_collect(args)
    if result != 0:
        logger.error("資料採集失敗，流程中止")
        return result

    # Step 2: AI 生成文章
    logger.info("\n🤖 Step 2/3: AI 文章生成")
    logger.info("-" * 40)
    result = await cmd_write_async(args)
    if result != 0:
        logger.error("文章生成失敗，流程中止")
        return result

    # Step 3: 建置網站
    logger.info("\n🔨 Step 3/3: Hugo 網站建置")
    logger.info("-" * 40)
    result = cmd_build(args)
    if result != 0:
        logger.error("網站建置失敗")
        return result

    logger.info("\n" + "=" * 60)
    logger.info("✅ CoinPilot AI - 完整流程執行成功!")
    logger.info("=" * 60)

    # 輸出摘要
    site_dir = get_project_root() / "site"
    output_dir = site_dir / "public"
    today = datetime.now().strftime("%Y-%m-%d")
    article_path = site_dir / "content" / "posts" / f"{today}.md"

    logger.info(f"\n📄 今日文章: {article_path}")
    logger.info(f"🌐 網站輸出: {output_dir}")
    logger.info(f"\n💡 預覽網站: python main.py serve")

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """執行完整流程"""
    return asyncio.run(cmd_run_async(args))


def cmd_status(args: argparse.Namespace) -> int:
    """顯示系統狀態"""
    from src.publisher import HugoBuilder

    logger = logging.getLogger("status")
    project_root = get_project_root()

    print("\n" + "=" * 50)
    print("CoinPilot AI - 系統狀態")
    print("=" * 50)

    # 檢查資料檔案
    data_path = project_root / "data" / "daily_context.json"
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n📊 資料檔案: ✅ 存在")
        print(f"   採集時間: {data.get('collected_at', 'N/A')}")
        print(f"   BTC 價格: ${data.get('price', {}).get('price_usd', 0):,.2f}")
    else:
        print(f"\n📊 資料檔案: ❌ 不存在")

    # 檢查今日文章
    today = datetime.now().strftime("%Y-%m-%d")
    article_path = project_root / "site" / "content" / "posts" / f"{today}.md"
    if article_path.exists():
        print(f"\n📝 今日文章: ✅ 已生成 ({article_path.name})")
    else:
        print(f"\n📝 今日文章: ❌ 尚未生成")

    # 檢查 Hugo
    try:
        builder = HugoBuilder(site_dir=project_root / "site")
        version = builder.check_version()
        if version.get("available"):
            print(f"\n🔧 Hugo: ✅ {version.get('version', 'Unknown')}")
            print(f"   Extended: {'✅' if version.get('extended') else '❌'}")
        else:
            print(f"\n🔧 Hugo: ❌ 未安裝")
    except Exception:
        print(f"\n🔧 Hugo: ❌ 未安裝")

    # 檢查網站輸出
    output_dir = project_root / "site" / "public"
    if output_dir.exists():
        file_count = len(list(output_dir.rglob("*")))
        print(f"\n🌐 網站輸出: ✅ 存在 ({file_count} 個檔案)")
    else:
        print(f"\n🌐 網站輸出: ❌ 尚未建置")

    # 檢查環境變數
    print(f"\n⚙️  環境變數:")
    print(f"   GITHUB_TOKEN: {'✅ 已設定' if os.getenv('GITHUB_TOKEN') else '❌ 未設定'}")
    print(f"   COPILOT_MODEL: {os.getenv('COPILOT_MODEL', 'gemini-3-flash')}")
    print(f"   HUGO_BASE_URL: {os.getenv('HUGO_BASE_URL', '(未設定)')}")

    print("\n" + "=" * 50 + "\n")

    return 0


def cmd_web(args: argparse.Namespace) -> int:
    """啟動 Web GUI 控制台"""
    from src.api.server import run_server

    logger = logging.getLogger("web")
    logger.info(f"啟動 Web GUI 控制台: http://{args.host}:{args.port}")
    logger.info("按 Ctrl+C 停止伺服器")

    try:
        run_server(host=args.host, port=args.port)
        return 0
    except KeyboardInterrupt:
        logger.info("Web 伺服器已停止")
        return 0
    except Exception as e:
        logger.error(f"Web 伺服器啟動失敗: {e}")
        return 1


def main():
    """主函數"""
    parser = argparse.ArgumentParser(
        description="CoinPilot AI - 自動化加密貨幣分析與出版系統",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python main.py run                    # 執行完整流程
  python main.py collect                # 僅採集資料
  python main.py write --mock           # 使用模擬模式生成文章
  python main.py build                  # 僅建置網站
  python main.py serve --port 8080      # 啟動開發伺服器
  python main.py status                 # 查看系統狀態
  python main.py web                    # 啟動 Web GUI 控制台
        """,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="顯示詳細日誌",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="日誌等級 (預設: info)",
    )

    subparsers = parser.add_subparsers(dest="command", help="可用指令")

    # run 指令
    run_parser = subparsers.add_parser("run", help="執行完整流程 (採集 → 生成 → 建置)")
    run_parser.add_argument("--mock", action="store_true", help="使用模擬 AI 模式")
    run_parser.add_argument("--model", type=str, help="指定 AI 模型")
    run_parser.add_argument("--lang", default="en", help="新聞語言 (預設: en)")
    run_parser.add_argument("--country", default="US", help="新聞國家 (預設: US)")
    run_parser.add_argument("--news-limit", type=int, default=3, help="新聞數量限制")
    run_parser.add_argument("--base-url", type=str, help="網站基礎 URL")
    run_parser.add_argument("--no-minify", action="store_true", help="不壓縮輸出")
    run_parser.add_argument("--no-clean", action="store_true", help="不清理輸出目錄")
    run_parser.add_argument("--env", default="production", help="建置環境")
    run_parser.set_defaults(func=cmd_run)

    # collect 指令
    collect_parser = subparsers.add_parser("collect", help="僅採集資料")
    collect_parser.add_argument("--lang", default="en", help="新聞語言")
    collect_parser.add_argument("--country", default="US", help="新聞國家")
    collect_parser.add_argument("--news-limit", type=int, default=3, help="新聞數量")
    collect_parser.set_defaults(func=cmd_collect)

    # write 指令
    write_parser = subparsers.add_parser("write", help="僅生成文章")
    write_parser.add_argument("--mock", action="store_true", help="使用模擬 AI")
    write_parser.add_argument("--model", type=str, help="指定 AI 模型")
    write_parser.set_defaults(func=cmd_write)

    # build 指令
    build_parser = subparsers.add_parser("build", help="僅建置網站")
    build_parser.add_argument("--base-url", type=str, help="網站基礎 URL")
    build_parser.add_argument("--no-minify", action="store_true", help="不壓縮輸出")
    build_parser.add_argument("--no-clean", action="store_true", help="不清理輸出目錄")
    build_parser.add_argument("--env", default="production", help="建置環境")
    build_parser.set_defaults(func=cmd_build)

    # serve 指令
    serve_parser = subparsers.add_parser("serve", help="啟動開發伺服器")
    serve_parser.add_argument("--port", type=int, default=1313, help="伺服器埠號")
    serve_parser.add_argument("--bind", default="127.0.0.1", help="綁定位址")
    serve_parser.set_defaults(func=cmd_serve)

    # status 指令
    status_parser = subparsers.add_parser("status", help="顯示系統狀態")
    status_parser.set_defaults(func=cmd_status)

    # web 指令
    web_parser = subparsers.add_parser("web", help="啟動 Web GUI 控制台")
    web_parser.add_argument("--port", type=int, default=8000, help="伺服器埠號 (預設: 8000)")
    web_parser.add_argument("--host", default="0.0.0.0", help="綁定位址 (預設: 0.0.0.0)")
    web_parser.set_defaults(func=cmd_web)

    args = parser.parse_args()

    # 設定日誌
    log_level = "DEBUG" if args.verbose else args.log_level.upper()
    setup_logging(log_level)

    # 執行指令
    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
