import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { Loader, PageHeader, Stat, useData } from "./components.jsx";
import { effortName, fmtDate, modelName } from "./format.js";

const STEPS = [
  ["research", "Research"], ["script", "Script"], ["voice", "Voice"], ["assets", "Assets"],
  ["storyboard", "Storyboard"], ["render", "Render"], ["qc", "QC"],
];
const COMPONENT_ZH = {
  HookScene: "开场大字", RealMediaScene: "实拍素材", BrowserScreenshotScene: "网页截图", PhoneOrDesktopScene: "系统界面",
  DataScene: "数据", ConceptDiagramScene: "图解动画", QuoteScene: "引语", ConclusionScene: "结尾",
};
const TYPE_ZH = {
  official_ui: "真实界面", web_screenshot: "官方页面", article_screenshot: "报道页面", article_image: "报道题图", user_upload: "人工上传", autoclip_video: "AutoClip 视频",
};
const REAL = ["RealMediaScene", "BrowserScreenshotScene", "PhoneOrDesktopScene"];
const METRICS = { points: "分", score: "分", comments: "条评论", num_comments: "条评论", likes: "个赞", upvotes: "票赞同", views: "次浏览", stars: "个星标", replies: "条回复" };

function StatusBadge({ state }) {
  const cls = state.status === "Ready" ? "status-candidate" : state.status === "Failed" || state.status === "Stopped" ? "status-failed" : state.running ? "status-new" : "";
  return <span className={`badge big ${cls}`}>{state.running && <i className="spinner" />}{state.status}</span>;
}

function StepBar({ state }) {
  return (
    <div className="stepbar">
      {STEPS.map(([key, label]) => {
        const st = state.steps?.[key] || {};
        return (
          <div key={key} className={`step step-${st.status || "pending"}`} title={st.error || ""}>
            <span className="step-name">{label}</span>
            <span className="step-meta">{st.status === "done" ? `${Math.round(st.seconds ?? 0)}s` : st.status === "running" ? "进行中" : st.status === "failed" ? "失败" : "—"}</span>
          </div>
        );
      })}
    </div>
  );
}

export function CreateVideoButton({ eventId, small }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const go = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api.createVideo({ event_id: eventId });
      window.location.hash = `#/video-studio/${res.id}`;
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className={`btn primary ${small ? "small" : ""}`} onClick={go} disabled={busy}>
        {busy ? "创建中…" : "▶ Create Video"}
      </button>
      {error && <span className="warn-text">{error}</span>}
    </>
  );
}

export function StudioList() {
  const state = useData(() => api.videoProjects(), []);
  return (
    <Loader state={state}>
      {({ projects }) => (
        <>
          <PageHeader title="Video Studio" subtitle="从一个 Event 到一条可以观看的短视频。在 Events 页面点 Create Video 开始。" />
          {projects.length === 0 && <div className="empty">还没有视频项目。去 <a href="#/events">Events</a> 选一个 Event，点 Create Video。</div>}
          <div className="cards">
            {projects.map((p) => (
              <a key={p.id} className="project-card" href={`#/video-studio/${p.id}`}>
                {p.files["render/thumbnail.png"]
                  ? <img src={`/video-files/${p.id}/render/thumbnail.png`} alt="" />
                  : <div className="thumb-empty">还没有成片</div>}
                <div>
                  <h3>{p.title}</h3>
                  <p className="field">{p.angle}</p>
                  <div className="row"><StatusBadge state={p} /><span className="muted">创建于 {fmtDate(p.created_at)}</span></div>
                </div>
              </a>
            ))}
          </div>
        </>
      )}
    </Loader>
  );
}

function Section({ id, title, hint, children, actions }) {
  return (
    <section className="panel" id={id}>
      <div className="row between"><h2>{title}</h2>{actions}</div>
      {hint && <p className="muted">{hint}</p>}
      {children}
    </section>
  );
}

