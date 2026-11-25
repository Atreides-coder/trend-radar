"""Phase 3：Signals → Events → Global Ranking → Trends。

三次模型调用，每次都让模型一次看到全部内容（聚类和排名都需要全局上下文）：
  1. Event Clustering   把报道同一件事的 signal 合并成 Event
  2. Global Ranking     对全部 Event 打维度分并强制给出不并列的名次；总分由代码计算
  3. Trend Linking      找出指向同一个更大趋势的不同 Event；优先归入已有趋势（Trend Memory）

模型只返回结构化结果；校验、修复和所有数据库写入都在这里完成。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from ..ai.base import AgentRunner, FatalRunnerError, RunnerError
from ..ai.codex_runner import CodexRunner
from ..ai.schemas import (
    EVENT_CLUSTERING_SCHEMA, EVENT_DIMENSIONS, EVENT_RANKING_SCHEMA, RELATIONSHIPS, TREND_LINKING_SCHEMA,
)
from ..fetchers.base import utcnow
from ..storage.database import Database, filter_window_start, fmt_dt

log = logging.getLogger("trend_radar.cluster")

DEFAULT_WEIGHTS = {
    "audience_relevance": 5, "change_magnitude": 4, "story_potential": 4,
    "trend_potential": 3, "evidence_strength": 2, "visual_potential": 2,
}
ACTIVE_TREND_STATUSES = ("watching", "rising", "selected")


def version(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]


def analysis_cutoff(db: Database, window_days: int) -> str:
    return filter_window_start(db.conn, window_days)


def call(runner: AgentRunner, task: str, prompt: str, payload, schema: dict, check):
    """调用模型并校验。check(data) 返回 (结果, 问题列表)；有问题就重试一次，取问题更少的那次。"""
    best = None
    for attempt in (1, 2):
        try:
            result, problems = check(runner.run(task=task, prompt=prompt, input_data=payload, schema=schema))
        except RunnerError as e:
            log.warning("%s 调用失败（第 %d 次）：%s", task, attempt, e)
            continue
        if best is None or len(problems) < len(best[1]):
            best = (result, problems)
        if not problems:
            break
        log.warning("%s 输出有问题（第 %d 次）：%s", task, attempt, "; ".join(problems))
    if best is None:
        raise RunnerError(f"{task} 两次调用都失败")
    return best


# ------------------------------------------------------------------ 1. clustering

def signal_payload(row) -> dict:
    meta = json.loads(row["metadata_json"] or "{}")
    f = json.loads(row["filter_json"] or "{}")
    d = {
        "item_id": row["id"], "title": row["title"], "summary": row["summary"] or "",
        "source": row["source"], "source_type": row["source_type"],
        "is_official": meta.get("tier") == 1,
        "published_at": (row["published_at"] or "")[:16],
        "possible_change": f.get("possible_change", ""),
        "filter_score": row["filter_score"], "url": row["url"],
    }
    if row["source_type"] == "hackernews":
        d["link_domain"] = urlsplit(row["canonical_url"] or "").netloc
    return d


def check_clustering(data: dict, rows: dict) -> tuple[list[dict], list[str]]:
    """每个输入条目必须恰好属于一个 event。丢掉编造的 id 和重复出现的 id，缺失的补成单条 event。"""
    ids = set(rows)
    seen: set[int] = set()
    invented, duplicate, events = [], [], []
    for ev in data.get("events", []):
        items = []
        for it in ev.get("items", []):
            iid = it.get("item_id")
            if iid not in ids:
                invented.append(iid)
            elif iid in seen:
                duplicate.append(iid)
            else:
                seen.add(iid)
                rel = it.get("relationship") if it.get("relationship") in RELATIONSHIPS else "supporting"
                items.append({"item_id": iid, "relationship": rel, "independent": bool(it.get("independent"))})
        if items:
            events.append({**ev, "items": items, "auto": False})
    missing = sorted(ids - seen)
    for iid in missing:
        row = rows[iid]
        events.append({
            "canonical_title": row["title"], "summary": row["summary"] or "",
            "core_change": json.loads(row["filter_json"] or "{}").get("possible_change", ""),
            "reason": "模型遗漏了这一条，自动单独成组", "auto": True,
            "items": [{"item_id": iid, "relationship": "primary", "independent": False}],
        })
    for ev in events:  # 每个 event 恰好一个 primary
        primaries = [it for it in ev["items"] if it["relationship"] == "primary"]
        if not primaries:
            max(ev["items"], key=lambda it: rows[it["item_id"]]["filter_score"] or 0)["relationship"] = "primary"
        for extra in primaries[1:]:
            extra["relationship"] = "supporting"
    problems = [f"{name} IDs: {vals}" for name, vals in
                (("missing", missing), ("duplicate", duplicate), ("invented", invented)) if vals]
    return events, problems


def event_stats(ev: dict, rows: dict) -> dict:
    items = [(it, rows[it["item_id"]]) for it in ev["items"]]
    metas = {it["item_id"]: json.loads(r["metadata_json"] or "{}") for it, r in items}
    official = {iid for iid, m in metas.items() if m.get("tier") == 1}
    # 来源按"原始出处的域名"去重：HN 帖子算作它链接的那个出处，所以 HN → techcrunch.com 和
    # TechCrunch 自己的条目是同一个来源。independent 只数独立报道的出处，一定 <= source_count。
    origin = lambda r: urlsplit(r["canonical_url"] or "").netloc or r["source"]  # noqa: E731
    all_sources = {origin(r) for _, r in items}
    origins = {origin(r) for it, r in items if it["independent"] and it["item_id"] not in official}
    scores = [r["filter_score"] for _, r in items if r["filter_score"] is not None]
    dates = sorted(r["published_at"] for _, r in items if r["published_at"])
    return {
        "first_seen": dates[0] if dates else None, "last_seen": dates[-1] if dates else None,
        "item_count": len(items), "source_count": len(all_sources),
        "independent_source_count": len(origins), "has_official_source": int(bool(official)),
        "max_filter_score": max(scores) if scores else None,
        "avg_filter_score": round(sum(scores) / len(scores), 1) if scores else None,
        "official_ids": official,
    }


def save_events(db: Database, run_id: int, events: list[dict], rows: dict, now: str) -> list[dict]:
    saved = []
    for ev in events:
        st = event_stats(ev, rows)
        cur = db.conn.execute(
            "INSERT INTO events (run_id, canonical_title, summary, core_change, cluster_reason, first_seen, "
            "last_seen, item_count, source_count, independent_source_count, has_official_source, "
            "max_filter_score, avg_filter_score, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, ev["canonical_title"].strip(), ev["summary"].strip(), ev["core_change"].strip(),
             ev["reason"].strip(), st["first_seen"], st["last_seen"], st["item_count"], st["source_count"],
             st["independent_source_count"], st["has_official_source"], st["max_filter_score"],
             st["avg_filter_score"], now, now))
        event_id = cur.lastrowid
        for it in ev["items"]:
            independent = it["independent"] and it["item_id"] not in st["official_ids"]
            db.conn.execute("INSERT INTO event_items (event_id, raw_item_id, relationship, independent) "
                            "VALUES (?,?,?,?)", (event_id, it["item_id"], it["relationship"], int(independent)))
        saved.append({**ev, **st, "event_id": event_id})
    db.conn.commit()
    return saved


# ------------------------------------------------------------------ 2. ranking

def ranking_payload(ev: dict, rows: dict) -> dict:
    return {
        "event_id": ev["event_id"], "canonical_title": ev["canonical_title"],
        "summary": ev["summary"], "core_change": ev["core_change"],
        "item_count": ev["item_count"], "source_count": ev["source_count"],
        "independent_source_count": ev["independent_source_count"],
        "has_official_source": bool(ev["has_official_source"]),
        "reports": [{
            "source": rows[it["item_id"]]["source"], "title": rows[it["item_id"]]["title"],
            "relationship": it["relationship"], "independent": it["independent"],
            "is_official": it["item_id"] in ev["official_ids"],
        } for it in ev["items"]],
    }


def compute_score(r: dict, weights: dict) -> float:
    return float(sum(r[d] * weights[d] for d in EVENT_DIMENSIONS))


def check_ranking(data: dict, event_ids: list[int], weights: dict) -> tuple[dict[int, dict], list[str]]:
    """每个 event 一个结果；rank 必须是 1..N 的排列。不干净时按 (模型给的 rank, 分数) 重新编号。"""
    valid: dict[int, dict] = {}
    for r in data.get("events", []):
        eid = r.get("event_id")
        if eid in event_ids and eid not in valid and \
                all(isinstance(r.get(d), int) and 0 <= r[d] <= 5 for d in EVENT_DIMENSIONS):
            valid[eid] = {**r, "score": compute_score(r, weights)}
    problems = []
    missing = [e for e in event_ids if e not in valid]
    if missing:
        problems.append(f"missing event ids: {missing}")
    ranks = sorted(r.get("rank") for r in valid.values() if isinstance(r.get("rank"), int))
    if ranks != list(range(1, len(event_ids) + 1)):
        problems.append("rank 不是 1..N 的无并列排列")
    ordered = sorted(valid.values(), key=lambda r: (r["rank"] if isinstance(r.get("rank"), int) else 10 ** 6, -r["score"]))
    for i, r in enumerate(ordered, start=1):
        r["rank"] = i
    return valid, problems


def save_ranking(db: Database, events: list[dict], ranking: dict[int, dict], top_n: int, now: str):
    # 模型两次都漏掉的 event 排在最后，按 Fast Filter 最高分排序
    leftover = sorted((e for e in events if e["event_id"] not in ranking),
                      key=lambda e: -(e["max_filter_score"] or 0))
    for i, ev in enumerate(leftover, start=len(ranking) + 1):
        db.conn.execute("UPDATE events SET rank=?, updated_at=? WHERE id=?", (i, now, ev["event_id"]))
        ev["rank"] = i
    for ev in events:
        r = ranking.get(ev["event_id"])
        if not r:
            continue
        ev.update(rank=r["rank"], score=r["score"], possible_bigger_trend=r["possible_bigger_trend"])
        db.conn.execute(
            "UPDATE events SET rank=?, score=?, audience_relevance=?, change_magnitude=?, story_potential=?, "
            "trend_potential=?, evidence_strength=?, visual_potential=?, why_it_matters=?, "
            "possible_bigger_trend=?, in_research_queue=?, updated_at=? WHERE id=?",
            (r["rank"], r["score"], *(r[d] for d in EVENT_DIMENSIONS), r["why_it_matters"].strip(),
             r["possible_bigger_trend"].strip(), int(r["rank"] <= top_n), now, ev["event_id"]))
    db.conn.commit()


# ------------------------------------------------------------------ 3. trends

def norm(name: str) -> str:
    return re.sub(r"[\W_]+", "", name.lower())


def existing_trends(db: Database) -> list[dict]:
    rows = db.conn.execute(
        f"SELECT * FROM trends WHERE status IN ({','.join('?' * len(ACTIVE_TREND_STATUSES))}) ORDER BY id",
        ACTIVE_TREND_STATUSES).fetchall()
    out = []
    for t in rows:
        aliases = [a["alias"] for a in db.conn.execute(
            "SELECT alias FROM trend_aliases WHERE trend_id=? ORDER BY alias", (t["id"],))]
        out.append({"trend_id": t["id"], "name": t["canonical_name"], "aliases": aliases,
                    "description": t["description"], "last_seen": t["last_seen"]})
    return out


def check_trends(data: dict, event_ids: set[int], known: list[dict]) -> tuple[list[dict], list[str]]:
    known_ids = {t["trend_id"] for t in known}
    by_name = {norm(n): t["trend_id"] for t in known for n in [t["name"], *t["aliases"]]}
    usage: dict[int, int] = {}
    trends = []
    for t in data.get("trends", []):
        ids = list(dict.fromkeys(e for e in t.get("event_ids", []) if e in event_ids and usage.get(e, 0) < 2))
        tid = t.get("existing_trend_id") if t.get("existing_trend_id") in known_ids else 0
        # 名称漂移兜底：模型说是新趋势，但名字或别名和已有趋势完全相同
        tid = tid or next((by_name[norm(n)] for n in [t.get("trend_name", ""), *t.get("aliases", [])]
                           if norm(n) in by_name), 0)
        if not t.get("trend_name", "").strip() or len(ids) < (1 if tid else 2):
            log.warning("丢弃趋势「%s」：支持的 event 不足", t.get("trend_name"))
            continue
        for e in ids:
            usage[e] = usage.get(e, 0) + 1
        same = next((x for x in trends if tid and x["existing_trend_id"] == tid), None)
        if same:  # 两个输出指向同一个已有趋势：合并，不重复记
            same["event_ids"] = list(dict.fromkeys([*same["event_ids"], *ids]))
            same["aliases"] = [*same.get("aliases", []), t["trend_name"], *t.get("aliases", [])]
            continue
        trends.append({**t, "event_ids": ids, "existing_trend_id": tid})
    return trends, []  # 被丢弃的趋势只记录，不触发重试


def save_trends(db: Database, run_id: int, trends: list[dict], now: str) -> int:
    for t in trends:
        tid = t["existing_trend_id"]
        if tid:
            db.conn.execute("UPDATE trends SET description=?, last_seen=?, confidence=?, updated_at=? WHERE id=?",
                            (t["hypothesis"].strip(), now, t["confidence"], now, tid))
        else:
            tid = db.conn.execute(
                "INSERT INTO trends (canonical_name, description, first_seen, last_seen, status, confidence, "
                "created_at, updated_at) VALUES (?,?,?,?, 'watching', ?,?,?)",
                (t["trend_name"].strip(), t["hypothesis"].strip(), now, now, t["confidence"], now, now)).lastrowid
        for alias in {t["trend_name"].strip(), *(a.strip() for a in t.get("aliases", []))} - {""}:
            db.conn.execute("INSERT OR IGNORE INTO trend_aliases (trend_id, alias) VALUES (?,?)", (tid, alias))
        for eid in t["event_ids"]:
            db.conn.execute("INSERT OR REPLACE INTO trend_events (trend_id, event_id, run_id, confidence, hypothesis) "
                            "VALUES (?,?,?,?,?)", (tid, eid, run_id, t["confidence"], t["hypothesis"].strip()))
        # 统计只反映最近一次运行；velocity 在历史不足 7 天时保持 NULL
        agg = db.conn.execute(
            "SELECT count(DISTINCT te.event_id) events, count(DISTINCT ei.raw_item_id) mentions, "
            "count(DISTINCT i.source) sources FROM trend_events te "
            "JOIN event_items ei ON ei.event_id = te.event_id JOIN raw_items i ON i.id = ei.raw_item_id "
            "WHERE te.trend_id=? AND te.run_id=?", (tid, run_id)).fetchone()
        db.conn.execute("UPDATE trends SET event_count=?, mention_count=?, source_count=? WHERE id=?",
                        (agg["events"], agg["mentions"], agg["sources"], tid))
    # 跨天共享的趋势与本轮完成标记一起提交。
    return len(trends)


# ------------------------------------------------------------------ stage

def run_cluster_stage(db: Database, root: Path, settings: dict, *, runner: AgentRunner | None = None,
                      dry_run: bool = False) -> dict:
    started = time.monotonic()
    now = fmt_dt(utcnow())
    cfg = settings.get("cluster", {})
    weights = {**DEFAULT_WEIGHTS, **(cfg.get("weights") or {})}
    top_n = cfg.get("research_top_n", 10)
    cap = settings.get("fast_filter", {}).get("max_signals_for_clustering", 100)
    window = settings.get("filter", {}).get("window_days", settings.get("lookback_days", 7))

    signals = db.conn.execute(
        "SELECT * FROM raw_items WHERE status='candidate' AND published_at >= ? "
        "ORDER BY filter_score DESC, id LIMIT ?", (analysis_cutoff(db, window), cap)).fetchall()
    rows = {r["id"]: r for r in signals}
    log.info("Signals: %d", len(rows))
    if dry_run:
        log.info("--dry-run：跳过聚类")
        return {"status": "dry_run", "signals": len(rows)}
    if not rows:
        run = {"status": "complete", "signals": 0, "events": 0, "trends": 0, "research_queue": 0}
        cur = db.conn.execute(
            "INSERT INTO cluster_runs (started_at, duration_seconds, input_signals, output_events, "
            "output_trends, stats_json) VALUES (?, ?, 0, 0, 0, ?)",
            (now, time.monotonic() - started, json.dumps(run)))
        db.conn.commit()
        log.info("没有候选，已更新为空榜")
        return {**run, "run_id": cur.lastrowid}

    prompts = {name: (root / "prompts" / f"{name}.md").read_text(encoding="utf-8").strip()
               for name in ("event_clustering", "event_ranking", "trend_linking")}
    prompt_version = "/".join(version(p) for p in prompts.values())
    run_id = db.conn.execute(
        "INSERT INTO cluster_runs (started_at, prompt_version, input_signals) VALUES (?,?,?)",
        (now, prompt_version, len(rows))).lastrowid
    db.conn.commit()
    run = {"run_id": run_id, "signals": len(rows), "events": 0, "trends": 0, "problems": [], "steps": {}}

    def step(name, fn):
        t0 = time.monotonic()
        result = fn()
        run["steps"][name] = round(time.monotonic() - t0, 1)
        return result

    try:
        runner = runner or CodexRunner.from_env(settings.get("codex", {}))
        effort = getattr(runner, "reasoning_effort", None)
        db.conn.execute("UPDATE cluster_runs SET runner=?, model=?, reasoning_effort=? WHERE id=?",
                        (f"{runner.name} ({getattr(runner, 'version', '')})", runner.model, effort, run_id))
        db.conn.commit()
        log.info("Model: %s", runner.model)
        log.info("Reasoning effort: %s", effort)

        events, problems = step("clustering", lambda: call(
            runner, "event_clustering", prompts["event_clustering"],
            [signal_payload(r) for r in signals], EVENT_CLUSTERING_SCHEMA,
            lambda data: check_clustering(data, rows)))
        run["problems"] += [f"clustering: {p}" for p in problems]
        events = save_events(db, run_id, events, rows, now)
        run["events"] = len(events)
        log.info("Events: %d (from %d signals)", len(events), len(rows))

        ids = [e["event_id"] for e in events]
        ranking, problems = step("ranking", lambda: call(
            runner, "event_ranking", prompts["event_ranking"],
            [ranking_payload(e, rows) for e in events], EVENT_RANKING_SCHEMA,
            lambda data: check_ranking(data, ids, weights)))
        run["problems"] += [f"ranking: {p}" for p in problems]
        if len(ranking) < min(top_n, len(events)) or not ranking:
            raise RunnerError(f"排名结果不足以生成研究队列：{len(ranking)}/{len(events)} 个事件有评分")
        save_ranking(db, events, ranking, top_n, now)
        run["research_queue"] = min(top_n, len(ranking))

        known = existing_trends(db)
        trends, _ = step("trend_linking", lambda: call(
            runner, "trend_linking", prompts["trend_linking"],
            {"events": [{"event_id": e["event_id"], "rank": e.get("rank"), "canonical_title": e["canonical_title"],
                         "core_change": e["core_change"], "possible_bigger_trend": e.get("possible_bigger_trend", "")}
                        for e in sorted(events, key=lambda e: e.get("rank") or 10 ** 6)],
             "existing_trends": known},
            TREND_LINKING_SCHEMA, lambda data: check_trends(data, set(ids), known)))
        run["trends"] = save_trends(db, run_id, trends, now)
        run["existing_trends_seen"] = len(known)
        run["trends_matched_existing"] = sum(1 for t in trends if t["existing_trend_id"])
        run["status"] = "complete"
    except (FatalRunnerError, RunnerError) as e:
        run["status"] = "failed"
        run["note"] = f"聚类阶段中止：{e}"
        log.error(run["note"])

    if runner:
        run["usage"] = runner.usage.as_dict()
    run["duration_seconds"] = time.monotonic() - started
    db.conn.execute(
        "UPDATE cluster_runs SET duration_seconds=?, output_events=?, output_trends=?, stats_json=? WHERE id=?",
        (run["duration_seconds"], run["events"], run["trends"], json.dumps(run, ensure_ascii=False), run_id))
    db.conn.commit()

    u = run.get("usage", {})
    for p in run["problems"]:
        log.warning("已自动修复：%s", p)
    log.info("Signals: %d → Events: %d → Trends: %d | Research queue: %d",
             run["signals"], run["events"], run["trends"], run.get("research_queue", 0))
    log.info("Codex calls: %d (failed %d) | input tokens: %d | output tokens: %d | %.1fs",
             u.get("calls", 0), u.get("failed_calls", 0), u.get("input_tokens", 0),
             u.get("output_tokens", 0), run["duration_seconds"])
    return run
