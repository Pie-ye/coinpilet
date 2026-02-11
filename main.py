#!/usr/bin/env python3
"""
CoinPilot AI - Bitcoin Autonomous Intelligence Agent (BAIA)

自動化加密貨幣分析與出版系統，具備程式碼執行與自我修復能力。

使用方式:
    python main.py run                    # 執行完整流程 (傳統模式)
    python main.py baia                   # 執行 BAIA 智能代理模式
    python main.py comprehensive-report   # 生成綜合投資報告
    python main.py collect                # 僅採集資料
    python main.py write                  # 僅生成文章
    python main.py build                  # 僅建置網站
    python main.py serve                  # 啟動開發伺服器
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import structlog

# 將 src 加入路徑
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# 載入環境變數
load_dotenv()


def setup_logging(level: str = "INFO", use_structlog: bool = False) -> None:
    """設定日誌格式"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    if use_structlog:
        # 使用 structlog 進行結構化日誌
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(
            level=log_level,
            format="%(message)s",
        )
    else:
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
    """執行完整流程 (採集 → 生成 → 建置 → 推送)"""
    logger = logging.getLogger("run")
    logger.info("=" * 60)
    logger.info("CoinPilot AI - 開始執行完整流程")
    logger.info("=" * 60)

    # Step 1: 採集資料
    logger.info("\n📊 Step 1/4: 資料採集")
    logger.info("-" * 40)
    result = cmd_collect(args)
    if result != 0:
        logger.error("資料採集失敗，流程中止")
        return result

    # Step 2: AI 生成文章
    logger.info("\n🤖 Step 2/4: AI 文章生成")
    logger.info("-" * 40)
    result = await cmd_write_async(args)
    if result != 0:
        logger.error("文章生成失敗，流程中止")
        return result

    # Step 3: 建置網站
    logger.info("\n🔨 Step 3/4: Hugo 網站建置")
    logger.info("-" * 40)
    result = cmd_build(args)
    if result != 0:
        logger.error("網站建置失敗")
        return result

    # Step 4: 推送到 GitHub
    logger.info("\n🚀 Step 4/4: 推送到 GitHub")
    logger.info("-" * 40)
    
    try:
        from src.publisher.github import push_to_github
        
        today = datetime.now().strftime("%Y-%m-%d")
        commit_message = f"🚀 Auto publish: {today} 比特幣日報"
        
        push_result = push_to_github(commit_message=commit_message)
        
        if push_result["success"]:
            logger.info(f"✅ {push_result['message']}")
            if push_result.get("details", {}).get("status") == "no_changes":
                logger.info("   提示: 沒有新的變更需要推送")
        else:
            logger.warning(f"⚠️ GitHub 推送失敗: {push_result['message']}")
            logger.warning("   網站已建置完成，但未推送到 GitHub")
            logger.warning("   您可以稍後手動推送或檢查 Git 設定")
            # 不中斷流程，因為網站已建置成功
    except Exception as e:
        logger.warning(f"⚠️ GitHub 推送失敗: {e}")
        logger.warning("   網站已建置完成，但未推送到 GitHub")

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
    logger.info(f"🚀 Cloudflare Pages 將自動部署")
    logger.info(f"\n💡 本地預覽: python main.py serve")

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """執行完整流程"""
    return asyncio.run(cmd_run_async(args))


