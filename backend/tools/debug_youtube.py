import asyncio
import re

import httpx

from app.pipeline.collectors.youtube import extract_initial_data

URL = "https://www.youtube.com/results?search_query=trending&sp=CAI%253D"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def main() -> None:
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30, headers=HEADERS
    ) as client:
        resp = await client.get(URL)
        html = resp.text
        print("status", resp.status_code, "len", len(html))
        for marker in ("var ytInitialData = ", "ytInitialData = "):
            print(f"marker {marker!r} at {html.find(marker)}")
        data = extract_initial_data(html)
        print("extracted chars:", len(data) if data else None)
        if data:
            import json

            parsed = json.loads(data)
            print("top keys:", list(parsed.keys()))
            contents = (
                parsed.get("contents")
                or parsed.get("frameworkUpdates")
                or {}
            )
            print("renderer keys sample:", list(contents.keys())[:10])
            text = json.dumps(parsed)
            for key in (
                "videoId",
                "viewCountText",
                "publishedTimeText",
                "richItemRenderer",
                "lockupViewModel",
                "shortsLockupViewModel",
            ):
                print(f"{key}: {text.count(key)}")
            idx = text.find("lockupViewModel")
            if idx > 0:
                print("--- lockupViewModel excerpt ---")
                print(text[idx : idx + 1500])
            browse = parsed["contents"]["twoColumnBrowseResultsRenderer"]
            print("--- browse keys ---")
            print(list(browse.keys()))
            tabs = browse.get("tabs", [])
            print("tabs:", len(tabs))
            if tabs:
                print(json.dumps(tabs[0])[:2000])


if __name__ == "__main__":
    asyncio.run(main())