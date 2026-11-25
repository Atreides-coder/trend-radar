"""用项目内的 last30days 检索公开讨论，只向子进程传递检索标题。"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

from .project import ROOT

VERSION = "4.6.0"
INSTALL = ROOT / ".tools" / "last30days"
PLATFORMS = ("hackernews", "github")


def public_query(event_title: str, sources: list[dict]) -> str:
    title = event_title.strip()
    if not title or re.search(r"[\u3400-\u9fff]", title):
        for source in sources:  # 事件来源已按主报道优先排序
            original = source.get("title") or ""
            if re.search(r"[A-Za-z]{2}", original) and not re.search(r"[\u3400-\u9fff]", original):
                title = original
                break
    if not title and sources:
        title = sources[0].get("title") or ""
    return " ".join(title.split()[:12])[:120].strip()


def _read_export(data: dict) -> tuple[list[dict], dict, bool]:
    """v1 agent JSON 支持单主题以及比较报告的 reports 信封。"""
    if str(data.get("schema_version", "")).split(".")[0] != "1":
        raise ValueError("不支持的 JSON 版本")
    reports = [entry["report"] for entry in data["reports"]] if data.get("comparison") else [data]
    if not reports:
        raise ValueError("报告中没有主题")
    items = []
    seen = set()
    outcomes = {}
    degraded = False
    for report in reports:
        for platform in PLATFORMS:
            state = report["source_status"].get(platform, "unknown")
            degraded |= state not in ("ok", "no-results")
            previous = outcomes.get(platform)
            if previous is None or previous == state:
                outcomes[platform] = state
            elif {previous, state} == {"ok", "no-results"}:
                outcomes[platform] = "ok"
            else:
                outcomes[platform] = "partial"
        for row in report["results"]:
            url = row.get("url") or ""
            parsed = urlsplit(url)
            title = (row.get("title") or "").strip()
            platform = row.get("source")
            if (not title or platform not in PLATFORMS or parsed.scheme not in ("http", "https")
                    or not parsed.hostname or parsed.username or parsed.password or url in seen):
                continue
            seen.add(url)
            counters = {k: v for k, v in (row.get("engagement") or {}).items() if type(v) in (float, int)}
            item = {"title": title[:300], "url": url, "platform": platform,
                    "date": row.get("published_at") or "", "engagement": counters}
            summary = " ".join((row.get("summary") or "").split())
            if summary and summary != title:
                item["summary"] = summary if len(summary) <= 350 else summary[:349].rstrip() + "…"
            items.append(item)
    return items[:12], outcomes, degraded


def collect(query: str, config: dict) -> dict:
    result = {"version": VERSION, "query": query, "window_days": 30, "items": [], "source_status": {}}

    def outcome(status: str, message: str) -> dict:
        return {**result, "status": status, "message": message}

    if not config.get("enabled", True):
        return outcome("disabled", "已关闭近 30 天社区线索。")
    if not query:
        return outcome("empty", "没有可检索的公开标题。")
    cli = INSTALL / "skills" / "last30days" / "scripts" / "last30days.py"
    if not cli.is_file() or sys.version_info < (3, 12):
        return outcome("unavailable", f"需要项目内的 last30days v{VERSION} 和 Python 3.12 或更高版本。")

    import tomllib

    try:
        with (INSTALL / "pyproject.toml").open("rb") as project:
            if tomllib.load(project)["project"]["version"] != VERSION:
                return outcome("unavailable", f"需要项目固定版本 last30days v{VERSION}。")
        # 空工作目录、独立用户目录及 PATH：只走匿名 HTTP，不继承账号、密钥或本地 CLI。
        with tempfile.TemporaryDirectory(prefix="trend-radar-last30days-") as temp:
            env = {"HOME": temp, "PATH": temp, "TMPDIR": temp, "LANG": "en_US.UTF-8",
                   "LAST30DAYS_CONFIG_DIR": "", "LAST30DAYS_SKIP_KEYCHAIN": "1",
                   "LAST30DAYS_SCHEDULED_RUN": "1"}
            proc = subprocess.run(
                [sys.executable, "-IBS", str(cli), "--research-only", "--no-research-persistence",
                 "--no-browser-cookies", "--search=" + ",".join(PLATFORMS), "--quick", "--days=30",
                 "--emit=json", "--json-profile=agent", "--", query],
                env=env, cwd=temp, capture_output=True, text=True, timeout=float(config.get("timeout_seconds", 75)))
        if proc.returncode:
            return outcome("failed", f"社区检索退出码 {proc.returncode}，研究将继续使用原有来源。")
        data = json.loads(proc.stdout)
        items, states, degraded = _read_export(data)
        result.update(items=items, source_status=states, generated_at=data.get("generated_at") or "")
    except subprocess.TimeoutExpired:
        return outcome("failed", "社区检索超时，研究将继续使用原有来源。")
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return outcome("failed", f"社区检索未完成（{type(exc).__name__}），研究将继续使用原有来源。")

    if items:
        return outcome("ok", "部分平台未完成检索，已保留可用线索。" if degraded else "")
    if degraded:
        return outcome("failed", "部分平台检索失败，暂未取得可追溯的讨论线索。")
    return outcome("empty", "最近 30 天未检索到带来源链接的匹配讨论。")
