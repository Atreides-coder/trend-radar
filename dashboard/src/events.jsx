import { useState } from "react";
import { api } from "./api.js";
import { Confidence, Dims, ItemCard, Loader, ModelTag, PageHeader, ReportTree, Score, Stat, useData } from "./components.jsx";
import { EVENT_DIMS, RELATIONSHIPS, TREND_STATUS, fmtDate, fmtDay } from "./format.js";
import { CreateVideoButton } from "./studio.jsx";

function Evidence({ e }) {
  return (
    <div className="meta-line">
      <span><b>{e.source_count}</b> 个来源</span>
      <span><b>{e.independent_source_count}</b> 个独立来源</span>
      <span><b>{e.item_count}</b> 篇报道</span>
      {e.has_official_source && <span>含官方来源</span>}
      {e.independent_source_count === 0 && <span className="warn-text">没有独立验证</span>}
    </div>
  );
}

function EventCard({ e, openItem }) {
  return (
    <article className={`event-card ${e.in_research_queue ? "queued" : ""}`}>
      <a className="event-rank" href={`#/events/${e.id}`} aria-label={`第 ${e.rank} 名`}>
        <span className="rank">#{e.rank ?? "—"}</span>
        <Score value={e.score} selected={e.in_research_queue} />
      </a>
      <div className="item-body">
        <h3><a href={`#/events/${e.id}`}>{e.canonical_title}</a></h3>
        <Evidence e={e} />
        {e.core_change && <p className="field"><b>核心变化</b>{e.core_change}</p>}
        {e.why_it_matters && <p className="field"><b>为什么值得讲</b>{e.why_it_matters}</p>}
        {e.possible_bigger_trend && <p className="field"><b>可能的大趋势</b>{e.possible_bigger_trend}</p>}
        <div className="item-foot">
          <Dims dims={e.dims} defs={EVENT_DIMS} compact />
          {e.in_research_queue && <span className="chip good">Research Queue</span>}
          {e.trends.map((t) => <a key={t.id} className="chip link" href={`#/trends/${t.id}`}>趋势 · {t.canonical_name}</a>)}
          <span className="push-right"><CreateVideoButton eventId={e.id} small /></span>
        </div>
        <ReportTree items={e.items} onOpen={openItem} />
      </div>
    </article>
  );
}

export function EventsPage({ openItem, version }) {
  const state = useData(() => api.events(), [version]);
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("");
  return (
    <Loader state={state}>
      {({ run, events }) => {
        if (!run) return (<><PageHeader title="Events" /><div className="empty">还没有聚类结果。运行 <code>python -m src.main --stage cluster</code>。</div></>);
        const needle = q.toLowerCase();
        const list = events.filter((e) =>
          (!only || (only === "queue" ? e.in_research_queue : only === "merged" ? e.item_count > 1 : e.independent_source_count === 0))
          && (!needle || e.canonical_title.toLowerCase().includes(needle)
            || e.items.some((i) => i.title.toLowerCase().includes(needle) || i.source.toLowerCase().includes(needle))));
        return (
          <>
            <PageHeader title="Events"
              subtitle={`${run.input_signals} 个 signal 聚成 ${events.length} 个 Event，按 Global Ranking 排序。每个 Event 下面是它包含的原始报道。`}>
              <ModelTag model={run.model} effort={run.reasoning_effort} />
            </PageHeader>
            <div className="filters">
              <input type="search" placeholder="搜索事件 / 报道标题 / 来源" value={q} onChange={(e) => setQ(e.target.value)} />
              <div className="segmented" role="group" aria-label="筛选">
                {[["", "全部"], ["queue", "Research Queue"], ["merged", "多篇报道合并"], ["unverified", "没有独立验证"]].map(([k, label]) => (
                  <button key={k} type="button" className={only === k ? "active" : ""} onClick={() => setOnly(k)}>{label}</button>
                ))}
              </div>
              <span className="count">{list.length} / {events.length} 个</span>
            </div>
            {run.note && <div className="notice warn">{run.note}</div>}
            {run.problems.length > 0 && (
              <div className="notice warn">模型输出有问题，已自动修复：{run.problems.join("；")}</div>
            )}
            <div className="cards">
              {list.map((e) => <EventCard key={e.id} e={e} openItem={openItem} />)}
            </div>
            {list.length === 0 && <div className="empty">没有符合条件的 Event。</div>}
          </>
        );
      }}
    </Loader>
  );
}