async def cmd_baia_async(args: argparse.Namespace) -> int:
    """
    執行 BAIA 智能代理模式
    
    流程: collect → analyst (繪圖) → writer → maintainer → build → push
    
    特點:
        - 自動生成 BTC K 線圖
        - 自動更新 README 儀表板
        - 具備自我修復能力
        - 結構化日誌記錄
    """
    log = structlog.get_logger("baia")
    
    log.info("=" * 60)
    log.info("🤖 BAIA - Bitcoin Autonomous Intelligence Agent")
    log.info("=" * 60)
    
    project_root = get_project_root()
    today = datetime.now().strftime("%Y-%m-%d")
    total_retries = 0
    
    # Step 1: 資料採集
    log.info("\n📊 Step 1/6: 資料採集")
    log.info("-" * 40)
    result = cmd_collect(args)
    if result != 0:
        log.error("資料採集失敗，流程中止")
        return result

    # Step 2: 生成 K 線圖 (Analyst Agent)
    log.info("\n📈 Step 2/6: 生成 BTC K 線圖")
    log.info("-" * 40)
    
    try:
        from src.agent.analyst import AnalystAgent
        
        analyst = AnalystAgent(working_dir=project_root)
        chart_result = await analyst.generate_chart()
        
        if chart_result.success:
            log.info(
                "K 線圖生成成功",
                path=str(chart_result.chart_path),
                price=f"${chart_result.current_price:,.2f}",
                change=f"{chart_result.price_change_24h:+.2f}%",
            )
            if chart_result.retry_count > 0:
                log.info(f"   自我修復次數: {chart_result.retry_count}")
                total_retries += chart_result.retry_count
        else:
            log.warning(f"K 線圖生成失敗: {chart_result.error_message}")
            log.warning("   繼續執行，但文章將不包含圖表")
            chart_result = None
    except Exception as e:
        log.warning(f"K 線圖生成異常: {e}")
        log.warning("   繼續執行，但文章將不包含圖表")
        chart_result = None

    # Step 3: AI 生成文章 (整合圖表數據)
    log.info("\n🤖 Step 3/6: AI 文章生成")
    log.info("-" * 40)
    
    try:
        from src.writer import Writer
        from src.writer.writer import get_writer

        # 讀取資料
        data_path = project_root / "data" / "daily_context.json"
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

        # 設定圖表數據
        if chart_result and chart_result.success:
            writer.set_chart_data(chart_result.to_dict())

        # 生成文章
        article = await writer.generate_article(context_data)

        # 保存文章
        output_dir = project_root / "site" / "content" / "posts"
        filename = today + ".md"
        filepath = await writer.save_article(article, output_dir, filename)

        await writer.stop()

        log.info(f"文章生成完成: {filepath}")
        
    except Exception as e:
        log.error(f"文章生成失敗: {e}")
        return 1

    # Step 4: 更新 README 儀表板 (Maintainer Agent)
    log.info("\n📋 Step 4/6: 更新 README 儀表板")
    log.info("-" * 40)
    
    try:
        from src.agent.maintainer import MaintainerAgent
        
        maintainer = MaintainerAgent(working_dir=project_root)
        maintain_result = await maintainer.update_readme()
        
        if maintain_result.success:
            if maintain_result.readme_updated:
                log.info(
                    "README 已更新",
                    articles=maintain_result.articles_found,
                    changes=maintain_result.changes,
                )
            else:
                log.info("README 無需更新")
        else:
            log.warning(f"README 更新失敗: {maintain_result.error_message}")
    except Exception as e:
        log.warning(f"README 更新異常: {e}")
        log.warning("   繼續執行後續步驟")

    # Step 5: 建置網站
    log.info("\n🔨 Step 5/6: Hugo 網站建置")
    log.info("-" * 40)
    result = cmd_build(args)
    if result != 0:
        log.error("網站建置失敗")
        return result

    # Step 6: 推送到 GitHub
    log.info("\n🚀 Step 6/6: 推送到 GitHub")
    log.info("-" * 40)
    
    try:
        from src.publisher.github import push_to_github
        
        commit_message = f"🤖 BAIA Auto publish: {today} 比特幣日報"
        if chart_result and chart_result.success:
            commit_message += f" (BTC ${chart_result.current_price:,.0f})"
        
        push_result = push_to_github(commit_message=commit_message)
        
        if push_result["success"]:
            log.info(f"✅ {push_result['message']}")
        else:
            log.warning(f"⚠️ GitHub 推送失敗: {push_result['message']}")
    except Exception as e:
        log.warning(f"⚠️ GitHub 推送失敗: {e}")

    # 完成摘要
    log.info("\n" + "=" * 60)
    log.info("✅ BAIA - 智能代理執行完成!")
    log.info("=" * 60)
    
    site_dir = project_root / "site"
    article_path = site_dir / "content" / "posts" / f"{today}.md"
    chart_path = site_dir / "static" / "images" / "btc_daily.png"
    
    log.info(f"\n📄 今日文章: {article_path}")
    if chart_result and chart_result.success:
        log.info(f"📈 K 線圖: {chart_path}")
        log.info(f"💰 BTC 價格: ${chart_result.current_price:,.2f} ({chart_result.price_change_24h:+.2f}%)")
    log.info(f"🌐 網站輸出: {site_dir / 'public'}")
    
    if total_retries > 0:
        log.info(f"\n🔧 自我修復紀錄: 共 {total_retries} 次重試")
    
    log.info(f"\n💡 本地預覽: python main.py serve")

    return 0


