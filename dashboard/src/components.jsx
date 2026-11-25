import { useEffect, useState } from "react";
import { api } from "./api.js";
import { DIMS, HUMAN, RELATIONSHIPS, STATUS, effortName, fmtDate, modelName, reasonLabel } from "./format.js";

export function useData(loader, deps) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    loader()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((error) => alive && setState({ error: error.message, loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function Loader({ state, children }) {
  if (state.error) return <div className="notice error">加载失败：{state.error}</div>;
  if (!state.data) return <div className="empty">加载中…</div>;
  return children(state.data);
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export function Score({ value, selected }) {
  if (value == null) return <span className="score none">—</span>;
  return <span className={`score ${selected ? "selected" : ""}`}>{Math.round(value)}</span>;
}

export function ModelTag({ model, effort }) {
  return (
    <span className="model-tag">
      <strong>{modelName(model)}</strong>
      <span>{effortName(effort)}</span>
    </span>
  );
}

/** 五个维度，每个 0–5。compact：一行字母 + 分段条；否则带完整名称。 */
export function Dims({ dims, compact, defs = DIMS }) {
  if (!dims) return null;
  return (
    <div className={compact ? "dims compact" : "dims"}>
      {defs.map((d) => (
        <div className="dim" key={d.key} title={`${d.label}（${d.zh}）${dims[d.key]} / 5 · 权重 ×${d.weight}`}>
          <span className="dim-name">{compact ? d.label.charAt(0) : d.label}</span>
          {!compact && <span className="dim-zh">{d.zh} ×{d.weight}</span>}
          <span className="dim-bar" aria-hidden="true">
            {[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= dims[d.key] ? "on" : ""} />)}
          </span>
          <span className="dim-val">{dims[d.key]}</span>
        </div>
      ))}
    </div>
  );
}

export function StatusBadge({ item }) {
  return (
    <span className={`badge status-${item.status}`}>
      {STATUS[item.status] || item.status}
      {item.restored && " · 人工恢复"}
    </span>
  );
}

export function FeedbackButtons({ item, onChange, withLabels }) {
  const [busy, setBusy] = useState(false);
  const set = async (key, e) => {
    e.stopPropagation();
    setBusy(true);
    try {
      onChange(await api.feedback(item.id, { human_status: item.human_status === key ? "none" : key }));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="feedback" role="group" aria-label="人工反馈">
      {HUMAN.map((h) => (
        <button key={h.key} type="button" disabled={busy} title={h.label}
          aria-pressed={item.human_status === h.key}
          className={`fb fb-${h.key} ${item.human_status === h.key ? "active" : ""}`}
          onClick={(e) => set(h.key, e)}>
          <span className="fb-icon">{h.icon}</span>
          {withLabels && <span>{h.label}</span>}
        </button>
      ))}
    </div>
  );
}

export function SourceLine({ item }) {
  return (
    <div className="meta-line">
      <span className="source">{item.source}</span>
      <span>{fmtDate(item.published_at)}</span>
      {item.engagement && <span>{item.engagement.label}</span>}
    </div>
  );
}

/** Candidates / Rejected / Borderline 共用的条目卡片 */
export function ItemCard({ item, onOpen, onChange, showRestore }) {
  const f = item.filter;
  const restore = async (e) => {
    e.stopPropagation();
    onChange(await (item.restored ? api.unrestore(item.id) : api.restore(item.id)));
  };
  return (
    <article className="item-card" onClick={() => onOpen(item.id)}>
      <div className="item-score">
        <Score value={item.score} selected={item.status === "candidate"} />
        <StatusBadge item={item} />
      </div>
      <div className="item-body">
        <h3>{item.title}</h3>
        <SourceLine item={item} />
        {f?.possible_change && <p className="field"><b>可能的变化</b>{f.possible_change}</p>}
        {f?.reason && <p className="field"><b>判断理由</b>{f.reason}</p>}
        {!f && item.reason_code && <p className="field"><b>规则过滤</b>{reasonLabel(item.reason_code)}</p>}
        <div className="item-foot">
          {f && <Dims dims={f} compact />}
          {item.reason_code && item.status !== "candidate" && <span className="chip">{reasonLabel(item.reason_code)}</span>}
          {item.mismatch && (
            <span className="chip warn" title="模型自己的 keep 判断和按分数得出的结论不一致">
              ⚠ 模型说{item.llm_keep ? "留" : "不留"}
            </span>
          )}
          {item.human_note && <span className="chip note" title={item.human_note}>有备注</span>}
        </div>
      </div>
      <div className="item-actions">
        <FeedbackButtons item={item} onChange={onChange} />
        {(showRestore || item.restored) && (
          <button type="button" className="btn small" onClick={restore}>
            {item.restored ? "撤销恢复" : "Restore to Candidate"}
          </button>
        )}
      </div>
    </article>
  );
}

function Row({ label, children }) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children || <span className="muted">—</span>}</dd>
    </div>
  );
}

/** 条目详情（右侧抽屉） */
export function ItemDrawer({ id, onClose, onChange }) {
  const [item, setItem] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setItem(null);
    setError(null);
    api.item(id).then((d) => { setItem(d); setNote(d.human_note); }).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const update = (next) => { setItem((cur) => ({ ...cur, ...next })); onChange?.(next); };
  const saveNote = async () => {
    update(await api.feedback(id, { human_note: note }));
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };
  const toggleRestore = async () => update(await (item.restored ? api.unrestore(id) : api.restore(id)));

  const f = item?.filter;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="条目详情">
        <button type="button" className="drawer-close" onClick={onClose} aria-label="关闭">×</button>
        {error && <div className="notice error">加载失败：{error}</div>}
        {!item && !error && <div className="empty">加载中…</div>}
        {item && (
          <>
            <div className="drawer-head">
              <Score value={item.score} selected={item.status === "candidate"} />
              <div>
                <StatusBadge item={item} />
                {item.reason_code && item.status !== "candidate" && <span className="chip">{reasonLabel(item.reason_code)}</span>}
                {item.mismatch && <span className="chip warn">⚠ 模型说{item.llm_keep ? "留" : "不留"}</span>}
              </div>
            </div>
            <h2>{item.title}</h2>
            <SourceLine item={item} />

            <section>
              <h4>人工反馈</h4>
              <FeedbackButtons item={item} onChange={update} withLabels />
              <textarea className="note" rows={3} value={note} placeholder="备注：为什么想做 / 不想做？以后用来调 prompt。"
                onChange={(e) => setNote(e.target.value)} />
              <div className="row">
                <button type="button" className="btn" onClick={saveNote} disabled={note === item.human_note}>保存备注</button>
                {saved && <span className="muted">已保存</span>}
                {(item.restored || ["filtered", "discarded"].includes(item.status)) && (
                  <button type="button" className="btn" onClick={toggleRestore}>
                    {item.restored ? "撤销恢复" : "Restore to Candidate"}
                  </button>
                )}
              </div>
            </section>

            <section>
              <h4>原始信息</h4>
              <dl>
                <Row label="原标题">{item.title}</Row>
                <Row label="原始摘要">{item.summary}</Row>
                <Row label="原始 URL">
                  <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a>
                  {item.engagement?.hn_url && <> · <a href={item.engagement.hn_url} target="_blank" rel="noreferrer">HN 讨论</a></>}
                </Row>
                <Row label="来源">{item.source}{item.tier ? ` · Tier ${item.tier}` : ""}{item.category ? ` · ${item.category}` : ""}</Row>
                <Row label="发布时间">{fmtDate(item.published_at)}</Row>
                <Row label="热度">{item.engagement?.label}</Row>
                <Row label="所属 Event">
                  {item.event && (
                    <a href={`#/events/${item.event.id}`} onClick={onClose}>
                      #{item.event.rank} {item.event.canonical_title}
                    </a>
                  )}
                </Row>
              </dl>
            </section>

            {f ? (
              <>
                <section>
                  <h4>AI 判断</h4>
                  <dl>
                    <Row label="判断理由">{f.reason}</Row>
                    <Row label="可能的变化">{f.possible_change}</Row>
                    <Row label="普通人关联">{f.ordinary_people_connection}</Row>
                    <Row label="故事角度">{f.possible_story_angle}</Row>
                    <Row label="可能的大趋势">{f.possible_bigger_trend}</Row>
                  </dl>
                </section>
                <section>
                  <h4>维度评分</h4>
                  <Dims dims={f} />
                  <dl>
                    <Row label="模型的 keep">{f.keep ? "留" : "不留"}</Row>
                    <Row label="Reject reason">{item.reason_code ? `${reasonLabel(item.reason_code)}（${item.reason_code}）` : ""}</Row>
                    <Row label="Model">{modelName(f.model)}</Row>
                    <Row label="Reasoning effort">{effortName(f.reasoning_effort)}</Row>
                    <Row label="Prompt version"><code>{f.prompt_version}</code></Row>
                  </dl>
                </section>
              </>
            ) : (
              <section>
                <h4>AI 判断</h4>
                <p className="muted">
                  {item.stage === "prefilter"
                    ? `这条被规则直接过滤（${reasonLabel(item.reason_code)}），没有交给模型评估。`
                    : "这条还没有被模型评估。"}
                </p>
              </section>
            )}

            {item.evaluations.length > 0 && (
              <section>
                <h4>历次评估</h4>
                <table className="table tight">
                  <thead><tr><th>Run</th><th>模型</th><th>Prompt</th><th className="num">分数</th><th>维度</th><th>结果</th></tr></thead>
                  <tbody>
                    {item.evaluations.map((e) => (
                      <tr key={e.run_id}>
                        <td>#{e.run_id}</td>
                        <td>{modelName(e.model)} {effortName(e.reasoning_effort)}</td>
                        <td><code>{e.prompt_version}</code></td>
                        <td className="num">{Math.round(e.score)}</td>
                        <td><Dims dims={e.dims} compact /></td>
                        <td>{e.selected ? "入选" : reasonLabel(e.final_reason || e.reject_reason)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </>
        )}
      </aside>
    </div>
  );
}

/** 分数分布直方图。series: [{ name, tone: 1|2, data: [{from,to,count}] }] */
export function Histogram({ series, height = 180 }) {
  const [hover, setHover] = useState(null);
  const W = 640, padL = 34, padB = 26, padT = 10;
  const plotW = W - padL - 8, plotH = height - padB - padT;
  const buckets = series[0].data;
  const rawMax = Math.max(1, ...series.flatMap((s) => s.data.map((d) => d.count)));
  const step = rawMax <= 10 ? 2 : rawMax <= 30 ? 10 : 20;
  const max = Math.ceil(rawMax / step) * step;
  const band = plotW / buckets.length;
  const gap = 2;
  const barW = Math.min(24, (band - 12 - gap * (series.length - 1)) / series.length);
  const groupW = barW * series.length + gap * (series.length - 1);
  const y = (v) => padT + plotH - (v / max) * plotH;

  return (
    <div className="chart">
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => <span key={s.name}><i className={`swatch tone-${s.tone}`} />{s.name}</span>)}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label="分数分布">
        {[0, max / 2, max].map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - 8} y1={y(t)} y2={y(t)} className={t === 0 ? "axis" : "grid"} />
            <text x={padL - 8} y={y(t) + 4} textAnchor="end" className="tick">{t}</text>
          </g>
        ))}
        {buckets.map((b, i) => {
          const x0 = padL + i * band + (band - groupW) / 2;
          return (
            <g key={b.from} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={padL + i * band} y={padT} width={band} height={plotH} fill="transparent" />
              {series.map((s, si) => {
                const c = s.data[i].count;
                const h = (c / max) * plotH;
                const x = x0 + si * (barW + gap);
                const r = Math.min(4, h);
                return c > 0 && (
                  <path key={s.name} className={`bar tone-${s.tone} ${hover === i ? "hover" : ""}`}
                    d={`M${x},${y(0)} V${y(c) + r} Q${x},${y(c)} ${x + r},${y(c)} H${x + barW - r} Q${x + barW},${y(c)} ${x + barW},${y(c) + r} V${y(0)} Z`} />
                );
              })}
              <text x={padL + i * band + band / 2} y={height - 8} textAnchor="middle" className="tick">{b.from}–{b.to}</text>
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <div className="tooltip" style={{ left: `${((padL + hover * band + band / 2) / W) * 100}%` }}>
          <b>{buckets[hover].from}–{buckets[hover].to} 分</b>
          {series.map((s) => (
            <span key={s.name}><i className={`swatch tone-${s.tone}`} />{series.length > 1 ? `${s.name}：` : ""}{s.data[hover].count} 条</span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Event 下面的原始报道：一眼看出哪些东西被合在了一起 */
export function ReportTree({ items, onOpen }) {
  return (
    <ul className="tree">
      {items.map((i) => (
        <li key={i.id} onClick={(e) => { e.stopPropagation(); onOpen(i.id); }}>
          <span className="tree-source">{i.source}</span>
          <span className="tree-title">{i.title}</span>
          <span className={`chip rel-${i.relationship}`}>{RELATIONSHIPS[i.relationship] || i.relationship}</span>
          {i.independent && <span className="chip good">独立来源</span>}
          <span className="tree-score">{i.score != null ? Math.round(i.score) : ""}</span>
        </li>
      ))}
    </ul>
  );
}

export function Confidence({ value }) {
  return (
    <span className="dim-bar confidence" title={`Confidence ${value} / 5`}>
      {[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= value ? "on" : ""} />)}
    </span>
  );
}

export function Stat({ label, value, hint, accent }) {
  return (
    <div className={`stat ${accent ? "accent" : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}
