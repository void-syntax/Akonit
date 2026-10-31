from __future__ import annotations

import pytest

from app.core.config import settings
from app.pipeline.collectors.base import FetchContext
from app.pipeline.collectors.x_trends import PublicTrendsPageStrategy


class FakeClient:
    def __init__(self):
        self.urls: list[str] = []

    async def get_text(self, url: str, **kwargs) -> str:
        self.urls.append(url)
        if "/azerbaijan/" in url:
            return "<html>no trend cards</html>"
        return """<html><div class="trend-card__list">
        <li><a href="https://x.com/search?q=launch">launch</a> 1200</li>
        </div></html>"""


def test_x_trends_parses_timeline_lists_without_legacy_card_class():
    html = """<html><h2>Latest trends</h2><ol>
    <li><a href="https://twitter.com/search?q=launch">#Launch</a></li>
    <li><a href="https://twitter.com/search?q=release">New release</a></li>
    </ol></html>"""

    events = PublicTrendsPageStrategy()._parse(html, "US")

    assert [event.title for event in events] == ["#Launch", "#New release"]
    assert all(event.country_code == "US" for event in events)


@pytest.mark.asyncio
async def test_x_trends_uses_broad_fallback_when_profile_locale_has_no_cards(monkeypatch):
    monkeypatch.setattr(settings, "default_collect_countries", ["AZ"])
    client = FakeClient()

    events = await PublicTrendsPageStrategy().fetch(
        client,
        FetchContext(countries=["AZ"], limit=10),
    )

    assert len(client.urls) == 2
    assert client.urls[0].endswith("/azerbaijan/")
    assert client.urls[1].endswith("/united-states/")
    assert events
    assert events[0].country_code == "US"