function FactPack({ pack }) {
  const src = Object.fromEntries(pack.sources.map((s) => [s.id, s]));
  const refs = (ids) => ids.map((i) => <a key={i} className="ref" href={src[i]?.url} target="_blank" rel="noreferrer" title={src[i]?.title}>[{i}]</a>);
  return (
    <>
      <dl>
        <div className="kv"><dt>Topic</dt><dd>{pack.topic}</dd></div>
        <div className="kv"><dt>核心变化</dt><dd>{pack.core_change}</dd></div>
        <div className="kv"><dt>改了什么 <em className="tag fact">FACT</em></dt><dd>{pack.what_changed}</dd></div>
        <div className="kv"><dt>为什么是现在 <em className="tag inf">INFERENCE</em></dt><dd>{pack.why_now}</dd></div>
        <div className="kv"><dt>为什么值得讲 <em className="tag inf">INFERENCE</em></dt><dd>{pack.why_it_matters}</dd></div>
        <div className="kv"><dt>对普通人 <em className="tag inf">INFERENCE</em></dt><dd>{pack.ordinary_people_impact}</dd></div>
      </dl>
      <h4>Verified facts <em className="tag fact">FACT</em></h4>
      <ol className="facts">{pack.verified_facts.map((f) => <li key={f.id} value={f.id}>{f.claim} {refs(f.source_ids)}</li>)}</ol>
      {pack.timeline.length > 0 && (<><h4>Timeline</h4><ul className="plain">{pack.timeline.map((t, i) => <li key={i}><b>{t.date}</b> {t.event} {refs(t.source_ids)}</li>)}</ul></>)}
      {pack.key_numbers.length > 0 && (<><h4>Key numbers</h4><ul className="plain">{pack.key_numbers.map((n, i) => <li key={i}><b>{n.value}</b> {n.meaning} {refs(n.source_ids)}</li>)}</ul></>)}
      <h4>Inferences <em className="tag inf">INFERENCE</em></h4>
      <ul className="plain">{pack.inferences.map((x, i) => <li key={i}>{x.text} <span className="muted">依据事实 {x.based_on_fact_ids.join("、") || "—"}</span></li>)}</ul>
      <h4>Predictions <em className="tag pred">PREDICTION</em></h4>
      <ul className="plain">{pack.predictions.map((x, i) => <li key={i}>{x.text} <span className="muted">依据：{x.basis}</span></li>)}</ul>
      <div className="grid two">
        <div><h4>Limitations</h4><ul className="plain">{pack.limitations.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
        <div><h4>Counterpoints</h4><ul className="plain">{pack.counterpoints.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
      </div>
      <h4>Sources</h4>
      <ul className="plain">{pack.sources.map((s) => (
        <li key={s.id}>[{s.id}] <span className="chip">{s.type}</span> <b>{s.publisher}</b> · <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> <span className="muted">{s.used_for}</span></li>
      ))}</ul>
    </>
  );
}

function ScriptEditor({ id, script, running, readOnly, reload }) {
  const [draft, setDraft] = useState({});
  const [note, setNote] = useState("");
  const [instruction, setInstruction] = useState({});
  const dirty = Object.keys(draft).some((k) => draft[k] !== script.scenes.find((s) => s.scene_id === Number(k))?.voice);
  const total = script.scenes.reduce((n, s) => n + (draft[s.scene_id] ?? s.voice).length, 0);
  const act = async (fn, msg) => {
    try { await fn(); setNote(msg); setDraft({}); reload(); } catch (e) { setNote(`失败：${e.message}`); }
  };
  const save = (thenRun) => act(async () => {
    await api.editScript(id, Object.entries(draft).map(([scene_id, voice]) => ({ scene_id: Number(scene_id), voice })));
    if (thenRun) await api.runVideo(id, ["voice", "storyboard", "render", "qc"]);
  }, thenRun ? "已保存，正在重新配音、分镜和渲染…" : "已保存。重新配音并渲染后才会进成片。");
  return (
    <>
      <h4>Hook 备选（{script.hooks.length}）</h4>
      <ol className="hooks">
        {script.hooks.map((h, i) => (
          <li key={i} className={i + 1 === script.chosen_hook ? "chosen" : ""}>{h.text} <span className="muted">· {h.style}</span>{i + 1 === script.chosen_hook && <span className="chip good">选用</span>}</li>
        ))}
      </ol>
      <p className="muted">选用理由：{script.hook_reason}</p>
      <h4>叙事</h4>
      <ol className="plain numbered">{script.narrative.map((n, i) => <li key={i}>{n}</li>)}</ol>
      <h4>分场口播（共 {total} 字）</h4>
      <div className="scenes">
        {script.scenes.map((s) => (
          <div key={s.scene_id} className="scene-row">
            <div className="scene-meta">
              <b>{s.scene_id}</b><span className="chip">{s.purpose}</span>
              <em className={`tag ${s.claim_type === "FACT" ? "fact" : s.claim_type === "PREDICTION" ? "pred" : s.claim_type === "INFERENCE" ? "inf" : ""}`}>{s.claim_type}</em>
              {s.fact_ids.length > 0 && <span className="muted">事实 {s.fact_ids.join("、")}</span>}
            </div>
            {readOnly ? <p>{s.voice}</p> : (
              <textarea rows={2} value={draft[s.scene_id] ?? s.voice} disabled={running}
                onChange={(e) => setDraft((d) => ({ ...d, [s.scene_id]: e.target.value }))} />
            )}
            <div className="muted">画面：{s.visual_intent}（{s.preferred_asset_type}）{s.emphasis_words.length > 0 && <> · 重点词：{s.emphasis_words.join("、")}</>}</div>
            {!readOnly && <div className="row">
              <input type="search" placeholder="重写要求（可留空），例如：更口语一点" value={instruction[s.scene_id] || ""}
                onChange={(e) => setInstruction((x) => ({ ...x, [s.scene_id]: e.target.value }))} />
              <button type="button" className="btn small" disabled={running}
                onClick={() => act(() => api.regenScene(id, s.scene_id, instruction[s.scene_id] || ""), `正在重写第 ${s.scene_id} 场，然后重新配音和渲染…`)}>
                重新生成这一场
              </button>
            </div>}
          </div>
        ))}
      </div>
      {!readOnly && <div className="row">
        <button type="button" className="btn" disabled={!dirty || running} onClick={() => save(false)}>保存修改</button>
        <button type="button" className="btn primary" disabled={!dirty || running} onClick={() => save(true)}>保存并重新配音 + 渲染</button>
        {note && <span className="muted">{note}</span>}
      </div>}
      {script.revisions?.length > 0 && <p className="muted">修改记录：{script.revisions.map((r) => `${r.reason}（${r.what_changed}）`).join("；")}</p>}
    </>
  );
}

function AssetPreview({ asset, base, link = false }) {
  const src = `${base}/${asset.path}`;
  if (asset.type === "autoclip_video") return <video src={src} controls muted playsInline preload="metadata" aria-label={asset.description || asset.id} />;
  const img = <img src={src} alt="" loading="lazy" />;
  return link ? <a href={src} target="_blank" rel="noreferrer">{img}</a> : img;
}

function Storyboard({ id, board, library, base, running, readOnly, reload }) {
  const [error, setError] = useState("");
  const replace = async (scene_id, shot_index, asset_id) => {
    if (!asset_id) return;
    try {
      await api.replaceAsset(id, { scene_id, shot_index, asset_id });
      setError("");
      reload();
    } catch (e) { setError(e.message); }
  };
  return (
    <>
      <div className="grid stats four">
        <Stat label="镜头" value={board.stats.shots} hint={`平均 ${board.stats.avg_shot}s · 最长 ${board.stats.longest_shot}s`} />
        <Stat label="真实素材占比" value={`${Math.round(board.stats.real_ratio * 100)}%`} hint={`${board.stats.real_seconds}s / ${board.duration.toFixed(1)}s · 目标 60–70%`} />
      </div>
      {board.notes.length > 0 && <div className="notice warn">{board.notes.join("；")}</div>}
      {error && <p className="warn-text" role="alert">{error}</p>}
      <div className="timeline" aria-label="镜头时间线">
        {board.scenes.flatMap((sc) => sc.shots.map((sh, i) => (
          <div key={`${sc.scene_id}-${i}`} className={`tl ${REAL.includes(sh.component) ? "real" : "anim"}`}
            style={{ flexGrow: sh.end - sh.start }} title={`${sh.start.toFixed(1)}–${sh.end.toFixed(1)}s ${COMPONENT_ZH[sh.component]}`} />
        )))}
      </div>
      <div className="legend"><span><i className="swatch tone-1" />真实素材</span><span><i className="swatch tone-anim" />Remotion 动画 / 文字</span></div>
      {board.scenes.map((sc) => (
        <div key={sc.scene_id} className="board-scene">
          <div className="scene-meta"><b>{sc.scene_id}</b><span className="chip">{sc.purpose}</span><span className="muted">{sc.start.toFixed(1)}–{sc.end.toFixed(1)}s</span><span>{sc.voice}</span></div>
          {sc.shots.map((sh, i) => (
            <div key={i} className="shot">
              {sh.asset ? <AssetPreview asset={sh.asset} base={base} /> : <div className="shot-anim">{COMPONENT_ZH[sh.component]}</div>}
              <div>
                <div className="row">
                  <b>{COMPONENT_ZH[sh.component] || sh.component}</b>
                  <span className="muted">{sh.start.toFixed(1)}–{sh.end.toFixed(1)}s（{(sh.end - sh.start).toFixed(1)}s）</span>
                  {sh.asset && <span className="chip">{sh.asset.source}</span>}
                </div>
                {sh.headline && <div className="field"><b>画面标签</b>{sh.headline}{sh.sub && ` · ${sh.sub}`}</div>}
                {sh.highlight_text && <div className="field"><b>框出</b>{sh.highlight_text}{!sh.highlight && <span className="warn-text">（没在截图上找到）</span>}</div>}
                {sh.diagram?.kind && sh.diagram.kind !== "none" && (
                  <div className="field"><b>图解</b>{sh.diagram.title} · {sh.diagram.kind === "compare"
                    ? `${sh.diagram.left_label}（${sh.diagram.left_items.join("、")}）↔ ${sh.diagram.right_label}（${sh.diagram.right_items.join("、")}）`
                    : sh.diagram.steps.join(" → ")}</div>
                )}
                <div className="muted">{sh.reason}</div>
                {!readOnly && <select value="" disabled={running} onChange={(e) => replace(sc.scene_id, i, e.target.value)} aria-label="替换素材">
                  <option value="">替换素材…</option>
                  {library.map((a) => <option key={a.id} value={a.id}>{TYPE_ZH[a.type] || a.type} · {a.type === "autoclip_video" ? a.description || a.source : `${a.source} · ${a.id}`}</option>)}
                </select>}
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

function Assets({ id, library, base, readOnly, reload }) {
  const input = useRef(null);
  const scanInput = useRef(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState("");
  const [notice, setNotice] = useState("");
  const upload = async (e, mode) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(mode);
    setNotice("");
    setError(null);
    try {
      const result = await api.uploadAsset(id, file, mode);
      setNotice(mode === "scan" ? `检测到 ${result.detected_shots} 个镜头，提取了 ${result.assets.length} 段候选素材。` : `已导入 ${file.name}`);
      reload();
    } catch (err) { setError(err.message); }
    finally { setUploading(""); }
    e.target.value = "";
  };
  return (
    <>
      <div className="asset-grid">
        {library.map((a) => (
          <figure key={a.id}>
            <AssetPreview asset={a} base={base} link />
            <figcaption>
              <div className="row"><span className="chip">{TYPE_ZH[a.type] || a.type}</span><b>{/^https?:\/\//i.test(a.url) ? <a href={a.url} target="_blank" rel="noreferrer">{a.source}</a> : a.source}</b></div>
              <div className="muted">{a.width}×{a.height}{Number.isFinite(a.duration) && ` · ${a.duration.toFixed(1)} 秒`} · {a.id}</div>
              <div>{a.description}</div>
              <div className="muted">{a.license_or_usage_note}</div>
            </figcaption>
          </figure>
        ))}
      </div>
      {!readOnly && <div className="row">
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,video/mp4,.mp4" hidden onChange={(e) => upload(e, "import")} />
        <button type="button" className="btn" disabled={!!uploading} onClick={() => input.current?.click()}>{uploading === "import" ? "正在导入…" : "导入图片或 AutoClip MP4"}</button>
        <input ref={scanInput} type="file" accept=".mp4,.mov,.mkv,.webm,video/mp4,video/quicktime,video/webm,video/x-matroska" hidden onChange={(e) => upload(e, "scan")} />
        <button type="button" className="btn" disabled={!!uploading} onClick={() => scanInput.current?.click()}>{uploading === "scan" ? "正在提取…" : "从视频提取候选镜头"}</button>
        <span className="muted">按画面切换选取，最多 6 段，每段最长 6 秒。</span>
        {notice && <span role="status">{notice}</span>}
        {error && <span className="warn-text">{error}</span>}
      </div>}
    </>
  );
}

function CommunityLeads({ id, report, running, reload }) {
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const search = async () => {
    setSearching(true);
    setError("");
    try { await api.refreshCommunityLeads(id); reload(); } catch (e) { setError(e.message); }
    finally { setSearching(false); }
  };
  const status = { empty: "本次未找到相关讨论。", unavailable: "社区来源暂不可用。", failed: "本次检索失败。", disabled: "本次研究未启用社区检索。" };
  const items = report?.items || [];
  return (
    <Section id="community-leads" title="社区线索 · last30days" hint={report?.query} actions={
      <button type="button" className="btn" disabled={running || searching} onClick={search}>
        {searching ? "正在检索…" : report ? "刷新社区线索" : "查找近 30 天讨论"}
      </button>
    }>
      {error && <p className="warn-text" role="alert">{error}</p>}
      {report?.from_cache && <p className="notice warn">{report.message || status[report.status]} 以下为上次成功检索的线索{report.last_success_at && `（${report.last_success_at}）`}。</p>}
      {report && !report.from_cache && items.length === 0 && <p className="muted">{report.message || status[report.status] || "本次未找到相关讨论。"}</p>}
      {!report?.from_cache && items.length > 0 && report.message && <p className="muted">{report.message}</p>}
      {items.length > 0 && <ul className="plain">{items.map((item) => (
        <li key={`${item.platform}:${item.url}`}>
          {/^(https?):\/\//i.test(item.url) ? <a href={item.url} target="_blank" rel="noreferrer">{item.title || item.url}</a> : item.title}
          <span className="muted"> · {[item.platform, item.date, ...Object.entries(item.engagement || {})
            .filter(([, n]) => Number.isFinite(n))
            .map(([key, n]) => `${n.toLocaleString("zh-CN")} ${METRICS[key] || key}`)].filter(Boolean).join(" · ")}</span>
          {item.summary && <div className="field">{item.summary}</div>}
        </li>
      ))}</ul>}
    </Section>
  );
}

export function StudioProject({ id }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const reload = () => setTick((t) => t + 1);

  useEffect(() => {
    let alive = true;
    api.videoProject(id).then((d) => alive && (setData(d), setError(null))).catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [id, tick]);

  // 运行中每 3 秒刷新一次状态
  const running = data?.state.running;
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, [running]);

  if (error) return <div className="notice error">加载失败：{error}</div>;
  if (!data) return <div className="empty">加载中…</div>;
  const { state, fact_pack: pack, script, storyboard: board, library, captions, timings, qc, files_base: base } = data;
  const directed = state.directed;
  const run = async (steps) => { try { await api.runVideo(id, steps); reload(); } catch (e) { setError(e.message); } };
  const v = `?v=${encodeURIComponent(state.updated_at)}`;   // 重新渲染后绕过浏览器缓存

  return (
    <>
      <PageHeader title={script?.title || state.title} subtitle={`Video Project · ${state.id}`}>
        <StatusBadge state={state} />
        <a className="btn" href="#/video-studio">← 全部项目</a>
      </PageHeader>
      <StepBar state={state} />
      {state.error && <div className="notice error">{state.error}</div>}

      <div className="row actions">
        {directed
          ? <button type="button" className="btn" disabled={running} onClick={() => run(["voice", "render", "qc"])}>重新配音并渲染导演版</button>
          : <button type="button" className="btn" disabled={running} onClick={() => run(["voice", "storyboard", "render", "qc"])}>重新 TTS（并重新分镜、渲染）</button>}
        <button type="button" className="btn" disabled={running || (directed ? !timings?.duration || !state.files["audio/voice.wav"] : !board)} onClick={() => run(["render", "qc"])}>
          {directed ? "沿用配音重渲染导演版" : "重新 Render"}
        </button>
        {!directed && <button type="button" className="btn" disabled={running} onClick={() => run(STEPS.map((s) => s[0]))}>从头全部重跑</button>}
        {state.model && <span className="muted">Codex：{modelName(state.model)} · {effortName(state.reasoning_effort)}</span>}
      </div>

      <div className="grid two studio-top">
        <Section id="render" title="Render" hint={state.files["render/final.mp4"] ? "render/final.mp4 · 1080×1920 · 30fps" : "还没有成片。"}>
          {state.files["render/final.mp4"] && (
            <>
              <video className="player" controls preload="metadata" poster={`${base}/render/thumbnail.png${v}`} src={`${base}/render/final.mp4${v}`} />
              <div className="row">
                <a className="btn small" href={`${base}/render/final.mp4`} download>下载 final.mp4</a>
                <a className="btn small" href={`${base}/render/preview.mp4`} target="_blank" rel="noreferrer">preview.mp4</a>
                <a className="btn small" href={`${base}/render/thumbnail.png`} target="_blank" rel="noreferrer">thumbnail.png</a>
              </div>
            </>
          )}
        </Section>
        <div>
          <Section id="topic" title="Topic">
            <dl>
              <div className="kv"><dt>Event</dt><dd>{state.event_id ? <a href={`#/events/${state.event_id}`}>#{state.event?.rank} {state.title}</a> : state.title}</dd></div>
              <div className="kv"><dt>叙事方向</dt><dd>{state.angle}</dd></div>
              <div className="kv"><dt>创建时间</dt><dd>{fmtDate(state.created_at)}</dd></div>
            </dl>
          </Section>
          <Section id="qc" title="QC" hint={qc ? `结论：${qc.result}` : "成片生成后自动检查。"}>
            {qc && (
              <table className="table tight">
                <tbody>{qc.checks.map((c) => (
                  <tr key={c.name}><td className="nowrap">{c.status === "PASS" ? "✅" : c.status === "WARN" ? "⚠️" : "❌"} {c.name}</td><td className="muted">{c.detail}</td></tr>
                ))}</tbody>
              </table>
            )}
          </Section>
          <Section id="audio" title="Audio" hint={timings?.duration ? `${timings.provider} · ${timings.voice} · rate ${timings.rate} · ${timings.duration.toFixed(1)} 秒 · ${captions.length} 页字幕` : "还没有配音。"}>
            {state.files["audio/voice.wav"] && <audio controls preload="none" src={`${base}/audio/voice.wav${v}`} style={{ width: "100%" }} />}
            {captions.length > 0 && <p className="captions-preview">{captions.map((c, i) => <span key={i} title={`${(c.startMs / 1000).toFixed(1)}s`}>{c.text}</span>)}</p>}
          </Section>
        </div>
      </div>

      {script && <Section id="script" title="Script" hint={directed ? "在 shots.json 修改导演版口播后，点“重新配音并渲染导演版”。" : "可以直接改口播。改完需要重新配音和渲染才会进成片。"}><ScriptEditor id={id} script={script} running={running} readOnly={directed} reload={reload} /></Section>}
      {board && <Section id="storyboard" title="Storyboard" hint={directed ? "导演版分镜由 shots.json 和对应的 Remotion 画面模板控制。" : "每一场的镜头、组件和素材。替换素材后点“重新 Render”即可，不需要重新配音。"}><Storyboard id={id} board={board} library={library} base={base} running={running} readOnly={directed} reload={reload} /></Section>}
      {(!directed || library.length > 0) && <Section id="assets" title={`Assets（${library.length}）`}><Assets id={id} library={library} base={base} readOnly={directed} reload={reload} /></Section>}
      {!directed && <CommunityLeads id={id} report={data.last30days} running={running} reload={reload} />}
      {pack && <Section id="research" title="Research · Fact Pack" hint="只研究这一个选题。事实、推断、预测分开标注。"><FactPack pack={pack} /></Section>}
      <details className="panel"><summary>Pipeline log</summary><pre className="prompt">{data.log || "（空）"}</pre></details>
    </>
  );
}
