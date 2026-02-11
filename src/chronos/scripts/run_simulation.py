"""
Project Chronos - 主執行腳本

使用方式:
    # 同步模式（使用規則決策，快速測試）
    python -m src.chronos.scripts.run_simulation
    
    # AI 模式（使用 Gemini 模型）
    python -m src.chronos.scripts.run_simulation --ai
    
    # 自訂日期範圍
    python -m src.chronos.scripts.run_simulation --start 2024-01-01 --end 2024-03-31
    
    # 快速測試（一個月）
    python -m src.chronos.scripts.run_simulation --quick
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# 將專案根目錄加入 path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.chronos.simulator import ChronosSimulator, SimulationConfig

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def progress_callback(current: int, total: int, current_date: date):
    """進度回調"""
    pct = (current / total) * 100
    if current % 30 == 0 or current == 1 or current == total:
        logger.info(f"進度: {current}/{total} ({pct:.1f}%) - {current_date}")


def main():
    parser = argparse.ArgumentParser(
        description="Project Chronos - 時光回溯投資模擬"
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2024-01-01",
        help="開始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2024-12-31",
        help="結束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1_000_000.0,
        help="初始資金 (USD)",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="使用 AI 模型決策 (預設使用規則決策)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-3-flash",
        help="AI 模型名稱",
    )
    parser.add_argument(
        "--no-debate",
        action="store_true",
        help="不生成辯論腳本",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/chronos",
        help="輸出目錄",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="快速測試模式（只跑一個月）",
    )
    
    args = parser.parse_args()
    
    # 解析日期
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error(f"日期格式錯誤: {e}")
        sys.exit(1)
    
    # 快速測試模式
    if args.quick:
        end_date = date(start_date.year, start_date.month + 1, start_date.day) if start_date.month < 12 else date(start_date.year + 1, 1, start_date.day)
        logger.info("快速測試模式：只跑一個月")
    
    # 建立配置
    config = SimulationConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
        model=args.model,
        use_ai=args.ai,
        generate_debates=not args.no_debate,
        output_dir=args.output,
    )
    
    # 顯示配置
    logger.info("=" * 60)
    logger.info("🕰️  Project Chronos - 時光回溯投資模擬")
    logger.info("=" * 60)
    logger.info(f"回測範圍: {config.start_date} ~ {config.end_date}")
    logger.info(f"初始資金: ${config.initial_capital:,.0f}")
    logger.info(f"決策模式: {'AI (' + config.model + ')' if config.use_ai else '規則決策'}")
    logger.info(f"生成辯論: {'是' if config.generate_debates else '否'}")
    logger.info(f"輸出目錄: {config.output_dir}")
    logger.info("=" * 60)
    
    # 執行模擬
    simulator = ChronosSimulator(config)
    
    if config.use_ai:
        import asyncio
        asyncio.run(simulator.run(progress_callback=progress_callback))
    else:
        simulator.run_sync(progress_callback=progress_callback)
    
    logger.info("模擬完成！請查看輸出目錄的報告。")


if __name__ == "__main__":
    main()
