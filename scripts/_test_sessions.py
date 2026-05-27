import asyncio
from src.utils.session_manager import check_health

async def main():
    platforms = ['douyin', 'xiaohongshu', 'kuaishou', 'zhihu', 'weibo', 'bilibili', 'tieba']
    for p in platforms:
        try:
            ok = await check_health(p)
            print(f"{p}: {'OK' if ok else 'FAIL'}")
        except Exception as e:
            print(f"{p}: ERROR - {e}")

asyncio.run(main())
