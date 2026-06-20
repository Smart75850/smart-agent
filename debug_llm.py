import httpx, json, asyncio

async def test():
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "http://192.168.1.7:11434/v1/chat/completions",
            json={
                "model": "qwen3:32b",
                "messages": [{"role": "user", "content": "用一句话回答: 你好吗"}],
                "max_tokens": 100,
            },
        )
        print(f"status: {r.status_code}")
        print(f"headers: {dict(r.headers)}")
        data = r.json()
        print(f"keys: {list(data.keys())}")
        if "choices" in data:
            msg = data["choices"][0]["message"]
            print(f"content: {repr(msg.get('content', 'NONE')[:100])}")
            print(f"reasoning: {repr(msg.get('reasoning', 'NONE')[:100])}")
        else:
            print(f"RAW: {json.dumps(data, ensure_ascii=False)[:500]}")

asyncio.run(test())
