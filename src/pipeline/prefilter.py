"""确定性 Prefilter：只过滤确定不需要的内容，不替 LLM 做判断。规则在 config/prefilter.yaml。"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta

from ..storage.database import Database, fmt_dt

log = logging.getLogger("trend_radar.prefilter")

# HN 惯例：旧文重发会在标题末尾标年份，如 "RSS Feed Best Practices (2022)"
_YEAR_SUFFIX = re.compile(r"\((19|20)\d\d\)\s*$")


class Rule:
    def __init__(self, cfg: dict):
        self.reason = cfg["reason"]
        self.field = cfg.get("field", "title")
        self.sources = set(cfg.get("sources") or [])
        self.unless_engagement_gte = cfg.get("unless_engagement_gte")
        if self.field == "tags":
            self.tags = set(cfg["patterns"])
        else:
            self.regexes = [re.compile(p, re.IGNORECASE) for p in cfg["patterns"]]

    def matches(self, row, tags: list[str]) -> bool:
        if self.sources and row["source"] not in self.sources:
            return False
        if self.unless_engagement_gte is not None and \
                (row["engagement_score"] or 0) >= self.unless_engagement_gte:
            return False
        if self.field == "tags":
            return bool(self.tags.intersection(tags))
        text = row["title"] if self.field == "title" else (row["url"] or "")
        return any(r.search(text) for r in self.regexes)


def reject_reason(row, rules: list[Rule], cutoff: str, this_year: int) -> str | None:
    if row["published_at"] and row["published_at"] < cutoff:
        return "old_information"
    m = _YEAR_SUFFIX.search(row["title"])
    if m and int(m.group(0).strip("() \t")) < this_year:
        return "old_information"
    tags = (json.loads(row["metadata_json"] or "{}").get("tags")) or []
    for rule in rules:
        if rule.matches(row, tags):
            return rule.reason
    return None


def run_prefilter(db: Database, rules_cfg: dict, window_days: int, now: datetime) -> Counter:
    """处理所有 status='new' 的条目。被拒的 → discarded；通过的保持 new，等 LLM。"""
    rules = [Rule(r) for r in rules_cfg.get("rules", [])]
    cutoff = fmt_dt(now - timedelta(days=window_days))
    rows = db.conn.execute(
        "SELECT * FROM raw_items WHERE status = 'new' "
        "AND coalesce(human_override, '') != 'restored'").fetchall()

    removed: Counter = Counter()
    for row in rows:
        reason = reject_reason(row, rules, cutoff, now.year)
        if reason:
            removed[reason] += 1
            db.conn.execute(
                "UPDATE raw_items SET status='discarded', filter_stage='prefilter', "
                "filter_reason=?, filtered_at=? WHERE id=?",
                (reason, fmt_dt(now), row["id"]),
            )
    db.conn.commit()
    log.info("Prefilter: checked %d, removed %d, passed %d  %s",
             len(rows), sum(removed.values()), len(rows) - sum(removed.values()), dict(removed))
    return removed
