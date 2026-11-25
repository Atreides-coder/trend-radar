"""Hacker News：走 Algolia 官方搜索 API（一次请求拿全字段，不用逐条请求 Firebase）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .base import BaseFetcher, RawItem, clean_text, register, utcnow

API = "https://hn.algolia.com/api/v1"


@register("hackernews")
class HackerNewsFetcher(BaseFetcher):
    def fetch(self) -> list[RawItem]:
        window_hours = self.settings.get("window_hours", 24)
        since = int((utcnow() - timedelta(hours=window_hours)).timestamp())
        max_items = self.cfg.get("max_items", 100)
        min_points = self.cfg.get("min_points", 50)

        hits: dict[str, dict] = {}
        # 1) 当前首页（Top Stories）
        front = self.get(f"{API}/search", params={"tags": "front_page", "hitsPerPage": 100}).json()
        # 2) 过去 window 内的高分帖（近似 Best Stories）
        best = self.get(
            f"{API}/search",
            params={
                "tags": "story",
                "numericFilters": f"created_at_i>{since},points>={min_points}",
                "hitsPerPage": max_items,
            },
        ).json()
        for listing, hit_list in (("front_page", front["hits"]), ("best_24h", best["hits"])):
            for h in hit_list:
                hits.setdefault(h["objectID"], {**h, "_listing": listing})

        max_chars = self.settings.get("fetch", {}).get("summary_max_chars", 500)
        items = []
        for h in hits.values():
            if not h.get("title"):
                continue
            hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
            points = h.get("points") or 0
            comments = h.get("num_comments") or 0
            items.append(
                RawItem(
                    source=self.name,
                    source_type=self.source_type,
                    external_id=h["objectID"],
                    title=h["title"],
                    summary=clean_text(h.get("story_text"), max_chars),
                    url=h.get("url") or hn_url,
                    author=h.get("author") or "",
                    published_at=datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc),
                    engagement_score=points,
                    metadata={
                        **self.base_metadata(),
                        "points": points,
                        "comments": comments,
                        "hn_url": hn_url,
                        "listing": h["_listing"],
                    },
                )
            )
        items.sort(key=lambda i: i.engagement_score, reverse=True)
        return items[:max_items]