def cmd_baia(args: argparse.Namespace) -> int:
    """執行 BAIA 智能代理模式"""
    # 啟用 structlog
    setup_logging(args.log_level if hasattr(args, 'log_level') else "info", use_structlog=True)
    return asyncio.run(cmd_baia_async(args))


async def cmd_comprehensive_report_async(args: argparse.Namespace) -> int:
    """
    生成綜合投資報告
    
    整合多日市場資料和四位 AI 投資者的決策，
    提供 $1M 資金的配置建議。
    """
    log = structlog.get_logger("comprehensive-report")
    
    log.info("=" * 60)
    log.info("📊 綜合投資報告生成系統")
    log.info("=" * 60)
    
    project_root = get_project_root()
    today = datetime.now().strftime("%Y-%m-%d")
    days = getattr(args, 'days', 3)
    capital = getattr(args, 'capital', 1000000.0)
    
    # Step 1: 採集多日資料
    log.info(f"\n📅 Step 1/4: 採集過去 {days} 天的市場資料")
    log.info("-" * 40)
    
    try:
        from src.collector import Collector
        
        collector = Collector(
            coingecko_api_key=os.getenv("COINGECKO_API_KEY"),
            news_language=getattr(args, 'lang', 'en'),
            news_country=getattr(args, 'country', 'US'),
        )
        
        multi_day_data = collector.collect_multi_day(
            days=days,
            news_limit_per_day=getattr(args, 'news_limit', 3),
            include_today=True,
        )
        
        if not multi_day_data:
            log.error("無法採集市場資料")
            return 1
            
        log.info(f"成功採集 {len(multi_day_data)} 天資料")
        
    except Exception as e:
        log.error(f"資料採集失敗: {e}")
        return 1
    
    # Step 2: 取得四位投資者決策
    log.info(f"\n🎭 Step 2/4: 取得四位 AI 投資者決策")
    log.info("-" * 40)
    
    try:
        from src.agent.investment_advisor import InvestmentAdvisor
        
        advisor = InvestmentAdvisor()
        
        # 使用最新一天的資料作為決策依據
        latest_context = multi_day_data[-1]
        market_context = advisor.build_market_context(
            latest_context,
            usd_balance=capital,
        )
        
        persona_decisions = advisor.get_multi_strategy_decisions(market_context)
        
        log.info(f"四位投資者決策完成:")
        for persona_id, decision in persona_decisions.decisions.items():
            log.info(f"  {decision.emoji} {decision.persona_name}: {decision.action} ({decision.confidence}% 信心)")
        log.info(f"  📊 共識: {persona_decisions.consensus_action} ({persona_decisions.consensus_confidence}% 信心)")
        
    except Exception as e:
        log.error(f"投資者決策失敗: {e}")
        return 1
    
    # Step 3: 計算資金配置
    log.info(f"\n💰 Step 3/4: 計算 ${capital:,.0f} 資金配置")
    log.info("-" * 40)
    
    try:
        btc_price = latest_context.price.get("price_usd", 66500)
        
        portfolio_allocation = advisor.calculate_portfolio_allocation(
            persona_decisions,
            total_capital=capital,
            btc_price=btc_price,
        )
        
        log.info(f"建議行動: {portfolio_allocation.recommended_action}")
        if portfolio_allocation.buy_amount_usd > 0:
            log.info(f"  買入金額: ${portfolio_allocation.buy_amount_usd:,.0f}")
            log.info(f"  BTC 數量: {portfolio_allocation.btc_to_buy:.4f} BTC")
        log.info(f"  風險等級: {portfolio_allocation.risk_level.upper()}")
        
    except Exception as e:
        log.error(f"資金配置計算失敗: {e}")
        return 1
    
    # Step 4: 生成報告
    log.info(f"\n📝 Step 4/4: 生成綜合投資報告")
    log.info("-" * 40)
    
    try:
        from src.writer import Writer
        from src.writer.writer import get_writer
        
        use_mock = getattr(args, 'mock', False)
        model = getattr(args, 'model', None) or os.getenv("COPILOT_MODEL", "gemini-3-flash")
        
        writer = get_writer(use_mock=use_mock, model=model)
        await writer.start()
        
        log.info("⏳ 正在生成報告（約 3-5 分鐘）...")
        
        report = await writer.generate_comprehensive_report(
            multi_day_data,
            persona_decisions,
            portfolio_allocation,
        )
        
        # 保存報告
        output_dir = project_root / "site" / "content" / "posts"
        filename = f"comprehensive-{today}.md"
        output_path = await writer.save_article(report, output_dir, filename)
        
        await writer.stop()
        
        log.info(f"報告已保存至: {output_path}")
        
    except Exception as e:
        log.error(f"報告生成失敗: {e}")
        return 1
    
    # 完成摘要
    log.info("\n" + "=" * 60)
    log.info("✅ 綜合投資報告生成完成！")
    log.info("=" * 60)
    log.info(f"📄 報告路徑: {output_path}")
    log.info(f"💰 分析資金: ${capital:,.0f}")
    log.info(f"📊 建議行動: {portfolio_allocation.recommended_action}")
    log.info(f"💡 本地預覽: python main.py serve")
    
    return 0


