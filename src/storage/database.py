"""SQLite 存储层。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..dedup import canonicalize_url, content_hash, url_hash
from ..fetchers.base import RawItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_type TEXT,
    external_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    canonical_url TEXT,
    url_hash TEXT,                 -- 跨来源相同链接的指纹
    author TEXT,
    published_at DATETIME,
    fetched_at DATETIME,           -- 首次抓到
    last_seen_at DATETIME,         -- 最近一次抓到
    seen_count INTEGER DEFAULT 1,
    engagement_score REAL,
    metadata_json TEXT,
    content_hash TEXT UNIQUE,
    prefilter_score REAL,
    llm_relevance_score REAL,
    status TEXT DEFAULT 'new',     -- new/filtered/candidate/clustered/researched/discarded
    -- Phase 2：筛选的最新状态（完整 LLM 输出在 filter_json，历史在 filter_evaluations）
    filter_stage TEXT,             -- prefilter / llm：是哪一层做的决定
    filter_score REAL,             -- Fast Filter 总分（代码计算，0-100）
    filter_reason TEXT,            -- 被拒原因；candidate 为 NULL
    filter_json TEXT,              -- Fast Filter 的完整输出
    filtered_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_raw_published ON raw_items(published_at);
CREATE INDEX IF NOT EXISTS idx_raw_status ON raw_items(status);
CREATE INDEX IF NOT EXISTS idx_raw_url_hash ON raw_items(url_hash);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date DATE,
    cluster_title TEXT,
    cluster_summary TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    item_count INTEGER,
    source_count INTEGER,
    importance_score REAL,
    trend_score REAL
);

CREATE TABLE IF NOT EXISTS cluster_items (
    cluster_id INTEGER,
    raw_item_id INTEGER,
    PRIMARY KEY (cluster_id, raw_item_id)
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER,
    topic_title TEXT,
    core_change TEXT,
    why_now TEXT,
    why_people_care TEXT,
    hook TEXT,
    narrative_angle TEXT,
    visual_potential TEXT,
    counterargument TEXT,
    risks TEXT,
    sources_json TEXT,
    relatedness_score REAL,
    story_score REAL,
    visual_score REAL,
    trend_score REAL,
    freshness_score REAL,
    credibility_score REAL,
    uniqueness_score REAL,
    total_score REAL,
    created_at DATETIME,
    -- 人工反馈（Phase 5 正式启用，之后作为 Editor 的 few-shot 样本）
    human_selected INTEGER,        -- 1 选了 / 0 没选
    human_rating INTEGER,          -- 1~5
    human_note TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_name TEXT,
    description TEXT,
    first_seen DATETIME,
    last_seen DATETIME,
    mention_count INTEGER,
    source_count INTEGER,
    trend_score REAL,
    status TEXT                    -- watching/rising/selected/cooling/dead
);

-- 每次运行、每个 source 的抓取结果，用于日志和最终报告里的 "xxx fetch failed"
CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at DATETIME,
    source TEXT,
    fetched INTEGER,
    inserted INTEGER,
    updated INTEGER,
    error TEXT
);

-- 每次 filter 阶段的运行记录（数量、token、成本）
CREATE TABLE IF NOT EXISTS filter_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at DATETIME,
    duration_seconds REAL,
    model TEXT,
    prompt_version TEXT,
    stats_json TEXT
);

-- 每条内容每次被 LLM 评估的完整记录。改 prompt 重跑后可以对比前后差异。
CREATE TABLE IF NOT EXISTS filter_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    raw_item_id INTEGER,
    model TEXT,
    prompt_version TEXT,
    change_signal INTEGER,
    ordinary_people INTEGER,
    story_potential INTEGER,
    trend_potential INTEGER,
    visual_potential INTEGER,
    score REAL,
    llm_keep INTEGER,
    reject_reason TEXT,
    result_json TEXT,
    created_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_eval_item ON filter_evaluations(raw_item_id);

-- ---------- Phase 3：Event / Trend ----------

-- 每次聚类运行（聚类 + Global Ranking + Trend Linking）
CREATE TABLE IF NOT EXISTS cluster_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at DATETIME,
    duration_seconds REAL,
    runner TEXT,
    model TEXT,
    reasoning_effort TEXT,
    prompt_version TEXT,           -- 三个 prompt 的版本，"cluster/rank/trend"
    input_signals INTEGER,
    output_events INTEGER,
    output_trends INTEGER,
    stats_json TEXT
);

-- Event：一个具体的现实事件。每次聚类运行生成一组新的 events（按 run_id 区分）。
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    canonical_title TEXT,
    summary TEXT,
    core_change TEXT,
    cluster_reason TEXT,           -- 为什么这些报道被合在一起
    first_seen DATETIME,
    last_seen DATETIME,
    item_count INTEGER,
    source_count INTEGER,
    independent_source_count INTEGER,  -- 独立报道的来源数；官方稿和转述不算
    has_official_source INTEGER,
    max_filter_score REAL,
    avg_filter_score REAL,
    -- Global Ranking
    rank INTEGER,
    score REAL,                    -- 由代码按维度权重计算
    audience_relevance INTEGER,
    change_magnitude INTEGER,
    story_potential INTEGER,
    trend_potential INTEGER,
    evidence_strength INTEGER,
    visual_potential INTEGER,
    why_it_matters TEXT,
    possible_bigger_trend TEXT,
    in_research_queue INTEGER DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME,
    status TEXT DEFAULT 'active'   -- active/watch/researched/discarded
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);

CREATE TABLE IF NOT EXISTS event_items (
    event_id INTEGER,
    raw_item_id INTEGER,
    relationship TEXT,             -- primary/duplicate_report/supporting/official_source/commentary
    independent INTEGER,           -- 是否算一个独立的报道来源
    PRIMARY KEY (event_id, raw_item_id)
);

-- Trend：跨多个 Event 的假设，跨天保留（Trend Memory）。
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT,
    description TEXT,              -- 最近一次的 hypothesis
    first_seen DATETIME,
    last_seen DATETIME,
    status TEXT DEFAULT 'watching',-- watching/rising/selected/cooling/dead
    confidence INTEGER,            -- 0~5，最近一次
    event_count INTEGER,           -- 以下三项为最近一次运行的统计
    mention_count INTEGER,
    source_count INTEGER,
    velocity REAL,                 -- 历史数据不足 7 天时保持 NULL
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS trend_events (
    trend_id INTEGER,
    event_id INTEGER,
    run_id INTEGER,
    confidence INTEGER,
    hypothesis TEXT,
    PRIMARY KEY (trend_id, event_id)
);

-- 同一个趋势的不同叫法都指向同一个 trend_id，避免跨天名称漂移
CREATE TABLE IF NOT EXISTS trend_aliases (
    trend_id INTEGER,
    alias TEXT,
    PRIMARY KEY (trend_id, alias)
);
"""

