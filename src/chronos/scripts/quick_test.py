"""
Project Chronos - 快速測試腳本

直接執行測試，不需要命令列參數
"""

import logging
import sys
from datetime import date
from pathlib import Path

# 將專案根目錄加入 path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from src.chronos.simulator import run_simulation


if __name__ == "__main__":
    print("=" * 60)
    print("🕰️  Project Chronos - 快速測試")
    print("=" * 60)
    print("測試範圍: 2024-01-01 ~ 2024-01-31 (一個月)")
    print("模式: 規則決策 (不使用 AI)")
    print("=" * 60)
    
    # 執行一個月的測試
    simulator = run_simulation(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        use_ai=False,
        generate_debates=True,
        output_dir="output/chronos_test",
    )
    
    print("\n✅ 測試完成！")
    print(f"輸出目錄: output/chronos_test")
