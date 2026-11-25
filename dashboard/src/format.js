export const DIMS = [
  { key: "change_signal", label: "Change Signal", zh: "变化信号", weight: 5 },
  { key: "ordinary_people", label: "People Relevance", zh: "普通人关联", weight: 5 },
  { key: "story_potential", label: "Story Potential", zh: "故事潜力", weight: 4 },
  { key: "trend_potential", label: "Trend Potential", zh: "趋势潜力", weight: 4 },
  { key: "visual_potential", label: "Visual Potential", zh: "视觉潜力", weight: 2 },
];

export const EVENT_DIMS = [
  { key: "audience_relevance", label: "Audience Relevance", zh: "观众关联", weight: 5 },
  { key: "change_magnitude", label: "Change Magnitude", zh: "变化幅度", weight: 4 },
  { key: "story_potential", label: "Story Potential", zh: "故事潜力", weight: 4 },
  { key: "trend_potential", label: "Trend Potential", zh: "趋势潜力", weight: 3 },
  { key: "evidence_strength", label: "Evidence Strength", zh: "证据强度", weight: 2 },
  { key: "visual_potential", label: "Visual Potential", zh: "视觉潜力", weight: 2 },
];

export const RELATIONSHIPS = {
  primary: "主报道",
  official_source: "官方来源",
  supporting: "补充信息",
  duplicate_report: "重复报道",
  commentary: "评论 / 讨论",
};

export const TREND_STATUS = { watching: "Watching", rising: "Rising", selected: "Selected", cooling: "Cooling", dead: "Dead" };

export const REASONS = {
  not_a_change: "不是变化",
  isolated_event: "孤立事件",
  low_people_relevance: "与观众关联低",
  low_story_potential: "故事性弱",
  minor_update: "小更新",
  pure_technical: "纯技术",
  promotion: "宣传 / 广告",
  old_information: "旧信息",
  below_threshold: "分数未过线",
  over_max_candidates: "过线但超出名额",
  human_restored: "人工恢复",
  event_promo: "活动宣传",
  podcast_newsletter: "播客 / Newsletter",
  job_post: "招聘",
  tutorial: "教程",
  security_cve: "安全 CVE",
};

export const STATUS = {
  new: "待评估",
  discarded: "规则过滤",
  filtered: "未入选",
  candidate: "Candidate",
  clustered: "已聚类",
  researched: "已研究",
};

export const HUMAN = [
  { key: "interested", icon: "👍", label: "Interested" },
  { key: "not_interested", icon: "👎", label: "Not Interested" },
  { key: "watch", icon: "👁", label: "Watch" },
  { key: "strong_topic", icon: "★", label: "Strong Topic" },
];

export const reasonLabel = (code) => REASONS[code] || code || "";

// 数据库里存的是 UTC "YYYY-MM-DD HH:MM:SS"
const parse = (s) => (s ? new Date(s.replace(" ", "T") + "Z") : null);

export function fmtDate(s) {
  const d = parse(s);
  if (!d) return "—";
  return d.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function fmtDay(s) {
  const d = parse(s);
  return d ? d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }) : "—";
}

export const fmtNum = (n) => (n == null ? "—" : Number(n).toLocaleString("en-US"));

export function fmtDuration(sec) {
  if (sec == null) return "—";
  if (sec < 60) return `${Math.round(sec)} 秒`;
  return `${Math.floor(sec / 60)} 分 ${Math.round(sec % 60)} 秒`;
}

// "gpt-6.1-sol" → "GPT-6.1 Sol"
export function modelName(slug) {
  if (!slug) return "—";
  const [head, version, ...rest] = slug.split("-");
  const tail = rest.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  return `${head.toUpperCase()}${version ? "-" + version : ""}${tail ? " " + tail : ""}`;
}

export const effortName = (e) => (e ? e.charAt(0).toUpperCase() + e.slice(1) : "—");

export const runLabel = (r) => `Run ${r.id} · ${modelName(r.model)} ${effortName(r.reasoning_effort)}`;
