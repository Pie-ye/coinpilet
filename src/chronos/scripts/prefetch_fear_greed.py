"""
預爬腳本 - 預爬 Fear & Greed Index 歷史資料

使用方式:
    python -m src.chronos.scripts.prefetch_fear_greed
"""

import logging
import sys
from pathlib import Path

# 將專案根目錄加入 path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.chronos.data.fear_greed_cache import FearGreedCache

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """預爬 Fear & Greed Index 歷史資料"""
    logger.info("=" * 60)
    logger.info("Project Chronos - Fear & Greed Index 預爬腳本")
    logger.info("=" * 60)
    
    cache = FearGreedCache()
    
    # 檢查現有快取
    summary = cache.get_summary()
    if summary.get("status") == "loaded":
        logger.info(f"現有快取: {summary['count']} 天")
        logger.info(f"日期範圍: {summary['date_range']['start']} ~ {summary['date_range']['end']}")
    
    # 抓取完整歷史
    logger.info("正在從 Alternative.me 抓取完整歷史...")
    count = cache.fetch_all_history(force=True)
    
    # 完成報告
    logger.info("=" * 60)
    logger.info(f"✅ 完成！共快取 {count} 天資料")
    logger.info(f"快取位置: {cache.cache_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