export function EventDetail({ id, openItem, version }) {
  const state = useData(() => api.event(id), [id, version]);
  const [local, setLocal] = useState({});
  return (
    <Loader state={state}>
      {(e) => (
        <>
          <PageHeader title={e.canonical_title} subtitle={`Event · ${fmtDay(e.first_seen)}${e.last_seen !== e.first_seen ? ` – ${fmtDay(e.last_seen)}` : ""}`}>
            {e.in_research_queue && <span className="chip good">Research Queue</span>}
            <CreateVideoButton eventId={e.id} />
            <a className="btn" href="#/events">← 全部 Events</a>
          </PageHeader>

          <section className="grid stats four">
            <Stat label="Global Rank" value={e.rank ? `#${e.rank}` : "—"} hint={`共 ${e.total_events} 个 Event`} accent={e.in_research_queue} />
            <Stat label="Score" value={e.score != null ? Math.round(e.score) : "—"} hint="由六个维度按权重计算" />
            <Stat label="来源" value={`${e.source_count} 个`} hint={`${e.item_count} 篇报道${e.has_official_source ? " · 含官方来源" : ""}`} />
            <Stat label="独立来源" value={`${e.independent_source_count} 个`} hint={e.independent_source_count === 0 ? "没有独立验证" : "官方稿和转述不计入"} />
          </section>

          <section className="grid two">
            <div className="panel">
              <h2>这件事</h2>
              <dl>
                <div className="kv"><dt>摘要</dt><dd>{e.summary}</dd></div>
                <div className="kv"><dt>核心变化</dt><dd>{e.core_change}</dd></div>
                <div className="kv"><dt>为什么值得讲</dt><dd>{e.why_it_matters || <span className="muted">—</span>}</dd></div>
                <div className="kv"><dt>可能的大趋势</dt><dd>{e.possible_bigger_trend || <span className="muted">—</span>}</dd></div>
                <div className="kv"><dt>为什么合在一起</dt><dd>{e.cluster_reason}</dd></div>
              </dl>
            </div>
            <div className="panel">
              <h2>Global Ranking 维度</h2>
              {e.dims ? <Dims dims={e.dims} defs={EVENT_DIMS} /> : <p className="muted">这个 Event 还没有排名。</p>}
              <p className="muted">Fast Filter 单篇最高分 {Math.round(e.max_filter_score ?? 0)} · 平均 {Math.round(e.avg_filter_score ?? 0)}（仅供参考，不参与排名）</p>
            </div>
          </section>

          {e.trends.length > 0 && (
            <section className="panel">
              <h2>所属趋势（假设）</h2>
              {e.trends.map((t) => (
                <p key={t.id} className="field"><a href={`#/trends/${t.id}`}><b className="link-b">{t.canonical_name}</b></a> <Confidence value={t.confidence} /> {t.hypothesis}</p>
              ))}
            </section>
          )}

          <section>
            <h2>包含的原始报道（{e.items.length}）</h2>
            <div className="cards">
              {e.items.map((raw) => {
                const i = { ...raw, ...(local[raw.id] || {}) };
                return (
                  <div key={i.id} className="report">
                    <div className="report-rel">
                      <span className={`chip rel-${i.relationship}`}>{RELATIONSHIPS[i.relationship]}</span>
                      {i.independent ? <span className="chip good">独立来源</span> : <span className="chip">不计入独立来源</span>}
                    </div>
                    <ItemCard item={i} onOpen={openItem} onChange={(n) => setLocal((l) => ({ ...l, [n.id]: n }))} />
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </Loader>
  );
}

export function TrendsPage() {
  const state = useData(() => api.trends(), []);
  return (
    <Loader state={state}>
      {({ trends }) => (
        <>
          <PageHeader title="Trends" subtitle="由多个不同 Event 共同支持的方向。趋势是假设，不是事实；跨天保留，用来观察它是否持续出现。" />
          {trends.length === 0 && <div className="empty">还没有趋势。聚类之后，系统会尝试把指向同一方向的不同 Event 连起来。</div>}
          <div className="cards">
            {trends.map((t) => (
              <a key={t.id} className="trend-card" href={`#/trends/${t.id}`}>
                <div className="row between">
                  <h3>{t.canonical_name}</h3>
                  <div className="row">
                    <span className="badge">{TREND_STATUS[t.status] || t.status}</span>
                    <span className="muted">Confidence</span><Confidence value={t.confidence} />
                  </div>
                </div>
                <p className="field">{t.description}</p>
                <div className="meta-line">
                  <span><b>{t.event_count ?? 0}</b> 个 Event</span>
                  <span><b>{t.source_count ?? 0}</b> 个来源</span>
                  <span><b>{t.mention_count ?? 0}</b> 篇报道</span>
                  <span>首次出现 {fmtDay(t.first_seen)}</span>
                  <span>最近出现 {fmtDay(t.last_seen)}</span>
                  {!t.in_latest_run && <span className="warn-text">最近一次运行没有出现</span>}
                </div>
                <ul className="tree static">
                  {t.events.map((e) => (
                    <li key={e.id}><span className="tree-source">#{e.rank}</span><span className="tree-title">{e.canonical_title}</span>
                      <span className="tree-score">{e.score != null ? Math.round(e.score) : ""}</span></li>
                  ))}
                </ul>
              </a>
            ))}
          </div>
        </>
      )}
    </Loader>
  );
}

export function TrendDetail({ id, openItem }) {
  const state = useData(() => api.trend(id), [id]);
  return (
    <Loader state={state}>
      {(t) => (
        <>
          <PageHeader title={t.canonical_name} subtitle="Trend hypothesis · 这是一个假设，不是事实">
            <span className="badge">{TREND_STATUS[t.status] || t.status}</span>
            <a className="btn" href="#/trends">← 全部 Trends</a>
          </PageHeader>
          <section className="grid stats four">
            <Stat label="Confidence" value={<>{t.confidence} / 5</>} hint="模型对这个假设的把握" />
            <Stat label="Events" value={t.event_count ?? 0} hint={`${t.mention_count ?? 0} 篇报道 · ${t.source_count ?? 0} 个来源`} />
            <Stat label="First seen" value={fmtDate(t.first_seen)} />
            <Stat label="Last seen" value={fmtDate(t.last_seen)} hint="Velocity：历史不足 7 天，暂不计算" />
          </section>
          <section className="panel">
            <h2>假设</h2>
            <p>{t.description}</p>
            {t.aliases.length > 0 && <p className="muted">别名：{t.aliases.join(" · ")}</p>}
          </section>
          <section>
            <h2>证据链：Trend → Events → 原始报道</h2>
            {t.events.length === 0 && <div className="empty">最近一次运行里没有 Event 支持这个趋势。</div>}
            <div className="cards">
              {t.events.map((e) => (
                <article key={e.id} className="event-card">
                  <a className="event-rank" href={`#/events/${e.id}`}>
                    <span className="rank">#{e.rank}</span>
                    <Score value={e.score} selected={e.in_research_queue} />
                  </a>
                  <div className="item-body">
                    <h3><a href={`#/events/${e.id}`}>{e.canonical_title}</a></h3>
                    <Evidence e={e} />
                    <p className="field"><b>核心变化</b>{e.core_change}</p>
                    <ReportTree items={e.items} onOpen={openItem} />
                  </div>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </Loader>
  );
}

export function ClusterRunsTable() {
  const state = useData(() => api.clusterRuns(), []);
  if (!state.data || state.data.runs.length === 0) return null;
  return (
    <section>
      <h2>Phase 3 · Clustering Runs</h2>
      <div className="panel flush">
        <table className="table">
          <thead>
            <tr><th>Run</th><th>时间</th><th>Model</th><th>Effort</th><th>Prompt（聚类 / 排名 / 趋势）</th><th className="num">Signals</th>
              <th className="num">Events</th><th className="num">Trends</th><th className="num">Codex calls</th><th className="num">Tokens</th><th className="num">Duration</th></tr>
          </thead>
          <tbody>
            {state.data.runs.map((r) => (
              <tr key={r.id}>
                <td>#{r.id}</td>
                <td className="nowrap">{fmtDate(r.started_at)}</td>
                <td><b>{r.model}</b></td>
                <td>{r.reasoning_effort}</td>
                <td><code>{r.prompt_version}</code></td>
                <td className="num">{r.input_signals}</td>
                <td className="num">{r.output_events}</td>
                <td className="num">{r.output_trends}</td>
                <td className="num">{r.usage.calls ?? "—"}</td>
                <td className="num">{r.usage.usage_reported ? ((r.usage.input_tokens || 0) + (r.usage.output_tokens || 0)).toLocaleString("en-US") : "—"}</td>
                <td className="num">{r.duration_seconds != null ? `${Math.floor(r.duration_seconds / 60)} 分 ${Math.round(r.duration_seconds % 60)} 秒` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
