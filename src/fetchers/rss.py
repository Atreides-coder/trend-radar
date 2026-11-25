"""通用 RSS/Atom fetcher：科技媒体和公司官方博客都走这里，靠 sources.yaml 区分。"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone

import feedparser

from .base import BaseFetcher, RawItem, clean_text, register, utcnow


@register("rss")
class RSSFetcher(BaseFetcher):
    def fetch(self) -> list[RawItem]:
        resp = self.get(self.cfg["url"])
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            raise RuntimeError(f"RSS 解析失败：{feed.bozo_exception}")

        # 有些源（如 OpenAI）会把全部历史塞进 feed，只留趋势窗口内的
        cutoff = utcnow() - timedelta(days=self.settings.get("lookback_days", 7))
        max_chars = self.settings.get("fetch", {}).get("summary_max_chars", 500)

        items = []
        for e in feed.entries:
            title = clean_text(e.get("title"), 300)
            if not title:
                continue
            parsed = e.get("published_parsed") or e.get("updated_parsed")
            published = (
                datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None
            )
            if published and published < cutoff:
                continue
            tags = [t.get("term") for t in e.get("tags", []) if t.get("term")]
            items.append(
                RawItem(
                    source=self.name,
                    source_type=self.source_type,
                    external_id=e.get("id") or e.get("link") or "",
                    title=title,
                    summary=clean_text(e.get("summary") or e.get("description"), max_chars),
                    url=e.get("link") or "",
                    author=e.get("author") or "",
                    published_at=published,
                    engagement_score=0,  # RSS 没有互动数据
                    metadata={**self.base_metadata(), "tags": tags[:10]},
                )
            )
        return items
