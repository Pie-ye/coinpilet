import asyncio
import json
from copilot import CopilotClient

async def main():
    # 讀取數據
    with open("data/daily_context.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    client = CopilotClient()
    
    # 建立簡單的 prompt
    price = data["price"]["price_usd"]
    change = data["price"]["price_change_24h"]
    
    prompt = f"""你是一位專業的加密貨幣分析師。

請根據以下數據撰寫一篇簡短的比特幣市場分析（300字以內）：

當前價格: ${price:,.2f}
24H 漲跌: {change:+.2f}%

請使用繁體中文，並以 Markdown 格式輸出，包含以下 Front Matter：

---
title: "比特幣日報 - 2026-02-05"
date: 2026-02-05
---

[你的分析內容]
"""
    
    print("發送請求...")
    session = await client.create_session({"model": "gpt-4.1"})
    response = await session.send_and_wait({"prompt": prompt})
    
    print("\n=== 生成的文章 ===")
    print(response.data.content)
    
    await client.stop()

asyncio.run(main())
