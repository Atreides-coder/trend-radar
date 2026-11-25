"""Filter 阶段编排：Prefilter → Fast Filter → 选 Candidate Pool → 写报告。"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from ..fetchers.base import utcnow
from ..ai.base import FatalRunnerError
from ..ai.codex_runner import CodexRunner
from ..output.filter_report import write_filter_report
from ..storage.database import Database, fmt_dt
from .fast_filter import prompt_version, run_fast_filter, select_candidates
from .prefilter import run_prefilter

log = logging.getLogger("trend_radar.filter")


def run_filter_stage(db: Database, root: Path, settings: dict, *, debug: bool = False,
                     dry_run: bool = False, force: bool = False) -> dict:
    started = time.monotonic()
    now = utcnow()
    cfg = settings.get("fast_filter", {})
    window_days = settings.get("filter", {}).get("window_days", settings.get("lookback_days", 7))
    cutoff = fmt_dt(now - timedelta(days=window_days))

    if force:
        # 改了 prompt / 规则后重跑：把窗口内还没进入聚类的条目全部打回 new
        n = db.conn.execute(
            "UPDATE raw_items SET status='new', filter_stage=NULL, filter_score=NULL, "
            "filter_reason=NULL, filter_json=NULL, filtered_at=NULL "
            "WHERE status IN ('new','discarded','filtered','candidate') AND published_at >= ?",
            (cutoff,)).rowcount
        db.conn.commit()
        log.info("--force: 重置了 %d 条，全部重新筛选", n)

    rules = yaml.safe_load((root / "config" / "prefilter.yaml").read_text(encoding="utf-8")) or {}
    removed = run_prefilter(db, rules, window_days, now)

    system = (root / "prompts" / "fast_filter.md").read_text(encoding="utf-8").strip()
    run = {"date": f"{datetime.now():%Y-%m-%d}", "window_days": window_days, "cfg": cfg,
           "status": "dry_run" if dry_run else "complete",
           "prompt_version": prompt_version(system), "prefilter_removed": dict(removed)}
    cur = db.conn.execute(
        "INSERT INTO filter_runs (started_at, prompt_version, prompt_text) VALUES (?,?,?)",
        (fmt_dt(now), run["prompt_version"], system))
    run["run_id"] = cur.lastrowid

    runner = None
    if dry_run:
        run["note"] = "DRY RUN：没有调用模型，只执行了 Prefilter。"
        log.info("--dry-run: 跳过 Fast Filter")
    else:
        try:
            runner = CodexRunner.from_env(settings.get("codex", {}))
            run.update(runner=f"{runner.name} ({runner.version})", model=runner.model,
                       reasoning_effort=runner.reasoning_effort)
            log.info("Runner: %s | %s", run["runner"], runner.login_status)
            log.info("Model: %s", runner.model)
            log.info("Reasoning effort: %s", runner.reasoning_effort)
            db.conn.execute("UPDATE filter_runs SET runner=?, model=?, reasoning_effort=? WHERE id=?",
                            (run["runner"], runner.model, runner.reasoning_effort, run["run_id"]))
            db.conn.commit()
            run["fast_filter"] = run_fast_filter(db, runner, system, cfg, cutoff,
                                                 run["run_id"], now, debug=debug)
            skipped = run["fast_filter"]["skipped_items"]
            if skipped:
                run["status"] = "failed"
                run["note"] = f"Fast Filter 有 {skipped} 条评估失败，重跑筛选可继续处理。"
                log.error(run["note"])
        except FatalRunnerError as e:
            run["status"] = "failed"
            run["note"] = f"Fast Filter 中止：{e}"
            log.error("Fast Filter 中止：%s", e)

    run["selection"] = select_candidates(db, cfg, cutoff)

    if runner:
        run["usage"] = runner.usage.as_dict()
    run["duration_seconds"] = time.monotonic() - started

    db.conn.execute(
        "UPDATE filter_runs SET duration_seconds=?, model=?, stats_json=? WHERE id=?",
        (run["duration_seconds"], run.get("model"),
         json.dumps({k: v for k, v in run.items() if k != "cfg"}, ensure_ascii=False), run["run_id"]))
    db.conn.commit()

    path = write_filter_report(db, root / "output" / run["date"], cutoff, run)
    # 每次运行另存一份，重跑不会覆盖旧报告
    path.with_name(f"filter_report_run{run['run_id']}.md").write_text(
        path.read_text(encoding="utf-8"), encoding="utf-8")
    run["report_path"] = str(path)

    c = lambda sql: db.conn.execute(sql, (cutoff,)).fetchone()[0]  # noqa: E731
    u = run.get("usage", {})
    log.info("Raw items: %d", c("SELECT count(*) FROM raw_items WHERE published_at >= ?"))
    log.info("Prefilter removed: %d",
             c("SELECT count(*) FROM raw_items WHERE filter_stage='prefilter' AND published_at >= ?"))
    log.info("Model evaluated: %d",
             c("SELECT count(*) FROM raw_items WHERE filter_stage='llm' AND published_at >= ?"))
    log.info("Candidates: %d", run["selection"]["candidates"])
    log.info("Model: %s | Reasoning effort: %s", run.get("model", "-"), run.get("reasoning_effort", "-"))
    log.info("Codex calls: %d (failed %d) | input tokens: %d (cached %d) | output tokens: %d | %.1fs",
             u.get("calls", 0), u.get("failed_calls", 0), u.get("input_tokens", 0),
             u.get("cached_input_tokens", 0), u.get("output_tokens", 0), run["duration_seconds"])
    log.info("Report: %s", path)
    return run
