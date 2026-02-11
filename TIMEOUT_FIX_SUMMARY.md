# AI 投資模擬超時問題修復摘要

## 問題描述
在 Project Chronos AI 投資模擬專案中，當使用 AI 模型進行投資者決策時，經常出現超時問題，導致模擬中斷。

## 根本原因
1. **超時設置不一致**：投資者決策的超時時間設置為 120 秒，但實際 AI 決策可能需要更長時間
2. **缺乏降級機制**：超時時直接拋出異常導致模擬終止，而不是降級到規則決策
3. **錯誤處理不完善**：沒有統計和追蹤超時/錯誤次數
4. **缺少進度報告**：無法得知模擬進度和決策狀態

## 修復方案

### 1. 增加超時時間（參考 main.py）
- ✅ 將投資者決策超時從 **120 秒** 增加到 **300 秒**（5 分鐘）
- ✅ 與 main.py 中的報告生成方式保持一致

**修改文件**：
- [src/chronos/personas/base.py](src/chronos/personas/base.py#L325)
- [src/chronos/simulator.py](src/chronos/simulator.py#L387)

### 2. 實施智能降級機制
- ✅ 超時時自動降級到規則決策，而不是終止模擬
- ✅ 錯誤時也降級到規則決策，確保模擬連續性
- ✅ 記錄詳細的降級原因和上下文

**降級流程**：
```
AI 決策請求
    ↓
超時 (>300s) / 錯誤
    ↓
記錄統計
    ↓
降級到規則決策
    ↓
繼續模擬
```

### 3. 添加統計追蹤
在模擬器中添加了決策統計：
- `ai_decisions`：成功的 AI 決策次數
- `rule_decisions`：規則決策次數（含降級）
- `timeout_fallbacks`：超時降級次數
- `error_fallbacks`：錯誤降級次數

### 4. 改進日誌和進度報告
- ✅ 添加更詳細的錯誤日誌（包含日期、模型、錯誤類型）
- ✅ 在績效摘要中顯示決策統計
- ✅ 顯示超時和錯誤次數

## 程式碼變更

### src/chronos/personas/base.py
```python
# 超時時間：120 秒 → 300 秒
timeout=300.0  # 5 分鐘超時（與 main.py 保持一致）

# 添加降級日誌
except asyncio.TimeoutError:
    logger.warning(
        f"{self.config.name_zh} AI 決策超時 (>300s)，"
        f"降級為規則決策 [日期: {context.current_date}]"
    )
    return self.make_decision_sync(context)
```

### src/chronos/simulator.py
```python
# 添加統計追蹤
self.stats = {
    "ai_decisions": 0,
    "rule_decisions": 0,
    "timeout_fallbacks": 0,
    "error_fallbacks": 0,
}

# 超時處理
except asyncio.TimeoutError:
    self.stats["timeout_fallbacks"] += 1
    logger.error(f"⏰ {persona.config.name_zh} AI 決策超時 (>300s)")
    logger.info(f"   ↳ 降級為規則決策以繼續模擬 (超時次數: {self.stats['timeout_fallbacks']})")
    self.stats["rule_decisions"] += 1
    return persona.make_decision_sync(context)

# 在績效摘要中顯示統計
if self.config.use_ai:
    total_decisions = self.stats["ai_decisions"] + self.stats["rule_decisions"]
    if total_decisions > 0:
        ai_pct = (self.stats["ai_decisions"] / total_decisions) * 100
        logger.info(f"🤖 AI 決策統計:")
        logger.info(f"   成功: {self.stats['ai_decisions']} 次 ({ai_pct:.1f}%)")
        logger.info(f"   降級: {self.stats['rule_decisions']} 次")
```

## 測試驗證

創建了 [test_timeout_fix.py](test_timeout_fix.py) 測試文件，包含：
1. 同步模式測試（規則決策）
2. AI 模式測試（含超時處理）
3. 統計信息驗證

## 使用方式

```bash
# 正常運行模擬（AI 模式）
python -m src.chronos.scripts.run_simulation --ai --start 2024-01-01 --end 2024-01-03

# 運行超時修復測試
python test_timeout_fix.py

# 查看輸出目錄
ls output/chronos/
ls output/chronos_test/
```

## 預期效果

### 修復前 ❌
- 決策超時直接導致模擬終止
- 無法得知超時發生的原因和頻率
- 浪費已完成的模擬結果

### 修復後 ✅
- 決策超時自動降級到規則決策
- 模擬可以完整執行到結束
- 提供詳細的統計報告
- 可以識別和優化容易超時的投資者

## 進一步優化建議

1. **並行決策**：考慮讓多個投資者並行決策（需要注意 Copilot SDK 的限制）
2. **Prompt 優化**：簡化 prompt 以減少 AI 推理時間
3. **超時預警**：在接近超時時提前警告
4. **模型選擇**：允許不同投資者使用不同速度的模型
5. **緩存機制**：對相似市場狀況的決策進行緩存

## 參考資料

- [main.py](main.py#L379) - 報告生成的 timeout 設置（300 秒）
- [test_timeout.py](test_timeout.py) - 超時測試案例
- Copilot SDK 文檔 - `send_and_wait()` timeout 參數

## 修復日期
2026-02-08

## 版本資訊
- Python: 3.x
- Copilot SDK: 最新版本
- 模型: gemini-3-flash
