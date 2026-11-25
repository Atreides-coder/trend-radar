"""Phase 2 的人工检查报告：output/YYYY-MM-DD/filter_report.md + raw_candidates.json"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from ..ai.schemas import FAST_FILTER_DIMENSIONS
from ..storage.database import Database

_DIM_LABEL = dict(zip(FAST_FILTER_DIMENSIONS, "CPSTV"))


def _cell(text: str | None, limit: int = 90) -> str:
    text = (text or "").replace("|", "/").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dims(j: dict) -> str:
    return " ".join(f"{_DIM_LABEL[d]}{j[d]}" for d in FAST_FILTER_DIMENSIONS)


def _title(row) -> str:
    title = _cell(row["title"], 80)
    return f"[{title}]({row['url']})" if row["url"] else title


def _signal(row) -> str:
    meta = json.loads(row["metadata_json"] or "{}")
    if row["source_type"] == "hackernews":
        return f"{row['source']} · {meta.get('points', 0)}分"
    if row["source_type"] == "github_trending":
        return f"{row['source']} · +{meta.get('stars_today', 0)}★"
    return row["source"]


def _llm_table(rows, with_change: bool = True) -> list[str]:
    head = "| Score | 维度 | Title | Source | Possible Change | Reason |" if with_change \
        else "| Score | 维度 | Title | Source | 拒绝原因 | Reason |"
    lines = [head, "|---|---|---|---|---|---|"]
    for r in rows:
        j = json.loads(r["filter_json"])
        mark = ""
        if r["status"] == "candidate" and not j.get("keep"):
            mark = " ⚠️模型说不留"
        elif r["status"] != "candidate" and j.get("keep"):
            mark = " ⚠️模型说留"
        mid = _cell(j.get("possible_change"), 60) if with_change else (r["filter_reason"] or "")
        lines.append(
            f"| {r['filter_score']:.0f}{' ✅' if r['status'] == 'candidate' else ''}{mark} "
            f"| {_dims(j)} | {_title(r)} | {_signal(r)} | {mid} | {_cell(j.get('reason'), 70)} |"
        )
    return lines


def write_filter_report(db: Database, out_dir: Path, cutoff: str, run: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    q = lambda sql, *a: db.conn.execute(sql, a).fetchall()  # noqa: E731

    total = q("SELECT count(*) c FROM raw_items WHERE published_at >= ?", cutoff)[0]["c"]
    pre = q("SELECT * FROM raw_items WHERE filter_stage='prefilter' AND published_at >= ? "
            "ORDER BY filter_reason, source, id", cutoff)
    llm = q("SELECT * FROM raw_items WHERE filter_stage='llm' AND published_at >= ? "
            "ORDER BY filter_score DESC, id", cutoff)
    pending = q("SELECT count(*) c FROM raw_items WHERE status='new' AND published_at >= ?",
                cutoff)[0]["c"]
    cands = [r for r in llm if r["status"] == "candidate"]
    rejected = [r for r in llm if r["status"] != "candidate"]
    sel = run.get("selection") or {}
    ff = run.get("fast_filter") or {}
    usage = run.get("usage") or {}

    L = [f"# Fast Filter Report — {run['date']}", ""]
    if run.get("note"):
        L += [f"> {run['note']}", ""]

    L += ["## Input", "", "```text",
          f"Raw items (过去 {run['window_days']} 天): {total}",
          f"Prefilter removed: {len(pre)}",
          f"Model evaluated: {len(llm)}",
          f"Candidates: {len(cands)}",
          "```", ""]
    if pending:
        L += [f"⚠️ 还有 {pending} 条通过了 Prefilter 但没有被模型评估（批次失败、dry-run 或 debug 限制）。", ""]

    L += ["## Run", "", "```text",
          f"Runner: {run.get('runner') or '-'}",
          f"Model: {run.get('model') or '-'} (reasoning effort: {run.get('reasoning_effort') or '-'})",
          f"Prompt version: {run.get('prompt_version') or '-'}",
          f"本次新评估: {ff.get('evaluated', 0)} 条 / {ff.get('batches', 0)} 批",
          f"Codex calls: {usage.get('calls', 0)} (失败 {usage.get('failed_calls', 0)})",
          *([f"Input tokens: {usage.get('input_tokens', 0)} (其中缓存命中 {usage.get('cached_input_tokens', 0)})",
             f"Output tokens: {usage.get('output_tokens', 0)} (其中推理 {usage.get('reasoning_output_tokens', 0)})"]
            if usage.get("usage_reported") else ["Tokens: Codex 本次没有报告用量"]),
          f"Tool / command events: {usage.get('tool_events', 0)} (应为 0)",
          f"Duration: {run.get('duration_seconds', 0):.1f}s",
          f"Keep threshold: {sel.get('threshold', '-')}"
          f" (配置 {run['cfg'].get('keep_threshold')}, 过线 {sel.get('passed_threshold', '-')} 条,"
          f" 安全上限 {run['cfg'].get('max_signals_for_clustering')})",
          "```", ""]
    if ff.get("errors"):
        L += ["**Errors**", ""] + [f"- {e}" for e in ff["errors"]] + [""]

    if llm:
        buckets = Counter(min(int(r["filter_score"]) // 10 * 10, 90) for r in llm)
        L += ["## Score Distribution", "", "```text"]
        for b in range(90, -1, -10):
            L.append(f"{b:>3}-{b + 9 if b < 90 else 100:<3} {'█' * buckets.get(b, 0)} {buckets.get(b, 0)}")
        L += ["```", "",
              "维度缩写：C 变化信号 ×5 · P 普通人关联 ×5 · S 故事潜力 ×4 · T 趋势潜力 ×4 · V 视觉潜力 ×2（每项 0–5）", ""]

    L += ["## Top Candidates", ""]
    L += _llm_table(cands[:20]) if cands else ["（无）"]
    if len(cands) > 20:
        L += ["", f"其余 {len(cands) - 20} 个 candidate：", ""] + _llm_table(cands[20:])
    L.append("")

    lo, hi = run["cfg"].get("min_threshold", 45), run["cfg"].get("keep_threshold", 55) + 5
    border = [r for r in llm if lo <= r["filter_score"] <= hi]
    L += [f"## Borderline（{lo}～{hi} 分）", "",
          "最需要人工检查的区域。✅ 表示进入了 Candidate Pool；⚠️ 表示模型自己的 keep 判断和分数结论不一致。", ""]
    L += _llm_table(border) if border else ["（无）"]
    L.append("")

    sample = random.Random(run.get("run_id", 0)).sample(rejected, min(20, len(rejected)))
    sample.sort(key=lambda r: -r["filter_score"])
    L += ["## Rejected Examples", "", f"从 {len(rejected)} 条被模型拒绝的内容里随机抽 {len(sample)} 条。", ""]
    L += _llm_table(sample, with_change=False) if sample else ["（无）"]
    L.append("")

    L += ["## Prefilter Removed", "",
          f"规则直接过滤的 {len(pre)} 条（未消耗模型额度）。全部列出，方便检查规则有没有误杀。", ""]
    by_reason: dict[str, list] = {}
    for r in pre:
        by_reason.setdefault(r["filter_reason"], []).append(r)
    for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        L += [f"**{reason}**（{len(items)}）", ""]
        L += [f"- {_title(r)} — {r['source']}" for r in items] + [""]

    path = out_dir / "filter_report.md"
    path.write_text("\n".join(L), encoding="utf-8")

    (out_dir / "raw_candidates.json").write_text(json.dumps([
        {"id": r["id"], "score": r["filter_score"], "title": r["title"], "source": r["source"],
         "url": r["url"], "published_at": r["published_at"], "summary": r["summary"],
         "filter": json.loads(r["filter_json"])}
        for r in cands], ensure_ascii=False, indent=2), encoding="utf-8")
    return path