def cmd_comprehensive_report(args: argparse.Namespace) -> int:
    """執行綜合投資報告生成"""
    setup_logging(args.log_level if hasattr(args, 'log_level') else "info", use_structlog=True)
    return asyncio.run(cmd_comprehensive_report_async(args))


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
        description="CoinPilot AI - Bitcoin Autonomous Intelligence Agent (BAIA)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python main.py baia                   # 🤖 執行 BAIA 智能代理模式 (推薦)
  python main.py comprehensive-report   # 📊 生成綜合投資報告
  python main.py run                    # 執行傳統流程 (採集→生成→建置→推送)
  python main.py collect                # 僅採集資料
  python main.py write --mock           # 使用模擬模式生成文章
  python main.py build                  # 僅建置網站
  python main.py serve --port 8080      # 啟動開發伺服器
  python main.py status                 # 查看系統狀態

BAIA 模式特點:
  - 📈 自動生成 BTC K 線圖 (白底、綠漲紅跌)
  - 📋 自動更新 README 儀表板 (最新 5 篇文章)
  - 🔧 具備自我修復能力 (錯誤自動重試)
  - 📊 結構化日誌記錄

綜合投資報告特點:
  - 📅 分析過去多天的市場數據
  - 🎭 整合 Guardian/Quant/Strategist/Degen 四位 AI 投資者觀點
  - 💰 提供具體的資金配置建議 (預設 $1,000,000)
  - 📊 包含技術指標、新聞分析、風險評估
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

    # baia 指令 (BAIA 智能代理模式)
    baia_parser = subparsers.add_parser(
        "baia",
        help="🤖 執行 BAIA 智能代理模式 (採集 → 繪圖 → 生成 → 維護 → 建置 → 推送)",
    )
    baia_parser.add_argument("--mock", action="store_true", help="使用模擬 AI 模式")
    baia_parser.add_argument("--model", type=str, help="指定 AI 模型")
    baia_parser.add_argument("--lang", default="en", help="新聞語言 (預設: en)")
    baia_parser.add_argument("--country", default="US", help="新聞國家 (預設: US)")
    baia_parser.add_argument("--news-limit", type=int, default=3, help="新聞數量限制")
    baia_parser.add_argument("--base-url", type=str, help="網站基礎 URL")
    baia_parser.add_argument("--no-minify", action="store_true", help="不壓縮輸出")
    baia_parser.add_argument("--no-clean", action="store_true", help="不清理輸出目錄")
    baia_parser.add_argument("--env", default="production", help="建置環境")
    baia_parser.set_defaults(func=cmd_baia)

    # comprehensive-report 指令（綜合投資報告）
    comp_parser = subparsers.add_parser(
        "comprehensive-report",
        help="📊 生成綜合投資報告（整合多日資料和四位 AI 投資者決策）",
    )
    comp_parser.add_argument("--days", type=int, default=3, help="分析天數 (預設: 3)")
    comp_parser.add_argument("--capital", type=float, default=1000000.0, help="分析資金 (預設: $1,000,000)")
    comp_parser.add_argument("--mock", action="store_true", help="使用模擬 AI 模式")
    comp_parser.add_argument("--model", type=str, help="指定 AI 模型")
    comp_parser.add_argument("--lang", default="en", help="新聞語言 (預設: en)")
    comp_parser.add_argument("--country", default="US", help="新聞國家 (預設: US)")
    comp_parser.add_argument("--news-limit", type=int, default=3, help="每日新聞數量限制")
    comp_parser.set_defaults(func=cmd_comprehensive_report)

    # run 指令 (傳統模式)
    run_parser = subparsers.add_parser("run", help="執行傳統流程 (採集 → 生成 → 建置)")
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
