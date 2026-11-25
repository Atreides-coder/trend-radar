"""GitHub Trending：没有官方 API，解析 github.com/trending 的静态 HTML（不需要 Playwright）。"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import BaseFetcher, RawItem, clean_text, register


def _to_int(text: str | None) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


@register("github_trending")
class GitHubTrendingFetcher(BaseFetcher):
    def fetch(self) -> list[RawItem]:
        since = self.cfg.get("since", "daily")
        seen: dict[str, RawItem] = {}
        for lang in self.cfg.get("languages") or [""]:
            url = "https://github.com/trending" + (f"/{lang}" if lang else "")
            soup = BeautifulSoup(self.get(url, params={"since": since}).text, "html.parser")
            rows = soup.select("article.Box-row")
            if not rows:
                raise RuntimeError(f"GitHub Trending 页面结构可能变了：{url} 没解析到任何 repo")
            for row in rows:
                link = row.select_one("h2 a")
                if not link or not link.get("href"):
                    continue
                repo = link["href"].strip("/")
                if repo in seen:
                    continue
                desc = row.select_one("p")
                lang_el = row.select_one('[itemprop="programmingLanguage"]')
                stars_el = row.select_one(f'a[href="/{repo}/stargazers"]')
                today_el = row.find(string=re.compile(r"stars? (today|this week|this month)"))
                stars_today = _to_int(today_el)
                seen[repo] = RawItem(
                    source=self.name,
                    source_type=self.source_type,
                    external_id=repo,
                    title=repo,
                    summary=clean_text(desc.get_text() if desc else ""),
                    url=f"https://github.com/{repo}",
                    author=repo.split("/")[0],
                    published_at=None,  # trending 没有发布时间，入库时用 fetched_at
                    engagement_score=stars_today,
                    metadata={
                        **self.base_metadata(),
                        "language": lang_el.get_text(strip=True) if lang_el else None,
                        "stars_total": _to_int(stars_el.get_text() if stars_el else ""),
                        "stars_today": stars_today,
                        "since": since,
                    },
                )
        return list(seen.values())
