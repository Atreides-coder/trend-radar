import { useEffect, useState } from "react";
import { api } from "./api.js";
import {
  Dims, Histogram, ItemCard, Loader, ModelTag, PageHeader, Score, Stat, StatusBadge, useData,
} from "./components.jsx";
import { ClusterRunsTable } from "./events.jsx";
import {
  HUMAN, STATUS, effortName, fmtDate, fmtDay, fmtDuration, fmtNum, modelName, reasonLabel, runLabel,
} from "./format.js";

// ------------------------------------------------------------------ Overview

export function Overview({ version }) {
  const state = useData(() => api.overview(), [version]);
  return (
    <Loader state={state}>
      {(d) => {
        const run = d.last_run;
        const f = d.funnel;
        const u = run?.usage || {};
        const cfgDiffers = run && (run.model !== d.config.model || run.reasoning_effort !== d.config.reasoning_effort);
        return (
          <>
            <PageHeader title="Overview" subtitle={`过去 ${d.config.window_days} 天的内容 · 最近一次分析 ${run ? fmtDate(run.started_at) : "—"}`} />

            <section className="hero">
              <div className="hero-model">
                <div className="stat-label">最近一次分析使用的模型</div>
                <div className="hero-name">{modelName(run?.model)}</div>
                <div className="hero-effort">Reasoning effort · <b>{effortName(run?.reasoning_effort)}</b></div>
                <div className="stat-hint">
                  {run ? <>Run #{run.id} · prompt <code>{run.prompt_version}</code> · {run.runner}</> : "还没有运行过分析"}
                </div>
              </div>
              <div className="funnel">
                <Stat label="Raw" value={f.raw} hint={`${d.sources_with_items} 个来源`} />
                <Stat label="Prefilter" value={f.after_prefilter} hint={`规则过滤 ${f.prefilter_removed}`} />
                <Stat label="Signals" value={f.signals} hint={`≥ ${run?.selection?.threshold ?? "—"} 分${d.restored ? ` · 含人工恢复 ${d.restored}` : ""}`} />
                <Stat label="Events" value={f.events ?? "—"} hint={f.events != null ? "聚类后的独立事件" : "还没有聚类"} />
                <Stat label="Trends" value={f.trends ?? "—"} hint="跟踪中的趋势假设" />
                <Stat label="Research Queue" value={f.research_queue ?? "—"} accent hint="Global Ranking 前列" />
              </div>
            </section>

            {cfgDiffers && (
              <div className="notice warn">
                当前 .env 配置是 <b>{modelName(d.config.model)} · {effortName(d.config.reasoning_effort)}</b>，
                与最近一次运行使用的模型不同。下次运行会使用当前配置。
              </div>
            )}
            {f.pending > 0 && <div className="notice warn">还有 {f.pending} 条通过了 Prefilter 但没有被模型评估。</div>}
            {run?.note && <div className="notice warn">{run.note}</div>}

            {d.last_cluster_run?.note && <div className="notice warn">{d.last_cluster_run.note}</div>}

            <section className="grid stats three">
              <Stat label="最近一次聚类" value={d.last_cluster_run ? fmtDate(d.last_cluster_run.started_at) : "—"}
                hint={d.last_cluster_run ? `${modelName(d.last_cluster_run.model)} · ${effortName(d.last_cluster_run.reasoning_effort)} · ${fmtDuration(d.last_cluster_run.duration_seconds)}` : "还没有运行聚类"} />
              <Stat label="聚类 Codex 调用" value={fmtNum(d.last_cluster_run?.usage.calls)} hint={d.last_cluster_run ? `失败 ${d.last_cluster_run.usage.failed_calls || 0}` : ""} />
              <Stat label="聚类 Token Usage"
                value={d.last_cluster_run?.usage.usage_reported ? fmtNum((d.last_cluster_run.usage.input_tokens || 0) + (d.last_cluster_run.usage.output_tokens || 0)) : "—"}
                hint={d.last_cluster_run?.usage.usage_reported ? `输入 ${fmtNum(d.last_cluster_run.usage.input_tokens)} · 输出 ${fmtNum(d.last_cluster_run.usage.output_tokens)}` : ""} />
              <Stat label="数据源" value={d.sources_configured} hint={`${d.sources_with_items} 个在窗口内有内容`} />
              <Stat label="最近一次抓取" value={d.last_fetch ? fmtDate(d.last_fetch.run_at) : "—"}
                hint={d.last_fetch ? `${d.last_fetch.fetched} 条${d.last_fetch.failed ? ` · 失败：${d.last_fetch.failed}` : " · 全部成功"}` : ""} />
              <Stat label="最近一次 Fast Filter" value={run ? fmtDate(run.started_at) : "—"} hint={run ? `评估 ${run.fast_filter.evaluated ?? 0} 条 · ${fmtDuration(run.duration_seconds)}` : ""} />
              <Stat label="Fast Filter Codex 调用" value={fmtNum(u.calls)} hint={u.failed_calls ? `失败 ${u.failed_calls}` : "失败 0"} />
              <Stat label="Fast Filter Token Usage"
                value={u.usage_reported ? fmtNum((u.input_tokens || 0) + (u.output_tokens || 0)) : "—"}
                hint={u.usage_reported ? `输入 ${fmtNum(u.input_tokens)} · 输出 ${fmtNum(u.output_tokens)}（推理 ${fmtNum(u.reasoning_output_tokens)}）` : "Codex 没有报告用量"} />
            </section>

            <section className="grid two">
              <div className="panel">
                <h2>分数分布</h2>
                <p className="muted">模型评估过的 {f.evaluated} 条内容，按 Fast Filter 总分分桶。</p>
                <Histogram series={[{ name: "条数", tone: 1, data: d.distribution }]} />
              </div>
              <div className="panel">
                <h2>人工反馈</h2>
                <div className="fb-summary">
                  {HUMAN.map((h) => (
                    <div key={h.key}><span className="fb-icon">{h.icon}</span><b>{d.feedback[h.key] || 0}</b><span>{h.label}</span></div>
                  ))}
                </div>
                <p className="muted">
                  模型的 keep 判断与分数结论不一致：{d.mismatch} 条（见 <a href="#/borderline">Borderline</a>）。
                </p>
              </div>
            </section>

            <section className="panel">
              <h2>各来源</h2>
              <table className="table">
                <thead><tr><th>来源</th><th className="num">Raw</th><th className="num">模型评估</th><th className="num">Candidates</th></tr></thead>
                <tbody>
                  {d.per_source.map((s) => (
                    <tr key={s.source}><td>{s.source}</td><td className="num">{s.raw}</td><td className="num">{s.evaluated}</td><td className="num">{s.candidates || ""}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        );
      }}
    </Loader>
  );
}

// ------------------------------------------------------------------ item lists

const VIEWS = {
  raw: { title: "Raw Intelligence", subtitle: "系统在分析窗口内看到的全部原始内容。", filters: ["source", "status", "date"] },
  candidates: { title: "Candidates", subtitle: "通过 Fast Filter 的全部 signal，会全部交给聚类。点开看详情，并标记你的判断。", filters: ["source", "human"], sorts: true },
  rejected: { title: "Rejected", subtitle: "模型评估后没有入选的内容。用来发现误杀，可以人工恢复。", filters: ["source", "reason", "prefilter"], sorts: true },
  borderline: { title: "Borderline", subtitle: "45～65 分，以及模型的 keep 判断与分数结论不一致的内容。调 prompt 时最值得看。", filters: ["source", "status"], sorts: true },
};

function Select({ value, onChange, placeholder, options }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={placeholder}>
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>)}
    </select>
  );
}

export function ItemsPage({ view, meta, version, openItem }) {
  const cfg = VIEWS[view];
  const [filters, setFilters] = useState({});
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const [info, setInfo] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => { setFilters({}); setQ(""); setItems(null); }, [view]);

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      api.items({ view, q, ...filters })
        .then((d) => { if (alive) { setItems(d.items); setInfo(d); setError(null); } })
        .catch((e) => alive && setError(e.message));
    }, q ? 200 : 0);
    return () => { alive = false; clearTimeout(t); };
  }, [view, q, filters, version]);

  const set = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }));
  const patch = (next) => setItems((list) => list.map((i) => (i.id === next.id ? { ...i, ...next } : i)));
  const days = [...new Set((items || []).map((i) => (i.published_at || "").slice(0, 10)))].filter(Boolean).sort().reverse();

  return (
    <>
      <PageHeader title={cfg.title} subtitle={cfg.subtitle}>
        <span className="count">{items ? `${info.total} / ${info.total_in_view} 条` : ""}</span>
      </PageHeader>

      <div className="filters">
        <input type="search" placeholder="搜索标题 / 摘要" value={q} onChange={(e) => setQ(e.target.value)} />
        {cfg.filters.includes("source") && <Select value={filters.source || ""} onChange={set("source")} placeholder="全部来源" options={meta.sources} />}
        {cfg.filters.includes("status") && (
          <Select value={filters.status || ""} onChange={set("status")} placeholder="全部状态"
            options={meta.statuses.map((s) => ({ value: s, label: STATUS[s] || s }))} />
        )}
        {cfg.filters.includes("reason") && (
          <Select value={filters.reason || ""} onChange={set("reason")} placeholder="全部拒绝原因"
            options={meta.reasons.filter((r) => r !== "human_restored").map((r) => ({ value: r, label: reasonLabel(r) }))} />
        )}
        {cfg.filters.includes("human") && (
          <Select value={filters.human || ""} onChange={set("human")} placeholder="全部人工标记"
            options={[{ value: "none", label: "还没标记" }, ...HUMAN.map((h) => ({ value: h.key, label: `${h.icon} ${h.label}` }))]} />
        )}
        {cfg.filters.includes("date") && (
          <Select value={filters.date || ""} onChange={set("date")} placeholder="全部日期（UTC）" options={filters.date ? [filters.date, ...days.filter((d) => d !== filters.date)] : days} />
        )}
        {cfg.sorts && (
          <Select value={filters.sort || ""} onChange={set("sort")} placeholder="分数从高到低"
            options={[{ value: "score_asc", label: "分数从低到高" }, { value: "date_desc", label: "最新发布" }, { value: "source", label: "按来源" }]} />
        )}
        {cfg.filters.includes("prefilter") && (
          <label className="check">
            <input type="checkbox" checked={!!filters.include_prefilter} onChange={(e) => set("include_prefilter")(e.target.checked ? "true" : "")} />
            包含规则过滤的内容
          </label>
        )}
      </div>

      {error && <div className="notice error">加载失败：{error}</div>}
      {!items && !error && <div className="empty">加载中…</div>}
      {items && items.length === 0 && <div className="empty">没有符合条件的内容。</div>}

      {items && view === "raw" && items.length > 0 && (
        <div className="panel flush">
          <table className="table clickable">
            <thead><tr><th>状态</th><th>标题</th><th>来源</th><th>发布时间</th><th className="num">分数</th><th>原文</th></tr></thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id} onClick={() => openItem(i.id)}>
                  <td><StatusBadge item={i} /></td>
                  <td className="title-cell">{i.title}{i.engagement && <span className="muted"> · {i.engagement.label}</span>}</td>
                  <td>{i.source}</td>
                  <td className="nowrap">{fmtDate(i.published_at)}</td>
                  <td className="num">{i.score != null ? Math.round(i.score) : ""}</td>
                  <td><a href={i.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>打开 ↗</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {items && view !== "raw" && (
        <div className="cards">
          {items.map((i) => <ItemCard key={i.id} item={i} onOpen={openItem} onChange={patch} showRestore={i.status !== "candidate"} />)}
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ Runs

export function RunsPage() {
  const state = useData(() => api.runs(), []);
  const [picked, setPicked] = useState([]);
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)));
  return (
    <Loader state={state}>
      {({ runs }) => {
        const pair = picked.length === 2 ? [...picked].sort((a, b) => a - b) : runs.length >= 2 ? [runs[1].id, runs[0].id] : null;
        return (
          <>
            <PageHeader title="Runs" subtitle="每次 Fast Filter 和聚类运行。勾选两个 Fast Filter 运行可以对比；不勾选时默认对比最近两次。">
              {pair && <a className="btn primary" href={`#/runs/compare?a=${pair[0]}&b=${pair[1]}`}>对比 Run {pair[0]} 与 Run {pair[1]}</a>}
            </PageHeader>
            <ClusterRunsTable />
            <h2>Phase 2 · Fast Filter Runs</h2>
            {runs.length === 0 && <div className="empty">还没有运行记录。</div>}
            <div className="panel flush">
              <table className="table clickable">
                <thead>
                  <tr><th></th><th>Run</th><th>时间</th><th>Model</th><th>Effort</th><th>Prompt</th><th className="num">Input</th>
                    <th className="num">Candidates</th><th className="num">Codex calls</th><th className="num">Tokens</th><th className="num">Duration</th></tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} onClick={() => { window.location.hash = `#/runs/${r.id}`; }}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={picked.includes(r.id)} onChange={() => toggle(r.id)} aria-label={`选择 Run ${r.id} 用于对比`} />
                      </td>
                      <td>#{r.id}</td>
                      <td className="nowrap">{fmtDate(r.started_at)}</td>
                      <td><b>{modelName(r.model)}</b></td>
                      <td>{effortName(r.reasoning_effort)}</td>
                      <td><code>{r.prompt_version}</code></td>
                      <td className="num">{r.evaluated}</td>
                      <td className="num">{r.candidates}</td>
                      <td className="num">{fmtNum(r.usage.calls)}</td>
                      <td className="num">{r.usage.usage_reported ? fmtNum((r.usage.input_tokens || 0) + (r.usage.output_tokens || 0)) : "—"}</td>
                      <td className="num">{fmtDuration(r.duration_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        );
      }}
    </Loader>
  );
}

function EvalTable({ rows, openItem }) {
  return (
    <table className="table clickable">
      <thead><tr><th className="num">分数</th><th>标题</th><th>来源</th><th>维度</th><th>可能的变化</th></tr></thead>
      <tbody>
        {rows.map((e) => (
          <tr key={e.item_id} onClick={() => openItem(e.item_id)}>
            <td className="num"><Score value={e.score} selected={e.selected} /></td>
            <td className="title-cell">{e.title}</td>
            <td>{e.source}</td>
            <td><Dims dims={e.dims} compact /></td>
            <td className="muted">{e.possible_change || e.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RunDetail({ id, openItem }) {
  const state = useData(() => api.run(id), [id]);
  return (
    <Loader state={state}>
      {(r) => {
        const u = r.usage, s = r.summary;
        const top = r.evaluations.filter((e) => e.selected);
        return (
          <>
            <PageHeader title={`Run #${r.id}`} subtitle={fmtDate(r.started_at)}>
              <ModelTag model={r.model} effort={r.reasoning_effort} />
              <a className="btn" href="#/runs">← 全部 Runs</a>
            </PageHeader>
            <section className="grid stats four">
              <Stat label="Model" value={modelName(r.model)} hint={`Reasoning effort · ${effortName(r.reasoning_effort)}`} />
              <Stat label="Prompt version" value={<code>{r.prompt_version}</code>} hint={r.runner} />
              <Stat label="Input" value={s.evaluated} hint="模型评估的条数" />
              <Stat label="Candidates" value={s.candidates} accent hint={`入选线 ${s.min_candidate_score ?? "—"} 分 · 阈值 ${r.selection.threshold ?? "—"}`} />
              <Stat label="Codex calls" value={fmtNum(u.calls)} hint={`失败 ${u.failed_calls || 0} · 工具调用 ${u.tool_events || 0}`} />
              <Stat label="Tokens" value={u.usage_reported ? fmtNum((u.input_tokens || 0) + (u.output_tokens || 0)) : "—"}
                hint={u.usage_reported ? `输入 ${fmtNum(u.input_tokens)} · 输出 ${fmtNum(u.output_tokens)}` : "没有报告用量"} />
              <Stat label="Duration" value={fmtDuration(r.duration_seconds)} />
              <Stat label="Borderline" value={s.borderline} hint={`keep 不一致 ${s.mismatch} · 五维同分 ${s.flat_scores}`} />
            </section>

            <section className="panel">
              <h2>Errors</h2>
              {r.note && <div className="notice warn">{r.note}</div>}
              {(r.fast_filter.errors || []).length === 0 && !r.note
                ? <p className="muted">这次运行没有错误。</p>
                : <ul>{(r.fast_filter.errors || []).map((e, i) => <li key={i}>{e}</li>)}</ul>}
            </section>

            <section className="panel">
              <h2>Score Distribution</h2>
              <Histogram series={[{ name: "条数", tone: 1, data: s.distribution }]} />
            </section>

            <section className="panel flush">
              <h2 className="pad">Top Candidates（{top.length}）</h2>
              <EvalTable rows={top} openItem={openItem} />
            </section>

            {r.prompt_text && (
              <details className="panel">
                <summary>这次运行使用的 Prompt（{r.prompt_version}）</summary>
                <pre className="prompt">{r.prompt_text}</pre>
              </details>
            )}
          </>
        );
      }}
    </Loader>
  );
}

const SHOW = {
  all: { label: "全部", test: () => true },
  only_b: { label: "仅 B 入选", test: (r) => r.b.selected && !r.a.selected },
  only_a: { label: "仅 A 入选", test: (r) => r.a.selected && !r.b.selected },
  both: { label: "两者都入选", test: (r) => r.a.selected && r.b.selected },
};

export function ComparePage({ a, b, openItem }) {
  const runs = useData(() => api.runs(), []);
  const state = useData(() => api.compare(a, b), [a, b]);
  const [show, setShow] = useState("all");
  const go = (na, nb) => { window.location.hash = `#/runs/compare?a=${na}&b=${nb}`; };
  return (
    <Loader state={state}>
      {(d) => {
        const A = d.a, B = d.b;
        const rows = d.items.filter(SHOW[show].test);
        const line = (label, va, vb, hint) => (
          <tr><td>{label}{hint && <span className="muted"> · {hint}</span>}</td><td className="num">{va}</td><td className="num">{vb}</td></tr>
        );
        return (
          <>
            <PageHeader title="Run 对比" subtitle={`两次运行都评估过的 ${d.common} 条内容。`}>
              <a className="btn" href="#/runs">← 全部 Runs</a>
            </PageHeader>

            <div className="filters">
              {runs.data && ["A", "B"].map((side) => (
                <label key={side} className="pick">
                  <i className={`swatch tone-${side === "A" ? 1 : 2}`} />{side}
                  <select value={side === "A" ? a : b} onChange={(e) => (side === "A" ? go(e.target.value, b) : go(a, e.target.value))}>
                    {runs.data.runs.map((r) => <option key={r.id} value={r.id}>{runLabel(r)}（{r.prompt_version}）</option>)}
                  </select>
                </label>
              ))}
            </div>

            {A.prompt_version !== B.prompt_version && (
              <div className="notice warn">
                两次运行的 prompt 版本不同（<code>{A.prompt_version}</code> → <code>{B.prompt_version}</code>）。差异同时来自模型和 prompt，不能单独归因于模型。
              </div>
            )}

            <section className="grid stats four">
              <Stat label="Top 20 重合" value={`${d.top20_overlap} / 20`} hint={`${20 - d.top20_overlap} 条不同`} />
              <Stat label="两者都入选" value={d.candidates_both} hint={`仅 A ${d.candidates_only_a} · 仅 B ${d.candidates_only_b}`} />
              <Stat label="平均分数变化" value={`±${d.mean_abs_delta}`} hint="同一条内容两次得分之差的平均绝对值" />
              <Stat label="Borderline（45–65）" value={`${A.summary.borderline} → ${B.summary.borderline}`} hint="A → B" />
            </section>

            <section className="grid two">
              <div className="panel">
                <h2>分数分布</h2>
                <Histogram series={[
                  { name: `A · ${modelName(A.model)} ${effortName(A.reasoning_effort)}`, tone: 1, data: A.summary.distribution },
                  { name: `B · ${modelName(B.model)} ${effortName(B.reasoning_effort)}`, tone: 2, data: B.summary.distribution },
                ]} />
              </div>
              <div className="panel">
                <h2>指标对比</h2>
                <table className="table tight">
                  <thead><tr><th></th><th className="num">A · #{A.id}</th><th className="num">B · #{B.id}</th></tr></thead>
                  <tbody>
                    {line("Model", `${modelName(A.model)} ${effortName(A.reasoning_effort)}`, `${modelName(B.model)} ${effortName(B.reasoning_effort)}`)}
                    {line("Prompt", <code>{A.prompt_version}</code>, <code>{B.prompt_version}</code>)}
                    {line("Candidates", A.summary.candidates, B.summary.candidates)}
                    {line("入选线", A.summary.min_candidate_score ?? "—", B.summary.min_candidate_score ?? "—", "最低入选分")}
                    {line("过阈值", A.selection.passed_threshold ?? "—", B.selection.passed_threshold ?? "—", "分数过线的条数")}
                    {line("模型说留", A.summary.llm_keep, B.summary.llm_keep)}
                    {line("keep 与结果不一致", A.summary.mismatch, B.summary.mismatch)}
                    {line("五维同分", A.summary.flat_scores, B.summary.flat_scores, "区分度差的迹象")}
                    {line("平均分", A.summary.mean_score, B.summary.mean_score)}
                    {line("Tokens", fmtNum((A.usage.input_tokens || 0) + (A.usage.output_tokens || 0)), fmtNum((B.usage.input_tokens || 0) + (B.usage.output_tokens || 0)))}
                    {line("Duration", fmtDuration(A.duration_seconds), fmtDuration(B.duration_seconds))}
                  </tbody>
                </table>
              </div>
            </section>

            {d.same_story.length > 0 && (
              <section className="panel">
                <h2>同一件事的评分稳定性</h2>
                <p className="muted">不同来源指向同一个链接的内容。同一次运行里分差越小，说明评分越稳定。</p>
                <table className="table tight">
                  <thead><tr><th>内容</th><th>来源</th><th className="num">A 的得分</th><th className="num">A 分差</th><th className="num">B 的得分</th><th className="num">B 分差</th></tr></thead>
                  <tbody>
                    {d.same_story.map((s) => (
                      <tr key={s.title}><td>{s.title}</td><td>{s.sources.join(" / ")}</td>
                        <td className="num">{s.a_scores.join(" / ")}</td><td className="num">{s.a_spread}</td>
                        <td className="num">{s.b_scores.join(" / ")}</td><td className="num">{s.b_spread}</td></tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            <section className="panel flush">
              <div className="pad row between">
                <h2>逐条对比（按分数变化排序）</h2>
                <div className="segmented" role="group" aria-label="筛选">
                  {Object.entries(SHOW).map(([key, v]) => (
                    <button key={key} type="button" className={show === key ? "active" : ""} onClick={() => setShow(key)}>
                      {v.label} {key !== "all" && d.items.filter(v.test).length}
                    </button>
                  ))}
                </div>
              </div>
              <table className="table clickable compare-table">
                <thead><tr><th>标题</th><th>来源</th><th className="num">A</th><th>A 维度</th><th className="num">B</th><th>B 维度</th><th className="num">变化</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.item_id} onClick={() => openItem(r.item_id)}>
                      <td className="title-cell">{r.title}</td>
                      <td>{r.source}</td>
                      <td className="num"><Score value={r.a.score} selected={r.a.selected} /></td>
                      <td><Dims dims={r.a.dims} compact /></td>
                      <td className="num"><Score value={r.b.score} selected={r.b.selected} /></td>
                      <td><Dims dims={r.b.dims} compact /></td>
                      <td className="num delta">{r.delta > 0 ? `▲ +${r.delta}` : r.delta < 0 ? `▼ ${r.delta}` : "0"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        );
      }}
    </Loader>
  );
}

// ------------------------------------------------------------------ Watchlist / Coming soon

export function WatchlistPage({ version, openItem }) {
  const state = useData(() => api.watchlist(), [version]);
  const [local, setLocal] = useState({});
  return (
    <Loader state={state}>
      {(d) => {
        const items = d.items.map((i) => ({ ...i, ...(local[i.id] || {}) }));
        return (
          <>
            <PageHeader title="Watchlist" subtitle="你标记为 Watch / Interested / Strong Topic 的内容。系统跟踪的趋势在 Trends 页面。" />
            <section>
              <h2>你标记的内容（{items.length}）</h2>
              {items.length === 0 && <div className="empty">还没有标记。在 Candidates 页面点 👁 Watch 或 ★ Strong Topic。</div>}
              <div className="cards">
                {items.map((i) => <ItemCard key={i.id} item={i} onOpen={openItem} onChange={(n) => setLocal((l) => ({ ...l, [n.id]: n }))} />)}
              </div>
            </section>
          </>
        );
      }}
    </Loader>
  );
}

export function ComingSoon({ title, text }) {
  return (
    <>
      <PageHeader title={title} />
      <div className="coming">
        <div className="coming-tag">Coming Soon</div>
        <p>{text}</p>
      </div>
    </>
  );
}
