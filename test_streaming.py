import asyncio
from copilot import CopilotClient

async def main():
    client = CopilotClient()
    
    # 建立會話 with streaming
    session = await client.create_session({
        "model": "gpt-4.1",
        "streaming": True
    })
    
    # 監聽回應
    full_response = ""
    
    def on_delta(event):
        nonlocal full_response
        full_response += event.data.delta_content
        print(event.data.delta_content, end="", flush=True)
    
    session.on("assistant.message_delta", on_delta)
    
    prompt = """你是專業的加密貨幣分析師。

請根據以下數據撰寫一篇簡短的比特幣分析（200字）：

- 當前價格: $69,156
- 24H 漲跌: -9.07%

請用繁體中文，Markdown 格式。"""
    
    print("發送請求...\n")
    await session.send_and_wait({"prompt": prompt})
    
    print("\n\n=== 完整回應 ===")
    print(f"長度: {len(full_response)} 字元")
    
    await client.stop()

asyncio.run(main())
