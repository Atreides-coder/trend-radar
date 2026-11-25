"""Fetcher 基类与统一数据结构。Fetcher 只负责抓取，不做理解/打分。"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

FETCHERS: dict[str, type["BaseFetcher"]] = {}


@dataclass
class RawItem:
    source: str
    source_type: str
    title: str
    summary: str = ""
    url: str = ""
    author: str = ""
    published_at: datetime | None = None
    engagement_score: float = 0
    external_id: str = ""
    metadata: dict = field(default_factory=dict)


def register(source_type: str):
    """新增数据源：写一个 BaseFetcher 子类并用 @register("类型名") 装饰即可。"""

    def deco(cls):
        cls.source_type = source_type
        FETCHERS[source_type] = cls
        return cls

    return deco


class BaseFetcher:
    source_type = ""

    def __init__(self, source_cfg: dict, settings: dict):
        self.cfg = source_cfg
        self.settings = settings
        self.name = source_cfg["name"]
        http = settings.get("http", {})
        self.retries = http.get("retries", 2)
        self.client = httpx.Client(
            timeout=http.get("timeout_seconds", 20),
            headers={"User-Agent": http.get("user_agent", "TrendRadar/1.0")},
            follow_redirects=True,
        )

    def get(self, url: str, **kwargs) -> httpx.Response:
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.client.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_err = e
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500 \
                        and e.response.status_code != 429:
                    break
                time.sleep(1.5 * (attempt + 1))
        raise last_err

    def base_metadata(self) -> dict:
        return {"category": self.cfg.get("category"), "tier": self.cfg.get("tier")}

    def fetch(self) -> list[RawItem]:
        raise NotImplementedError


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(text: str | None, max_chars: int = 500) -> str:
    if not text:
        return ""
    text = _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text))).strip()
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
