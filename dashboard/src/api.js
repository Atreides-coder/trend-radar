async function request(path, options) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败（${res.status}）`);
  }
  return res.json();
}

const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

export const api = {
  meta: () => request("/meta"),
  overview: () => request("/overview"),
  // 去掉空值，避免把 "" 当成参数发给后端
  items: (params) =>
    request(`/items?${new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null))}`),
  item: (id) => request(`/items/${id}`),
  feedback: (id, body) => post(`/items/${id}/feedback`, body),
  restore: (id) => post(`/items/${id}/restore`),
  unrestore: (id) => post(`/items/${id}/unrestore`),
  runs: () => request("/runs"),
  run: (id) => request(`/runs/${id}`),
  compare: (a, b) => request(`/runs/compare?a=${a}&b=${b}`),
  watchlist: () => request("/watchlist"),
  events: () => request("/events"),
  event: (id) => request(`/events/${id}`),
  trends: () => request("/trends"),
  trend: (id) => request(`/trends/${id}`),
  clusterRuns: () => request("/cluster-runs"),
  videoProjects: () => request("/video-projects"),
  videoProject: (id) => request(`/video-projects/${id}`),
  refreshCommunityLeads: (id) => post(`/video-projects/${id}/community-leads`),
  createVideo: (body) => post("/video-projects", body),
  runVideo: (id, steps) => post(`/video-projects/${id}/run`, { steps }),
  editScript: (id, scenes) =>
    request(`/video-projects/${id}/script`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenes }) }),
  regenScene: (id, sceneId, instruction) => post(`/video-projects/${id}/scenes/${sceneId}/regenerate`, { instruction }),
  replaceAsset: (id, body) => post(`/video-projects/${id}/replace-asset`, body),
  uploadAsset: (id, file, mode = "import") => {
    const form = new FormData();
    form.append("file", file);
    form.append("mode", mode);
    return request(`/video-projects/${id}/assets`, { method: "POST", body: form });
  },
};
