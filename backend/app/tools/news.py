from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import quote_plus

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.enums import AgentRole
from app.tools.base import SentinelTool, ToolResult

logger = get_logger(__name__)
_NEWSAPI_URL = "https://newsapi.org/v2/everything"


async def _fetch_rss_news(query: str) -> list[dict[str, Any]]:
    encoded = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        res = await client.get(url)
        if res.status_code != 200:
            return []

        root = ET.fromstring(res.content)
        articles: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            title = item.find("title")
            title_text = title.text if title is not None else ""

            link = item.find("link")
            link_text = link.text if link is not None else ""

            pub_date = item.find("pubDate")
            pub_text = pub_date.text if pub_date is not None else None

            source = item.find("source")
            source_text = source.text if source is not None else "Google News"

            if title_text:
                articles.append({
                    "title": title_text,
                    "source": source_text,
                    "published_at": pub_text,
                    "url": link_text,
                    "snippet": title_text,
                })
            if len(articles) >= 10:
                break
        return articles


class NewsIntelTool(SentinelTool):
    name: ClassVar[str] = "search_news"
    description: ClassVar[str] = (
        "Recent news and open-source reports about a location and hazard, used "
        "to corroborate or challenge the field report. Returns zero results when "
        "no live feed is configured — treat that as an information gap, never as "
        "evidence of absence. Args: query (str), location (str), hours (int)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.SITUATION_ANALYSIS,
        AgentRole.COMMANDER,
        AgentRole.COMMUNICATION,
    )

    def has_live_backend(self, **kwargs: Any) -> bool:
        key = settings.newsapi_key
        return bool(key) and key != "your_newsapi_key_here" and not settings.offline_mode

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query") or kwargs.get("location") or "disaster flood")
        
        # 1. Try NewsAPI if key configured
        if settings.newsapi_key:
            try:
                hours = int(kwargs.get("hours", 24))
                since = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
                params = {
                    "q": query,
                    "from": since,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 10,
                    "apiKey": settings.newsapi_key,
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(_NEWSAPI_URL, params=params)

                if response.status_code == 200:
                    articles = response.json().get("articles", [])
                    if articles:
                        return ToolResult(
                            data={
                                "article_count": len(articles),
                                "feed_available": True,
                                "articles": [
                                    {
                                        "title": a.get("title"),
                                        "source": (a.get("source") or {}).get("name"),
                                        "published_at": a.get("publishedAt"),
                                        "url": a.get("url"),
                                        "snippet": (a.get("description") or "")[:300],
                                    }
                                    for a in articles
                                ],
                            },
                            source="newsapi.org",
                        )
            except Exception as exc:
                logger.warning("newsapi.failed", error=str(exc))

        # 2. Fallback to Google News RSS (Free & Keyless)
        try:
            rss_articles = await _fetch_rss_news(query)
            if rss_articles:
                return ToolResult(
                    data={
                        "article_count": len(rss_articles),
                        "feed_available": True,
                        "articles": rss_articles,
                    },
                    source="google-news-rss",
                )
        except Exception as exc:
            logger.warning("rss_news.failed", error=str(exc))

        return await self.fetch_fallback(**kwargs)

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            data={
                "article_count": 0,
                "feed_available": False,
                "articles": [],
                "information_gap": (
                    "No live news feed is configured. Open-source corroboration is "
                    "UNAVAILABLE for this incident — do not infer that an absence of "
                    "reports means an absence of events."
                ),
            },
            source="none (no synthetic news generated by design)",
        )

