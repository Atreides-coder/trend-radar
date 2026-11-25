"""Trend Radar 工作台 API，提供选题数据、人工反馈、社区检索和本地视频素材管理。

视频制作通过独立的 pipeline 进程启动，模型配置来自项目 .env。
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Literal

import yaml
from dotenv import dotenv_values
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..storage.database import Database, filter_window_start, latest_filter_run
from ..video import project as vp

ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}
DB_PATH = ROOT / SETTINGS.get("database", "data/trend_radar.db")
EVENT_DIMS = ["audience_relevance", "change_magnitude", "story_potential",
              "trend_potential", "evidence_strength", "visual_potential"]
DIMS = ["change_signal", "ordinary_people", "story_potential", "trend_potential", "visual_potential"]
HUMAN_STATUSES = {"none", "interested", "not_interested", "watch", "strong_topic"}
BORDERLINE = (45, 65)

Database(DB_PATH).close()  # 确保表结构是最新的
app = FastAPI(title="Trend Radar Dashboard")


def get_db():
    # 依赖和路由函数可能在线程池的不同线程里执行；timeout 让它在 pipeline 写库时等一下而不是报错
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def window_days() -> int:
    return SETTINGS.get("filter", {}).get("window_days", SETTINGS.get("lookback_days", 7))


def latest_run(db) -> sqlite3.Row | None:
    return latest_filter_run(db)


def cutoff(db) -> str:
    return filter_window_start(db, window_days())


def engagement(row) -> dict | None:
    meta = json.loads(row["metadata_json"] or "{}")
    if row["source_type"] == "hackernews":
        return {"label": f"{meta.get('points', 0)} 分 · {meta.get('comments', 0)} 评论",
                "hn_url": meta.get("hn_url")}
    if row["source_type"] == "github_trending":
        return {"label": f"+{meta.get('stars_today', 0)} ★ 今日 · 共 {meta.get('stars_total', 0):,} ★"
                         + (f" · {meta['language']}" if meta.get("language") else "")}
    return None


def item_dict(row) -> dict:
    f = json.loads(row["filter_json"]) if row["filter_json"] else None
    is_candidate = row["status"] == "candidate"
    meta = json.loads(row["metadata_json"] or "{}")
    return {
        "id": row["id"], "title": row["title"], "summary": row["summary"], "url": row["url"],
        "source": row["source"], "source_type": row["source_type"],
        "category": meta.get("category"), "tier": meta.get("tier"), "tags": meta.get("tags") or [],
        "published_at": row["published_at"], "fetched_at": row["fetched_at"],
        "engagement": engagement(row),
        "status": row["status"], "stage": row["filter_stage"],
        "score": row["filter_score"], "reason_code": row["filter_reason"],
        "filter": f,
        "llm_keep": bool(f["keep"]) if f else None,
        # 模型自己的 keep 判断和代码按分数得出的结论不一致
        "mismatch": bool(f) and row["human_override"] != "restored" and bool(f["keep"]) != is_candidate,
        "human_status": row["human_status"] or "none", "human_note": row["human_note"] or "",
        "human_updated_at": row["human_updated_at"], "restored": row["human_override"] == "restored",
    }


def window_items(db) -> list[dict]:
    rows = db.execute("SELECT * FROM raw_items WHERE published_at >= ? ORDER BY id", (cutoff(db),))
    return [item_dict(r) for r in rows]


def run_dict(row) -> dict:
    stats = json.loads(row["stats_json"] or "{}")
    return {
        "id": row["id"], "started_at": row["started_at"], "duration_seconds": row["duration_seconds"],
        "runner": row["runner"], "model": row["model"], "reasoning_effort": row["reasoning_effort"],
        "prompt_version": row["prompt_version"],
        "usage": stats.get("usage") or {}, "fast_filter": stats.get("fast_filter") or {},
        "selection": stats.get("selection") or {}, "note": stats.get("note"),
        "prefilter_removed": stats.get("prefilter_removed") or {},
    }


def latest_cluster_run(db) -> sqlite3.Row | None:
    # 旧运行没有 status，最后一步完成且未记录中止时才可作为默认榜单。
    return db.execute("""
        SELECT * FROM cluster_runs
        WHERE json_extract(stats_json, '$.status') = 'complete'
           OR (json_extract(stats_json, '$.status') IS NULL
               AND json_extract(stats_json, '$.steps.trend_linking') IS NOT NULL
               AND json_extract(stats_json, '$.note') IS NULL)
        ORDER BY id DESC LIMIT 1
    """).fetchone()


def cluster_run_dict(row) -> dict:
    stats = json.loads(row["stats_json"] or "{}")
    return {
        "id": row["id"], "started_at": row["started_at"], "duration_seconds": row["duration_seconds"],
        "runner": row["runner"], "model": row["model"], "reasoning_effort": row["reasoning_effort"],
        "prompt_version": row["prompt_version"], "input_signals": row["input_signals"],
        "output_events": row["output_events"], "output_trends": row["output_trends"],
        "research_queue": stats.get("research_queue"), "usage": stats.get("usage") or {},
        "problems": stats.get("problems") or [], "note": stats.get("note"), "steps": stats.get("steps") or {},
    }


def event_dict(row) -> dict:
    d = {k: row[k] for k in (
        "id", "run_id", "canonical_title", "summary", "core_change", "cluster_reason", "first_seen",
        "last_seen", "item_count", "source_count", "independent_source_count", "max_filter_score",
        "avg_filter_score", "rank", "score", "why_it_matters", "possible_bigger_trend", "status")}
    d["has_official_source"] = bool(row["has_official_source"])
    d["in_research_queue"] = bool(row["in_research_queue"])
    d["dims"] = {k: row[k] for k in EVENT_DIMS} if row["score"] is not None else None
    return d


def event_items(db, event_id: int) -> list[dict]:
    order = "CASE ei.relationship WHEN 'primary' THEN 0 WHEN 'official_source' THEN 1 WHEN 'supporting' THEN 2 " \
            "WHEN 'duplicate_report' THEN 3 ELSE 4 END"
    rows = db.execute(
        f"SELECT i.*, ei.relationship, ei.independent FROM event_items ei JOIN raw_items i ON i.id = ei.raw_item_id "
        f"WHERE ei.event_id = ? ORDER BY {order}, i.filter_score DESC", (event_id,)).fetchall()
    return [{**item_dict(r), "relationship": r["relationship"], "independent": bool(r["independent"])} for r in rows]


def events_of_run(db, run_id: int, with_items: bool = True) -> list[dict]:
    rows = db.execute("SELECT * FROM events WHERE run_id = ? ORDER BY rank IS NULL, rank, id", (run_id,)).fetchall()
    out = []
    for r in rows:
        e = event_dict(r)
        if with_items:
            e["items"] = event_items(db, r["id"])
        e["trends"] = [dict(t) for t in db.execute(
            "SELECT t.id, t.canonical_name FROM trend_events te JOIN trends t ON t.id = te.trend_id "
            "WHERE te.event_id = ?", (r["id"],))]
        out.append(e)
    return out


def histogram(scores: list[float]) -> list[dict]:
    buckets = Counter(min(int(s) // 10 * 10, 90) for s in scores)
    return [{"from": b, "to": 100 if b == 90 else b + 9, "count": buckets.get(b, 0)} for b in range(0, 100, 10)]


def current_config() -> dict:
    env = dotenv_values(ROOT / ".env")
    return {"model": env.get("CODEX_MODEL") or None,
            "reasoning_effort": env.get("CODEX_REASONING_EFFORT") or None,
            "runner": "Codex CLI", "fast_filter": SETTINGS.get("fast_filter", {}),
            "window_days": window_days()}


# ---------------------------------------------------------------- overview / meta

@app.get("/api/meta")
def meta(db=Depends(get_db)):
    items = window_items(db)
    return {
        "config": current_config(),
        "sources": sorted({i["source"] for i in items}),
        "reasons": sorted({i["reason_code"] for i in items if i["reason_code"]}),
        "statuses": sorted({i["status"] for i in items}),
        "dims": DIMS, "borderline": BORDERLINE,
    }


@app.get("/api/overview")
def overview(db=Depends(get_db)):
    items = window_items(db)
    by_status = Counter(i["status"] for i in items)
    pre_removed = sum(1 for i in items if i["stage"] == "prefilter" and i["status"] == "discarded")
    evaluated = [i for i in items if i["stage"] == "llm"]
    run = latest_run(db)
    fetch = db.execute(
        "SELECT run_at, sum(fetched) fetched, sum(inserted) inserted, count(*) sources, "
        "group_concat(CASE WHEN error IS NOT NULL THEN source END) failed "
        "FROM fetch_runs WHERE run_at = (SELECT max(run_at) FROM fetch_runs)").fetchone()
    cfg_sources = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    per_source: dict[str, dict] = {}
    for i in items:
        s = per_source.setdefault(i["source"], {"source": i["source"], "raw": 0, "evaluated": 0, "candidates": 0})
        s["raw"] += 1
        s["evaluated"] += i["stage"] == "llm"
        s["candidates"] += i["status"] == "candidate"
    crun = latest_cluster_run(db)
    n_trends = db.execute("SELECT count(*) FROM trends WHERE status IN ('watching','rising','selected')").fetchone()[0]
    return {
        "last_cluster_run": cluster_run_dict(crun) if crun else None,
        "funnel": {
            "signals": by_status["candidate"],
            "events": crun["output_events"] if crun else None,
            "trends": n_trends if crun else None,
            "research_queue": db.execute("SELECT count(*) FROM events WHERE run_id = ? AND in_research_queue = 1",
                                         (crun["id"],)).fetchone()[0] if crun else None,
            "raw": len(items), "prefilter_removed": pre_removed,
            "after_prefilter": len(items) - pre_removed, "evaluated": len(evaluated),
            "candidates": by_status["candidate"], "rejected": by_status["filtered"],
            "pending": by_status["new"],
        },
        "sources_configured": sum(1 for s in cfg_sources if s.get("enabled", True)),
        "sources_with_items": len(per_source),
        "per_source": sorted(per_source.values(), key=lambda s: (-s["candidates"], -s["raw"])),
        "last_fetch": dict(fetch) if fetch and fetch["run_at"] else None,
        "last_run": run_dict(run) if run else None,
        "config": current_config(),
        "distribution": histogram([i["score"] for i in evaluated]),
        "feedback": dict(Counter(i["human_status"] for i in items if i["human_status"] != "none")),
        "restored": sum(i["restored"] for i in items),
        "mismatch": sum(i["mismatch"] for i in items),
    }


# ---------------------------------------------------------------- items

SORTS = {
    "score_desc": lambda i: (-(i["score"] if i["score"] is not None else -1), i["id"]),
    "score_asc": lambda i: (i["score"] if i["score"] is not None else 999, i["id"]),
    "date_desc": lambda i: (i["published_at"] or "",),
    "source": lambda i: (i["source"], -(i["score"] or 0)),
}


@app.get("/api/items")
def items(view: str = "raw", source: str = "", status: str = "", reason: str = "", stage: str = "",
          human: str = "", q: str = "", date: str = "", sort: str = "",
          include_prefilter: bool = False, db=Depends(get_db)):
    data = window_items(db)
    if view == "candidates":
        data = [i for i in data if i["status"] == "candidate"]
    elif view == "rejected":
        keep = {"filtered", "discarded"} if include_prefilter else {"filtered"}
        data = [i for i in data if i["status"] in keep]
    elif view == "borderline":
        lo, hi = BORDERLINE
        data = [i for i in data if i["stage"] == "llm"
                and (lo <= (i["score"] or 0) <= hi or i["mismatch"])]
    elif view == "watch":
        data = [i for i in data if i["human_status"] in ("watch", "strong_topic", "interested")]
    total_in_view = len(data)

    if source:
        data = [i for i in data if i["source"] == source]
    if status:
        data = [i for i in data if i["status"] == status]
    if stage:
        data = [i for i in data if i["stage"] == stage]
    if reason:
        data = [i for i in data if i["reason_code"] == reason]
    if human:
        data = [i for i in data if i["human_status"] == human]
    if date:
        data = [i for i in data if (i["published_at"] or "").startswith(date)]
    if q:
        needle = q.lower()
        data = [i for i in data if needle in i["title"].lower() or needle in (i["summary"] or "").lower()]

    sort = sort or ("date_desc" if view == "raw" else "score_desc")
    data.sort(key=SORTS.get(sort, SORTS["score_desc"]), reverse=(sort == "date_desc"))
    return {"items": data, "total": len(data), "total_in_view": total_in_view}


def get_row(db, item_id: int):
    row = db.execute("SELECT * FROM raw_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "item not found")
    return row


@app.get("/api/items/{item_id}")
def item_detail(item_id: int, db=Depends(get_db)):
    item = item_dict(get_row(db, item_id))
    evals = db.execute(
        "SELECT e.*, r.started_at FROM filter_evaluations e LEFT JOIN filter_runs r ON r.id = e.run_id "
        "WHERE e.raw_item_id = ? ORDER BY e.id DESC", (item_id,)).fetchall()
    item["evaluations"] = [{
        "run_id": e["run_id"], "started_at": e["started_at"], "model": e["model"],
        "reasoning_effort": e["reasoning_effort"], "prompt_version": e["prompt_version"],
        "score": e["score"], "dims": {d: e[d] for d in DIMS}, "llm_keep": bool(e["llm_keep"]),
        "reject_reason": e["reject_reason"], "selected": bool(e["selected"]),
        "final_reason": e["final_reason"], "result": json.loads(e["result_json"] or "{}"),
    } for e in evals]
    crun = latest_cluster_run(db)
    ev = db.execute("SELECT e.id, e.canonical_title, e.rank, ei.relationship FROM event_items ei "
                    "JOIN events e ON e.id = ei.event_id WHERE ei.raw_item_id = ? AND e.run_id = ?",
                    (item_id, crun["id"])).fetchone() if crun else None
    item["event"] = dict(ev) if ev else None
    return item


class Feedback(BaseModel):
    human_status: str | None = None
    human_note: str | None = None


@app.post("/api/items/{item_id}/feedback")
def feedback(item_id: int, body: Feedback, db=Depends(get_db)):
    get_row(db, item_id)
    if body.human_status is not None:
        if body.human_status not in HUMAN_STATUSES:
            raise HTTPException(400, f"human_status 必须是 {sorted(HUMAN_STATUSES)} 之一")
        db.execute("UPDATE raw_items SET human_status = ?, human_updated_at = ? WHERE id = ?",
                   (None if body.human_status == "none" else body.human_status, now_utc(), item_id))
    if body.human_note is not None:
        db.execute("UPDATE raw_items SET human_note = ?, human_updated_at = ? WHERE id = ?",
                   (body.human_note.strip() or None, now_utc(), item_id))
    db.commit()
    return item_dict(get_row(db, item_id))


@app.post("/api/items/{item_id}/restore")
def restore(item_id: int, db=Depends(get_db)):
    """人工把被拒的条目恢复为 candidate。之后的筛选不会再把它降级。"""
    row = get_row(db, item_id)
    if row["status"] not in ("filtered", "discarded"):
        raise HTTPException(400, "只有被拒绝的条目可以恢复")
    db.execute("UPDATE raw_items SET status = 'candidate', human_override = 'restored', "
               "human_updated_at = ? WHERE id = ?", (now_utc(), item_id))
    db.commit()
    return item_dict(get_row(db, item_id))


@app.post("/api/items/{item_id}/unrestore")
def unrestore(item_id: int, db=Depends(get_db)):
    row = get_row(db, item_id)
    if row["human_override"] != "restored":
        raise HTTPException(400, "这条不是人工恢复的")
    back = "discarded" if row["filter_stage"] == "prefilter" else "filtered"
    db.execute("UPDATE raw_items SET status = ?, human_override = NULL, human_updated_at = ? "
               "WHERE id = ?", (back, now_utc(), item_id))
    db.commit()
    return item_dict(get_row(db, item_id))


# ---------------------------------------------------------------- runs

def run_evals(db, run_id: int) -> list[dict]:
    rows = db.execute(
        "SELECT e.*, i.title, i.source, i.url, i.url_hash, i.source_type, i.metadata_json, i.published_at "
        "FROM filter_evaluations e JOIN raw_items i ON i.id = e.raw_item_id "
        "WHERE e.run_id = ? ORDER BY e.score DESC, e.raw_item_id", (run_id,)).fetchall()
    out = []
    for e in rows:
        r = json.loads(e["result_json"] or "{}")
        out.append({
            "item_id": e["raw_item_id"], "title": e["title"], "source": e["source"], "url": e["url"],
            "url_hash": e["url_hash"], "engagement": engagement(e), "score": e["score"],
            "dims": {d: e[d] for d in DIMS}, "llm_keep": bool(e["llm_keep"]),
            "selected": bool(e["selected"]), "reject_reason": e["reject_reason"],
            "final_reason": e["final_reason"], "reason": r.get("reason", ""),
            "possible_change": r.get("possible_change", ""),
        })
    return out


def run_summary(evals: list[dict]) -> dict:
    lo, hi = BORDERLINE
    scores = [e["score"] for e in evals]
    return {
        "evaluated": len(evals), "candidates": sum(e["selected"] for e in evals),
        "llm_keep": sum(e["llm_keep"] for e in evals),
        "mismatch": sum(e["llm_keep"] != e["selected"] for e in evals),
        "borderline": sum(lo <= s <= hi for s in scores),
        "mean_score": round(mean(scores), 1) if scores else None,
        "min_candidate_score": min((e["score"] for e in evals if e["selected"]), default=None),
        # 五个维度打成同一个分：模型没有真正区分维度的迹象
        "flat_scores": sum(len(set(e["dims"].values())) == 1 for e in evals),
        "distribution": histogram(scores),
    }


@app.get("/api/runs")
def runs(db=Depends(get_db)):
    out = []
    for r in db.execute("SELECT * FROM filter_runs ORDER BY id DESC").fetchall():
        d = run_dict(r)
        agg = db.execute("SELECT count(*) n, coalesce(sum(selected), 0) c FROM filter_evaluations "
                         "WHERE run_id = ?", (r["id"],)).fetchone()
        d.update(evaluated=agg["n"], candidates=agg["c"])
        # 成功的增量筛选可能零评估；保留实际失败记录，便于查看失败原因。
        if agg["n"] or d["fast_filter"] or (d["note"] and not d["note"].startswith("DRY RUN")):
            out.append(d)
    return {"runs": out}


def get_run(db, run_id: int):
    row = db.execute("SELECT * FROM filter_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "run not found")
    return row


@app.get("/api/runs/compare")
def compare(a: int = Query(...), b: int = Query(...), db=Depends(get_db)):
    ra, rb = run_dict(get_run(db, a)), run_dict(get_run(db, b))
    ea, eb = run_evals(db, a), run_evals(db, b)
    ma, mb = {e["item_id"]: e for e in ea}, {e["item_id"]: e for e in eb}
    common = [i for i in ma if i in mb]

    rows = []
    for i in common:
        x, y = ma[i], mb[i]
        rows.append({"item_id": i, "title": x["title"], "source": x["source"], "url": x["url"],
                     "engagement": x["engagement"], "a": x, "b": y, "delta": y["score"] - x["score"]})
    rows.sort(key=lambda r: -abs(r["delta"]))

    top = lambda evals, n: [e["item_id"] for e in evals[:n]]  # noqa: E731
    sel_a = {i for i in common if ma[i]["selected"]}
    sel_b = {i for i in common if mb[i]["selected"]}

    # 不同来源指向同一个链接的条目：同一件事在同一次运行里得分差多少
    groups: dict[str, list[int]] = {}
    for i in common:
        if ma[i]["url_hash"]:
            groups.setdefault(ma[i]["url_hash"], []).append(i)
    same_story = []
    for ids in groups.values():
        if len(ids) > 1:
            sa, sb = [ma[i]["score"] for i in ids], [mb[i]["score"] for i in ids]
            same_story.append({"title": ma[ids[0]]["title"], "sources": [ma[i]["source"] for i in ids],
                               "a_scores": sa, "b_scores": sb,
                               "a_spread": max(sa) - min(sa), "b_spread": max(sb) - min(sb)})

    return {
        "a": {**ra, "summary": run_summary(ea)}, "b": {**rb, "summary": run_summary(eb)},
        "common": len(common),
        "top20_overlap": len(set(top(ea, 20)) & set(top(eb, 20))),
        "candidates_both": len(sel_a & sel_b), "candidates_only_a": len(sel_a - sel_b),
        "candidates_only_b": len(sel_b - sel_a),
        "mean_abs_delta": round(mean(abs(r["delta"]) for r in rows), 1) if rows else None,
        "same_story": same_story, "items": rows,
    }


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int, db=Depends(get_db)):
    row = get_run(db, run_id)
    evals = run_evals(db, run_id)
    return {**run_dict(row), "prompt_text": row["prompt_text"], "summary": run_summary(evals),
            "evaluations": evals}


# ---------------------------------------------------------------- events / trends

@app.get("/api/events")
def events(run_id: int | None = None, db=Depends(get_db)):
    run = db.execute("SELECT * FROM cluster_runs WHERE id = ?", (run_id,)).fetchone() if run_id \
        else latest_cluster_run(db)
    if not run:
        return {"run": None, "events": []}
    return {"run": cluster_run_dict(run), "events": events_of_run(db, run["id"])}


@app.get("/api/events/{event_id}")
def event_detail(event_id: int, db=Depends(get_db)):
    row = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, "event not found")
    e = event_dict(row)
    e["items"] = event_items(db, event_id)
    e["trends"] = [dict(t) for t in db.execute(
        "SELECT t.id, t.canonical_name, te.hypothesis, te.confidence FROM trend_events te "
        "JOIN trends t ON t.id = te.trend_id WHERE te.event_id = ?", (event_id,))]
    e["total_events"] = db.execute("SELECT count(*) FROM events WHERE run_id = ?", (row["run_id"],)).fetchone()[0]
    run = db.execute("SELECT * FROM cluster_runs WHERE id = ?", (row["run_id"],)).fetchone()
    e["run"] = cluster_run_dict(run) if run else None
    return e


def trend_dict(db, row, with_events: bool = False) -> dict:
    t = dict(row)
    t["aliases"] = [a["alias"] for a in db.execute(
        "SELECT alias FROM trend_aliases WHERE trend_id = ? AND alias != ? ORDER BY alias",
        (row["id"], row["canonical_name"]))]
    crun = latest_cluster_run(db)
    evs = db.execute(
        "SELECT e.* FROM trend_events te JOIN events e ON e.id = te.event_id "
        "WHERE te.trend_id = ? AND te.run_id = ? ORDER BY e.rank IS NULL, e.rank",
        (row["id"], crun["id"] if crun else -1)).fetchall()
    t["events"] = []
    for e in evs:
        d = event_dict(e)
        if with_events:
            d["items"] = event_items(db, e["id"])
        t["events"].append(d)
    t["in_latest_run"] = bool(evs)
    return t


@app.get("/api/trends")
def trends(db=Depends(get_db)):
    rows = db.execute("SELECT * FROM trends ORDER BY confidence DESC, event_count DESC, id").fetchall()
    return {"trends": [trend_dict(db, r) for r in rows]}


@app.get("/api/trends/{trend_id}")
def trend_detail(trend_id: int, db=Depends(get_db)):
    row = db.execute("SELECT * FROM trends WHERE id = ?", (trend_id,)).fetchone()
    if not row:
        raise HTTPException(404, "trend not found")
    return trend_dict(db, row, with_events=True)


@app.get("/api/cluster-runs")
def cluster_runs(db=Depends(get_db)):
    rows = db.execute("SELECT * FROM cluster_runs ORDER BY id DESC").fetchall()
    return {"runs": [cluster_run_dict(r) for r in rows]}


# ---------------------------------------------------------------- watchlist

@app.get("/api/watchlist")
def watchlist(db=Depends(get_db)):
    marked = db.execute("SELECT * FROM raw_items WHERE human_status IN ('watch','strong_topic','interested') "
                        "ORDER BY human_updated_at DESC").fetchall()
    return {"items": [item_dict(r) for r in marked]}


# ---------------------------------------------------------------- video studio
# Dashboard 只负责启动和查看：真正的生产流程是独立的 Python 进程（src.video.pipeline），由它去调用 Codex。

def _video(project_id: str) -> vp.Project:
    proj = vp.Project(project_id)
    if not re.fullmatch(r"[a-z0-9-]+", project_id) or not proj.state:
        raise HTTPException(404, "video project not found")
    return proj


def _editable_video(project_id: str) -> vp.Project:
    proj = _video(project_id)
    if proj.is_directed:
        raise HTTPException(409, "导演版口播、分镜和素材请在 shots.json 和专用画面模板中修改。")
    return proj


def _running(state: dict) -> bool:
    pid = state.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _spawn(proj: vp.Project, *args: str):
    if _running(proj.state):
        raise HTTPException(409, "这个项目正在运行，等它结束后再操作")
    log = open(proj.path("pipeline.out"), "a", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "src.video.pipeline", *args], cwd=ROOT, stdout=log, stderr=log,
                         start_new_session=True)
    proj.update(pid=p.pid, status="Starting", error=None)


def _video_state(proj: vp.Project) -> dict:
    st = proj.state
    st["directed"] = proj.is_directed
    st["running"] = _running(st)
    if not st["running"] and st.get("status") in vp.STATUS.values():   # 进程没了但状态还停在某一步
        st["status"] = "Stopped"
    st["files"] = {name: proj.exists(*name.split("/")) for name in
                   ("render/final.mp4", "render/preview.mp4", "render/thumbnail.png", "audio/voice.wav", "qc_report.md")}
    return st


class NewVideo(BaseModel):
    event_id: int
    angle: str = ""


@app.get("/api/video-projects")
def video_projects():
    return {"projects": [_video_state(vp.Project(s["id"])) for s in vp.list_projects()]}


@app.post("/api/video-projects")
def create_video(body: NewVideo):
    """Create Video：建项目，然后在后台从头跑到 final.mp4。"""
    from ..video.pipeline import create_project
    existing = next((s for s in vp.list_projects() if s.get("event_id") == body.event_id), None)
    if existing:
        return {"id": existing["id"], "existing": True}
    try:
        proj = create_project(body.event_id, angle=body.angle)
    except SystemExit as e:
        raise HTTPException(400, str(e)) from e
    _spawn(proj, "run", proj.id)
    return {"id": proj.id, "existing": False}


@app.get("/api/video-projects/{project_id}")
def video_project(project_id: str):
    proj = _video(project_id)
    log_path = proj.dir / "pipeline.log"
    return {
        "state": _video_state(proj),
        "fact_pack": proj.read("fact_pack.json"), "script": proj.read("script.json"),
        "last30days": None if proj.is_directed else proj.read("research/last30days.json"),
        "storyboard": proj.read("storyboard.json"), "library": proj.read("assets/library.json", []),
        "scene_assets": proj.read("assets.json", []), "captions": proj.read("captions.json", []),
        "timings": {k: v for k, v in (proj.read("audio/timings.json") or {}).items() if k != "scenes"},
        "qc": proj.read("qc.json"),
        "log": log_path.read_text(encoding="utf-8")[-4000:] if log_path.exists() else "",
        "files_base": f"/video-files/{project_id}",
    }


class RunSteps(BaseModel):
    steps: list[str]


@app.post("/api/video-projects/{project_id}/community-leads")
def refresh_video_community_leads(project_id: str):
    from ..video.research import refresh_community_leads
    proj = _video(project_id)
    if proj.is_directed:
        raise HTTPException(409, "社区线索检索适用于普通视频项目。")
    if _running(proj.state):
        raise HTTPException(409, "项目正在制作，结束后可刷新社区线索。")
    with proj.path("research", ".last30days.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise HTTPException(409, "这个项目正在检索社区线索。") from e
        return {"last30days": refresh_community_leads(proj, SETTINGS)}


@app.post("/api/video-projects/{project_id}/run")
def video_run(project_id: str, body: RunSteps):
    """重新执行某几步：重新配音、重新渲染等。"""
    proj = _video(project_id)
    if not body.steps or any(s not in vp.STEPS for s in body.steps):
        raise HTTPException(400, f"steps 必须来自 {vp.STEPS}")
    if proj.is_directed and body.steps != ["qc"]:
        try:
            vp.directed_skip_voice(body.steps)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    _spawn(proj, "run", proj.id, "--steps", ",".join(body.steps))
    return {"ok": True}


class ScriptEdit(BaseModel):
    scenes: list[dict]


@app.put("/api/video-projects/{project_id}/script")
def video_edit_script(project_id: str, body: ScriptEdit):
    """人工修改口播。保存后需要重新配音、分镜和渲染才会进成片。"""
    from ..video.writer import save_script
    proj = _editable_video(project_id)
    script = proj.read("script.json")
    if not script:
        raise HTTPException(400, "还没有脚本")
    edits = {int(s["scene_id"]): str(s.get("voice", "")).strip() for s in body.scenes}
    changed = 0
    for sc in script["scenes"]:
        new = edits.get(sc["scene_id"])
        if new and new != sc["voice"]:
            sc["voice"], changed = new, changed + 1
    if changed:
        script.setdefault("revisions", []).append({"reason": "人工修改", "what_changed": f"改了 {changed} 场口播"})
        save_script(proj, script)
    return {"changed": changed, "script": proj.read("script.json")}


class RegenScene(BaseModel):
    instruction: str = ""


@app.post("/api/video-projects/{project_id}/scenes/{scene_id}/regenerate")
def video_regen_scene(project_id: str, scene_id: int, body: RegenScene):
    proj = _editable_video(project_id)
    _spawn(proj, "regen-scene", proj.id, str(scene_id), "--instruction", body.instruction)
    return {"ok": True}


class ReplaceAsset(BaseModel):
    scene_id: int
    shot_index: int
    asset_id: str


@app.post("/api/video-projects/{project_id}/replace-asset")
def video_replace_asset(project_id: str, body: ReplaceAsset):
    """把某个镜头的素材换成素材库里的另一个。之后重新渲染即可，不需要重新配音。"""
    proj = _editable_video(project_id)
    board = proj.read("storyboard.json")
    asset = next((a for a in proj.read("assets/library.json", []) if a["id"] == body.asset_id), None)
    scene = next((s for s in (board or {}).get("scenes", []) if s["scene_id"] == body.scene_id), None)
    if not asset or not scene or not 0 <= body.shot_index < len(scene["shots"]):
        raise HTTPException(400, "找不到这个镜头或素材")
    shot = scene["shots"][body.shot_index]
    shot.update(asset=asset, asset_id=asset["id"], highlight=None, highlight_text="", reason="人工替换素材")
    if shot["component"] not in ("HookScene", "ConclusionScene"):
        shot["component"] = {"official_ui": "PhoneOrDesktopScene", "web_screenshot": "BrowserScreenshotScene",
                             "article_screenshot": "BrowserScreenshotScene"}.get(asset["type"], "RealMediaScene")
    from ..video.storyboard import save_storyboard
    save_storyboard(proj, board)
    return {"ok": True, "storyboard": board}


@app.post("/api/video-projects/{project_id}/assets")
def video_upload_asset(project_id: str, file: UploadFile = File(...), mode: Literal["import", "scan"] = Form("import")):
    """从浏览器上传图片或 AutoClip MP4。上传任务在线程池中执行。"""
    from ..video.assets import image_size, safe_asset_name, update_library
    proj = _editable_video(project_id)
    filename = Path((file.filename or "upload.png").replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if mode == "scan" and suffix not in (".mp4", ".mov", ".mkv", ".webm"):
        raise HTTPException(400, "提取候选镜头支持 MP4、MOV、MKV 和 WebM 视频")
    if mode == "import" and suffix not in (".png", ".jpg", ".jpeg", ".webp", ".mp4"):
        raise HTTPException(400, "请选择 PNG、JPG、WebP 图片或 MP4 视频")
    with tempfile.TemporaryDirectory() as tmp:
        stem = re.sub(r"[^\w .()-]", "_", Path(filename).stem)[:55] or "upload"
        pending = Path(tmp) / (stem + suffix)
        with pending.open("wb") as dst:
            shutil.copyfileobj(file.file, dst)
        if mode == "scan" or suffix == ".mp4":
            from ..video.autoclip import import_clip, scan
            try:
                if mode == "scan":
                    result = scan(proj, pending, max_clips=6, clip_seconds=6, source_name=filename)
                    return {**result, "library": proj.read("assets/library.json", [])}
                asset = import_clip(proj, pending, title=Path(filename).stem, source_name=filename)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
            except (OSError, RuntimeError) as e:
                raise HTTPException(503, str(e)) from e
            return {"asset": asset, "library": proj.read("assets/library.json", [])}
        size = image_size(pending)
        if not size:
            raise HTTPException(400, "这个文件不是可读取的图片")
        out = proj.path("assets", f"user_{safe_asset_name(filename)}")
        shutil.move(pending, out)
    asset = {"id": f"user_{out.stem[5:]}", "type": "user_upload", "path": f"assets/{out.name}",
             "width": size[0], "height": size[1], "source": "人工上传", "url": "",
             "description": f"人工上传的图片：{filename}", "license_or_usage_note": "人工提供的素材，使用范围由上传者确认。"}
    library = update_library(proj, [asset])
    return {"library": library}


vp.PROJECTS_DIR.mkdir(exist_ok=True)
app.mount("/video-files", StaticFiles(directory=vp.PROJECTS_DIR), name="video-files")

# 前端构建产物。放在最后挂载，/api 路由优先。
DIST = ROOT / "dashboard" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="dashboard")
