"""Fast Filter（模型判断层）：只看标题 / 摘要 / 少量元数据，判断"是不是值得继续调查的信号"。

- 分批调用（每批 10~20 条），模型只打 5 个 0~5 的维度分，总分由代码按权重计算
- 单批失败自动重试一次，再失败则跳过该批（这些条目保持 new，下次运行会再评估）
- 不读取文章全文
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlsplit

from ..ai.base import AgentRunner, FatalRunnerError, RunnerError
from ..ai.schemas import FAST_FILTER_DIMENSIONS, FAST_FILTER_SCHEMA, REJECT_REASONS
from ..storage.database import Database, fmt_dt

log = logging.getLogger("trend_radar.fast_filter")

DEFAULT_WEIGHTS = {
    "change_signal": 5, "ordinary_people": 5, "story_potential": 4,
    "trend_potential": 4, "visual_potential": 2,
}


def prompt_version(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]


def compute_score(result: dict, weights: dict) -> float:
    return float(sum(result[d] * weights[d] for d in FAST_FILTER_DIMENSIONS))


def item_payload(row) -> dict:
    """给模型看的字段。source / engagement 只是弱信号，但仍然提供。"""
    meta = json.loads(row["metadata_json"] or "{}")
    d: dict = {"item_id": row["id"], "title": row["title"]}
    if row["summary"]:
        d["summary"] = row["summary"]
    d["source"] = row["source"]
    d["source_type"] = row["source_type"]
    if meta.get("category"):
        d["category"] = meta["category"]
    d["published_at"] = (row["published_at"] or "")[:16]
    if row["source_type"] == "hackernews":
        d["hn_points"] = meta.get("points")
        d["hn_comments"] = meta.get("comments")
        d["link_domain"] = urlsplit(row["canonical_url"] or "").netloc
    elif row["source_type"] == "github_trending":
        d["language"] = meta.get("language")
        d["stars_today"] = meta.get("stars_today")
        d["stars_total"] = meta.get("stars_total")
    elif meta.get("tags"):
        d["tags"] = meta["tags"][:6]
    return d


def validate_results(data: dict, batch_ids: set[int]) -> dict[int, dict]:
    """只保留合法的结果：id 属于本批、不重复、五个维度都是 0~5 的整数。"""
    valid: dict[int, dict] = {}
    for r in data.get("results", []):
        iid = r.get("item_id")
        if iid not in batch_ids or iid in valid:
            continue
        if not all(isinstance(r.get(d), int) and 0 <= r[d] <= 5 for d in FAST_FILTER_DIMENSIONS):
            continue
        if r.get("reject_reason") not in REJECT_REASONS:
            r["reject_reason"] = "none"
        valid[iid] = r
    return valid


def evaluate_batch(runner: AgentRunner, system: str, rows: list) -> tuple[dict[int, dict], str | None]:
    """返回 (合法结果, 错误信息)。失败自动重试一次；FatalRunnerError 直接向上抛。"""
    ids = {r["id"] for r in rows}
    payload = [item_payload(r) for r in rows]
    best: dict[int, dict] = {}
    error = None
    for attempt in (1, 2):
        try:
            valid = validate_results(
                runner.run(task="fast_filter", prompt=system, input_data=payload,
                           schema=FAST_FILTER_SCHEMA), ids)
        except RunnerError as e:
            error = str(e)
            log.warning("batch 失败（第 %d 次）：%s", attempt, e)
            continue
        if len(valid) > len(best):
            best = valid
        if len(best) == len(ids):
            return best, None
        error = f"返回结果不完整：{len(best)}/{len(ids)}"
        log.warning("batch %s（第 %d 次）", error, attempt)
    return best, error


def run_fast_filter(db: Database, runner: AgentRunner, system: str, cfg: dict,
                    cutoff: str, run_id: int, now: datetime, debug: bool = False) -> dict:
    rows = db.conn.execute(
        "SELECT * FROM raw_items WHERE status = 'new' AND published_at >= ? ORDER BY id", (cutoff,)
    ).fetchall()
    # 打散来源，避免一整批都是同一个 feed 导致相对打分失真
    random.Random(run_id).shuffle(rows)
    size = cfg.get("batch_size", 15)
    batches = [rows[i:i + size] for i in range(0, len(rows), size)]
    if debug:
        batches = batches[: cfg.get("debug_max_batches", 2)]

    weights = {**DEFAULT_WEIGHTS, **(cfg.get("weights") or {})}
    version = prompt_version(system)
    effort = getattr(runner, "reasoning_effort", None)
    stats = {"to_evaluate": len(rows), "batches": len(batches), "evaluated": 0,
             "failed_batches": 0, "skipped_items": 0, "errors": []}

    def save(batch, results: dict[int, dict], error: str | None):
        if error:
            missing = len(batch) - len(results)
            stats["skipped_items"] += missing
            if not results:
                stats["failed_batches"] += 1
            stats["errors"].append(f"batch 跳过 {missing} 条：{error}")
            log.error("batch 跳过 %d 条（保持 new，下次再评估）：%s", missing, error)
        for iid, r in results.items():
            score = compute_score(r, weights)
            payload = json.dumps({**r, "score": score, "run_id": run_id, "runner": runner.name,
                                  "model": runner.model, "reasoning_effort": effort,
                                  "prompt_version": version},
                                 ensure_ascii=False)
            db.conn.execute(
                "UPDATE raw_items SET status='filtered', filter_stage='llm', filter_score=?, "
                "filter_json=?, filter_reason=NULL, filtered_at=? WHERE id=?",
                (score, payload, fmt_dt(now), iid),
            )
            db.conn.execute(
                "INSERT INTO filter_evaluations (run_id, raw_item_id, model, prompt_version, "
                "change_signal, ordinary_people, story_potential, trend_potential, visual_potential, "
                "score, llm_keep, reject_reason, result_json, created_at, reasoning_effort) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, iid, runner.model, version, *(r[d] for d in FAST_FILTER_DIMENSIONS),
                 score, int(bool(r.get("keep"))), r["reject_reason"], payload, fmt_dt(now), effort),
            )
        stats["evaluated"] += len(results)
        db.conn.commit()

    if not batches:
        return stats
    # 第一批同步跑：登录 / 模型名 / 额度有问题时立刻失败，不会并发浪费调用
    save(batches[0], *evaluate_batch(runner, system, batches[0]))
    with ThreadPoolExecutor(max_workers=cfg.get("max_workers", 3)) as pool:
        futures = [pool.submit(evaluate_batch, runner, system, b) for b in batches[1:]]
        fatal = None
        for batch, fut in zip(batches[1:], futures):
            try:
                save(batch, *fut.result())
            except FatalRunnerError as e:
                fatal = e
        if fatal:
            raise fatal
    log.info("Fast Filter: evaluated %d/%d items in %d batches",
             stats["evaluated"], len(rows), len(batches))
    return stats


def select_candidates(db: Database, cfg: dict, cutoff: str) -> dict:
    """在分析窗口内所有已评估的条目里选出 signal（status = candidate）。

    Fast Filter 是 Signal Gate 而不是最终排名：score >= keep_threshold 的全部入选，交给聚类。
    max_signals_for_clustering 只是安全上限；少于 min_candidates 时逐分降低阈值，但不低于 min_threshold。
    """
    threshold = cfg.get("keep_threshold", 55)
    floor = cfg.get("min_threshold", 45)
    max_n = cfg.get("max_signals_for_clustering", 100)
    min_n = cfg.get("min_candidates", 20)

    # 过了窗口还没被聚类的旧 candidate 退出候选池
    db.conn.execute(
        "UPDATE raw_items SET status='filtered', filter_reason='old_information' "
        "WHERE status='candidate' AND published_at < ?", (cutoff,))

    rows = db.conn.execute(
        "SELECT id, filter_score, filter_json, human_override FROM raw_items "
        "WHERE filter_stage='llm' AND status IN ('filtered','candidate') AND published_at >= ? "
        "ORDER BY filter_score DESC, json_extract(filter_json,'$.change_signal') DESC, "
        "json_extract(filter_json,'$.ordinary_people') DESC, published_at DESC", (cutoff,)
    ).fetchall()

    while sum(r["filter_score"] >= threshold for r in rows) < min_n and threshold > floor:
        threshold -= 1
    # 人工恢复的条目始终是 candidate，且不占用 max_candidates 名额
    restored = {r["id"] for r in rows if r["human_override"] == "restored"}
    passing = [r for r in rows if r["filter_score"] >= threshold and r["id"] not in restored]
    chosen = {r["id"] for r in passing[:max_n]}

    for r in rows:
        if r["id"] in chosen:
            status, reason = "candidate", None
        elif r["id"] in restored:
            status, reason = "candidate", "human_restored"
        elif r["filter_score"] >= threshold:
            status, reason = "filtered", "over_max_candidates"
        else:
            llm_reason = json.loads(r["filter_json"]).get("reject_reason", "none")
            status, reason = "filtered", llm_reason if llm_reason != "none" else "below_threshold"
        db.conn.execute("UPDATE raw_items SET status=?, filter_reason=? WHERE id=?",
                        (status, reason, r["id"]))
        # 同步写到这条内容最近一次评估记录上，run 之间才能对比"谁入选了"
        db.conn.execute(
            "UPDATE filter_evaluations SET selected=?, final_reason=? WHERE id = "
            "(SELECT max(id) FROM filter_evaluations WHERE raw_item_id=?)",
            (int(status == "candidate"), reason, r["id"]))
    db.conn.commit()
    log.info("Candidates: %d (threshold %d, %d passed, cap %d)",
             len(chosen), threshold, len(passing), max_n)
    return {"threshold": threshold, "candidates": len(chosen), "passed_threshold": len(passing)}
