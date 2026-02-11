"""
預爬腳本 - 批次爬取 2024 全年歷史新聞

使用方式:
    python -m src.chronos.scripts.prefetch_news

功能:
    - 爬取 2024/01/01 - 2024/12/31 共 366 天的新聞
    - 每天爬取 5 則比特幣相關新聞
    - 自動跳過已快取的日期
    - 支援中斷後續傳
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# 將專案根目錄加入 path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.collector.news import NewsClient
from src.chronos.data.news_cache import NewsCache, NewsCacheConfig

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def prefetch_news(
    start_date: date,
    end_date: date,
    limit_per_day: int = 5,
    delay: float = 1.5,
    force: bool = False,
):
    """
    預爬歷史新聞
    
    Args:
        start_date: 開始日期
        end_date: 結束日期
        limit_per_day: 每天爬取的新聞數量
        delay: 請求間隔（秒）
        force: 是否強制重新爬取已有快取的日期
    """
    # 初始化
    cache = NewsCache(NewsCacheConfig(
        data_dir="data/chronos_news",
        max_news_per_day=limit_per_day,
        request_delay=delay,
    ))
    client = NewsClient()
    
    # 計算需要爬取的日期
    if force:
        # 強制模式：爬取所有日期
        missing_dates = []
        current = start_date
        while current <= end_date:
            missing_dates.append(current)
            current += timedelta(days=1)
    else:
        # 增量模式：只爬取缺失的日期
        missing_dates = cache.get_missing_dates(start_date, end_date)
    
    total_days = (end_date - start_date).days + 1
    missing_count = len(missing_dates)
    
    logger.info("=" * 60)
    logger.info("Project Chronos - 歷史新聞預爬腳本")
    logger.info("=" * 60)
    logger.info(f"日期範圍: {start_date} ~ {end_date} ({total_days} 天)")
    logger.info(f"每天新聞: {limit_per_day} 則")
    logger.info(f"請求間隔: {delay} 秒")
    logger.info(f"需要爬取: {missing_count} 天")
    logger.info(f"已快取: {total_days - missing_count} 天")
    
    if missing_count == 0:
        logger.info("✅ 所有日期都已有快取，無需爬取")
        return
    
    # 預估時間
    estimated_minutes = (missing_count * delay) / 60
    logger.info(f"預估時間: {estimated_minutes:.1f} 分鐘")
    logger.info("=" * 60)
    
    # 開始爬取
    start_time = time.time()
    success_count = 0
    fail_count = 0
    
    for i, target_date in enumerate(missing_dates):
        date_str = target_date.strftime("%Y-%m-%d")
        progress = f"[{i+1}/{missing_count}]"
        
        try:
            logger.info(f"{progress} 爬取 {date_str}...")
            
            # 爬取新聞
            news_items = client.get_historical_news(
                target_date=target_date,
                limit=limit_per_day,
                fetch_content=False,  # 不爬取全文以節省時間
            )
            
            # 儲存到快取
            news_data = [item.to_dict() for item in news_items]
            cache.save_date(target_date, news_data)
            
            logger.info(f"  ✓ 獲取 {len(news_items)} 則新聞")
            success_count += 1
            
        except KeyboardInterrupt:
            logger.warning("\n⚠️ 使用者中斷，已保存目前進度")
            break
        except Exception as e:
            logger.error(f"  ✗ 失敗: {e}")
            fail_count += 1
            # 失敗時也儲存空列表，避免重試
            cache.save_date(target_date, [])
        
        # 請求間隔
        if i < len(missing_dates) - 1:
            time.sleep(delay)
    
    # 更新索引
    cache._update_index()
    
    # 完成報告
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("爬取完成！")
    logger.info(f"成功: {success_count} 天")
    logger.info(f"失敗: {fail_count} 天")
    logger.info(f"耗時: {elapsed/60:.1f} 分鐘")
    logger.info(f"快取摘要: {cache.get_summary()}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Project Chronos - 歷史新聞預爬腳本"
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
        "--limit",
        type=int,
        default=5,
        help="每天爬取的新聞數量",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="請求間隔（秒）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="強制重新爬取已有快取的日期",
    )
    
    args = parser.parse_args()
    
    # 解析日期
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error(f"日期格式錯誤: {e}")
        sys.exit(1)
    
    if start_date > end_date:
        logger.error("開始日期不能晚於結束日期")
        sys.exit(1)
    
    # 執行預爬
    prefetch_news(
        start_date=start_date,
        end_date=end_date,
        limit_per_day=args.limit,
        delay=args.delay,
        force=args.force,
    )


if __name__ == "__main__":
    main()
