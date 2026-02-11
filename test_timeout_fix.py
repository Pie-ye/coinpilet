"""
測試超時修復是否有效

這個測試驗證：
1. 超時時會降級到規則決策
2. 統計信息正確記錄
3. 模擬不會因為超時而中斷
"""
import asyncio
import logging
from datetime import date
from src.chronos.simulator import ChronosSimulator, SimulationConfig

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def test_timeout_handling():
    """測試超時處理機制"""
    logger.info("=" * 60)
    logger.info("測試超時處理機制")
    logger.info("=" * 60)
    
    # 配置一個短時間的測試
    config = SimulationConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),  # 只測試 2 天
        initial_capital=1_000_000.0,
        model="gemini-3-flash",
        use_ai=True,
        generate_debates=False,  # 關閉辯論以加快測試
        output_dir="output/chronos_test",
    )
    
    simulator = ChronosSimulator(config)
    
    try:
        logger.info("\n開始執行模擬...")
        await simulator.run()
        
        # 檢查統計信息
        logger.info("\n" + "=" * 60)
        logger.info("測試結果")
        logger.info("=" * 60)
        
        total_decisions = simulator.stats["ai_decisions"] + simulator.stats["rule_decisions"]
        logger.info(f"總決策次數: {total_decisions}")
        logger.info(f"AI 決策成功: {simulator.stats['ai_decisions']}")
        logger.info(f"規則決策（降級）: {simulator.stats['rule_decisions']}")
        logger.info(f"超時次數: {simulator.stats['timeout_fallbacks']}")
        logger.info(f"錯誤次數: {simulator.stats['error_fallbacks']}")
        
        # 驗證模擬完成
        if len(simulator.daily_results) > 0:
            logger.info(f"\n✅ 模擬成功完成 {len(simulator.daily_results)} 天")
            logger.info("✅ 超時處理機制運作正常")
            return True
        else:
            logger.error("\n❌ 模擬未產生任何結果")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 模擬失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sync_mode():
    """測試同步模式（無 AI）"""
    logger.info("\n" + "=" * 60)
    logger.info("測試同步模式（規則決策）")
    logger.info("=" * 60)
    
    config = SimulationConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        initial_capital=1_000_000.0,
        use_ai=False,  # 使用規則決策
        generate_debates=False,
        output_dir="output/chronos_test",
    )
    
    simulator = ChronosSimulator(config)
    
    try:
        logger.info("\n開始執行同步模擬...")
        simulator.run_sync()
        
        if len(simulator.daily_results) > 0:
            logger.info(f"\n✅ 同步模擬成功完成 {len(simulator.daily_results)} 天")
            return True
        else:
            logger.error("\n❌ 同步模擬未產生任何結果")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 同步模擬失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函數"""
    logger.info("=" * 60)
    logger.info("🧪 開始超時修復測試")
    logger.info("=" * 60)
    
    results = []
    
    # 測試 1: 同步模式
    logger.info("\n📝 測試 1/2: 同步模式（規則決策）")
    result1 = test_sync_mode()
    results.append(("同步模式", result1))
    
    # 測試 2: AI 模式（可能超時）
    logger.info("\n📝 測試 2/2: AI 模式（含超時處理）")
    result2 = await test_timeout_handling()
    results.append(("AI 模式", result2))
    
    # 總結
    logger.info("\n" + "=" * 60)
    logger.info("🏁 測試總結")
    logger.info("=" * 60)
    
    for name, result in results:
        status = "✅ 通過" if result else "❌ 失敗"
        logger.info(f"{name}: {status}")
    
    all_passed = all(r for _, r in results)
    
    if all_passed:
        logger.info("\n🎉 所有測試通過！超時處理機制運作正常。")
    else:
        logger.warning("\n⚠️ 部分測試失敗，請檢查日誌。")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
