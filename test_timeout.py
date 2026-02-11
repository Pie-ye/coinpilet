import asyncio
from copilot import CopilotClient
import os
from dotenv import load_dotenv

load_dotenv()

async def test_long_generation():
    """測試長時間生成是否能突破 60 秒限制"""
    client = CopilotClient()
    
    # 創建 session (不使用 streaming)
    session = await client.create_session({
        "model": "gpt-4.1"
    })
    
    # 要求生成一篇長文章（應該超過 60 秒）
    prompt = """
請撰寫一篇 2000 字的比特幣市場分析文章，包含以下內容：

1. 市場概況（300 字）
   - 當前價格走勢
   - 24 小時漲跌分析
   - 交易量變化

2. 技術分析（500 字）
   - K 線形態
   - 支撐與壓力位
   - 技術指標（MACD, RSI, 布林通道）
   - 趨勢判斷

3. 基本面分析（500 字）
   - 宏觀經濟環境
   - 機構動態
   - 政策影響
   - 鏈上數據

4. 新聞事件（400 字）
   - 近期重大新聞
   - 影響分析

5. 市場展望（300 字）
   - 短期預測
   - 中期展望
   - 風險提示

請用專業、詳細的語氣撰寫，確保文章內容充實。
"""
    
    print("⏳ 開始生成長文章...")
    print(f"⏰ 測試是否能突破 60 秒限制...")
    
    try:
        # 嘗試不同的 timeout 值
        print("\n📌 測試 1: timeout=300 (5 分鐘)")
        
        import time
        start_time = time.time()
        
        response = await session.send_and_wait(
            {"prompt": prompt},
            timeout=300.0
        )
        
        elapsed = time.time() - start_time
        
        article = response.data.content
        print(f"✅ 成功！")
        print(f"⏱️  實際花費時間: {elapsed:.1f} 秒")
        print(f"📝 生成內容長度: {len(article)} 字元")
        print(f"\n內容預覽:\n{article[:300]}...\n")
        
    except asyncio.TimeoutError as e:
        elapsed = time.time() - start_time
        print(f"❌ 超時錯誤（{elapsed:.1f} 秒後）: {e}")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 錯誤（{elapsed:.1f} 秒後）: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_long_generation())