# 旧数据库升级：表已存在时 CREATE TABLE IF NOT EXISTS 不会加新列，这里补上
MIGRATIONS = {
    "raw_items": {
        "filter_stage": "TEXT", "filter_score": "REAL", "filter_reason": "TEXT",
        "filter_json": "TEXT", "filtered_at": "DATETIME",
        # 人工反馈（Dashboard 写入，以后用于调 prompt）
        "human_status": "TEXT",        # NULL / interested / not_interested / watch / strong_topic
        "human_note": "TEXT",
        "human_updated_at": "DATETIME",
        "human_override": "TEXT",      # restored：人工恢复为 candidate，筛选不会再把它降级
    },
    "filter_runs": {"runner": "TEXT", "reasoning_effort": "TEXT", "prompt_text": "TEXT"},
    # selected / final_reason：这条内容在这次运行里的最终结果，用于 run 之间对比
    "filter_evaluations": {"reasoning_effort": "TEXT", "selected": "INTEGER", "final_reason": "TEXT"},
    "topics": {"human_selected": "INTEGER", "human_rating": "INTEGER", "human_note": "TEXT"},
}


def fmt_dt(dt: datetime | None) -> str | None:
    """统一存 UTC 的 'YYYY-MM-DD HH:MM:SS'，SQLite 的 datetime() 能直接比较。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def latest_filter_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """最近一次成功的实际筛选；即使所有条目都已评估，也会产生新的分析窗口。"""
    return conn.execute("""
        SELECT r.* FROM filter_runs r
        WHERE json_extract(stats_json, '$.status') = 'complete'
           OR (json_extract(stats_json, '$.status') IS NULL AND duration_seconds IS NOT NULL
               AND json_extract(stats_json, '$.note') IS NULL
               AND coalesce(json_extract(stats_json, '$.fast_filter.skipped_items'), 0) = 0
               AND (json_type(stats_json, '$.fast_filter') = 'object'
                    OR EXISTS (SELECT 1 FROM filter_evaluations e WHERE e.run_id = r.id)))
        ORDER BY r.id DESC LIMIT 1
    """).fetchone()


def filter_window_start(conn: sqlite3.Connection, default_days: int) -> str:
    run = latest_filter_run(conn)
    if run:
        base = datetime.fromisoformat(run["started_at"])
        days = json.loads(run["stats_json"] or "{}").get("window_days", default_days)
    else:
        base = datetime.now(timezone.utc)
        days = default_days
    return fmt_dt(base - timedelta(days=days))


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        for table, columns in MIGRATIONS.items():
            existing = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, col_type in columns.items():
                if name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def upsert_items(self, items: list[RawItem], now: datetime) -> tuple[int, int]:
        """写入 raw_items。返回 (新增数, 更新数)。

        重复条目不丢弃而是更新 engagement / last_seen_at——HN 分数和 GitHub star
        会随时间涨，这是后面算趋势速度需要的。
        """
        inserted = updated = 0
        now_s = fmt_dt(now)
        for it in items:
            canon = canonicalize_url(it.url)
            chash = content_hash(it.source, it.title, canon)
            meta = json.dumps(it.metadata, ensure_ascii=False)
            cur = self.conn.execute(
                """UPDATE raw_items
                   SET engagement_score = ?, metadata_json = ?, last_seen_at = ?,
                       seen_count = seen_count + 1
                   WHERE content_hash = ?""",
                (it.engagement_score, meta, now_s, chash),
            )
            if cur.rowcount:
                updated += 1
                continue
            self.conn.execute(
                """INSERT INTO raw_items
                   (source, source_type, external_id, title, summary, url, canonical_url,
                    url_hash, author, published_at, fetched_at, last_seen_at,
                    engagement_score, metadata_json, content_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    it.source, it.source_type, it.external_id, it.title.strip(), it.summary,
                    it.url, canon, url_hash(canon), it.author,
                    fmt_dt(it.published_at) or now_s, now_s, now_s,
                    it.engagement_score, meta, chash,
                ),
            )
            inserted += 1
        self.conn.commit()
        return inserted, updated

    def log_fetch_run(self, now: datetime, source: str, fetched: int, inserted: int,
                      updated: int, error: str | None):
        self.conn.execute(
            "INSERT INTO fetch_runs (run_at, source, fetched, inserted, updated, error) "
            "VALUES (?,?,?,?,?,?)",
            (fmt_dt(now), source, fetched, inserted, updated, error),
        )
        self.conn.commit()
