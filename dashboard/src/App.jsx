import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { ItemDrawer, useData } from "./components.jsx";
import { effortName, modelName } from "./format.js";
import { EventDetail, EventsPage, TrendDetail, TrendsPage } from "./events.jsx";
import { StudioList, StudioProject } from "./studio.jsx";
import { ComingSoon, ComparePage, ItemsPage, Overview, RunDetail, RunsPage, WatchlistPage } from "./pages.jsx";

const NAV = [
  { path: "overview", label: "Overview" },
  { path: "raw", label: "Raw Intelligence", count: (f) => f.raw },
  { path: "candidates", label: "Candidates", count: (f) => f.candidates },
  { path: "rejected", label: "Rejected", count: (f) => f.rejected },
  { path: "borderline", label: "Borderline" },
  { path: "events", label: "Events", count: (f) => f.events },
  { path: "trends", label: "Trends", count: (f) => f.trends },
  { path: "video-studio", label: "Video Studio" },
  { path: "runs", label: "Runs" },
  { path: "watchlist", label: "Watchlist" },
];

const SOON = [
  { path: "topics", label: "Topics", text: "研究、打分之后的每日选题，以及推荐的 Hook 和叙事角度（Phase 4–5）。" },
];

function useRoute() {
  const read = () => {
    const [path, query] = (window.location.hash.replace(/^#\/?/, "") || "overview").split("?");
    return { parts: path.split("/"), params: new URLSearchParams(query || "") };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export default function App() {
  const { parts, params } = useRoute();
  const [drawerId, setDrawerId] = useState(null);
  const [version, setVersion] = useState(0); // 抽屉里改了东西后，让列表和计数重新加载
  const meta = useData(() => api.meta(), []);
  const overview = useData(() => api.overview(), [version]);
  const closeDrawer = useCallback(() => setDrawerId(null), []);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    const item = params.get("item");
    if (item) setDrawerId(Number(item));
  }, [params]);

  const page = parts[0];
  const funnel = overview.data?.funnel;
  const config = meta.data?.config;
  const soon = SOON.find((s) => s.path === page);

  let content;
  if (!meta.data) content = <div className="empty">{meta.error ? `无法连接后端：${meta.error}` : "加载中…"}</div>;
  else if (page === "overview") content = <Overview version={version} />;
  else if (["raw", "candidates", "rejected", "borderline"].includes(page))
    content = <ItemsPage view={page} meta={meta.data} version={version} openItem={setDrawerId} />;
  else if (page === "runs" && parts[1] === "compare")
    content = <ComparePage a={params.get("a")} b={params.get("b")} openItem={setDrawerId} />;
  else if (page === "runs" && parts[1]) content = <RunDetail id={parts[1]} openItem={setDrawerId} />;
  else if (page === "runs") content = <RunsPage />;
  else if (page === "events" && parts[1]) content = <EventDetail id={parts[1]} openItem={setDrawerId} version={version} />;
  else if (page === "events") content = <EventsPage openItem={setDrawerId} version={version} />;
  else if (page === "trends" && parts[1]) content = <TrendDetail id={parts[1]} openItem={setDrawerId} />;
  else if (page === "trends") content = <TrendsPage />;
  else if (page === "video-studio" && parts[1]) content = <StudioProject key={parts[1]} id={parts[1]} />;
  else if (page === "video-studio") content = <StudioList />;
  else if (page === "watchlist") content = <WatchlistPage version={version} openItem={setDrawerId} />;
  else if (soon) content = <ComingSoon title={soon.label} text={soon.text} />;
  else content = <div className="empty">页面不存在。</div>;

  return (
    <div className="app">
      <nav className="sidebar">
        <a className="brand" href="#/overview">
          <span className="brand-mark" aria-hidden="true" />
          <span>Trend Radar<small>AI 媒体编辑工作台</small></span>
        </a>
        <ul>
          {NAV.map((n) => (
            <li key={n.path}>
              <a href={`#/${n.path}`} className={page === n.path ? "active" : ""}>
                <span>{n.label}</span>
                {n.count && funnel && n.count(funnel) != null && <span className="nav-count">{n.count(funnel)}</span>}
              </a>
            </li>
          ))}
        </ul>
        <div className="nav-section">Coming Soon</div>
        <ul>
          {SOON.map((n) => (
            <li key={n.path}><a href={`#/${n.path}`} className={`soon ${page === n.path ? "active" : ""}`}><span>{n.label}</span></a></li>
          ))}
        </ul>
        {config && (
          <div className="sidebar-config" title="只读。模型在项目的 .env 文件里配置。">
            <div className="stat-label">当前配置（.env）</div>
            <b>{modelName(config.model)}</b>
            <span>Reasoning · {effortName(config.reasoning_effort)}</span>
            <span>{config.runner}</span>
          </div>
        )}
      </nav>
      <main className="main">{content}</main>
      {drawerId != null && <ItemDrawer id={drawerId} onClose={closeDrawer} onChange={bump} />}
    </div>
  );
}
