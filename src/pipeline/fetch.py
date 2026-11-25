"""Fetch 阶段：并发抓所有 source，单个 source 失败不影响其他。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..fetchers import FETCHERS, RawItem
from ..fetchers.base import utcnow
from ..storage.database import Database

log = logging.getLogger("trend_radar.fetch")


@dataclass
class SourceResult:
    source: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    error: str | None = None


def _fetch_one(source_cfg: dict, settings: dict) -> tuple[list[RawItem], str | None]:
    try:
        fetcher_cls = FETCHERS.get(source_cfg.get("type"))
        if fetcher_cls is None:
            return [], f"未知的 source type: {source_cfg.get('type')}"
        return fetcher_cls(source_cfg, settings).fetch(), None
    except Exception as e:  # 任何 source 出错都只记录，不中断
        return [], f"{type(e).__name__}: {e}"


def run_fetch(db: Database, sources: list[dict], settings: dict, debug: bool = False) -> list[SourceResult]:
    sources = [s for s in sources if s.get("enabled", True)]
    fetch_cfg = settings.get("fetch", {})
    now = utcnow()

    with ThreadPoolExecutor(max_workers=fetch_cfg.get("max_workers", 8)) as pool:
        outcomes = list(pool.map(lambda s: _fetch_one(s, settings), sources))

    results = []
    for src, (items, error) in zip(sources, outcomes):
        res = SourceResult(source=src["name"], error=error)
        if debug:
            items = items[: fetch_cfg.get("debug_limit_per_source", 10)]
        if error:
            log.error("%s fetch failed. %s", src["name"], error)
        else:
            res.fetched = len(items)
            res.inserted, res.updated = db.upsert_items(items, now)
            log.info("%-24s fetched=%-4d new=%-4d updated=%d",
                     src["name"], res.fetched, res.inserted, res.updated)
        db.log_fetch_run(now, res.source, res.fetched, res.inserted, res.updated, error)
        results.append(res)

    failed = [r.source for r in results if r.error]
    log.info("Fetched: %d (new %d, updated %d) from %d/%d sources",
             sum(r.fetched for r in results), sum(r.inserted for r in results),
             sum(r.updated for r in results), len(results) - len(failed), len(results))
    for name in failed:
        log.warning("%s fetch failed.", name)
    return results
