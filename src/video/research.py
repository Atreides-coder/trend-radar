"""按需 Deep Research：只研究被选中做视频的 Event，产出 fact_pack.json。

读取 Event 已有来源的正文，再让 Codex 在有次数上限的联网搜索下核实和补充。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from ..ai.base import AgentRunner
from ..dedup import canonicalize_url
from . import last30days
from .project import ROOT, Project

log = logging.getLogger("trend_radar.video.research")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX_SOURCE_CHARS = 9000

_STR = {"type": "string"}
_IDS = {"type": "array", "items": {"type": "integer"}}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(item: dict) -> dict:
    return {"type": "array", "items": item}


FACT_PACK_SCHEMA = _obj({
    "topic": _STR, "core_change": _STR,
    "verified_facts": _arr(_obj({"id": {"type": "integer"}, "claim": _STR, "source_ids": _IDS})),
    "timeline": _arr(_obj({"date": _STR, "event": _STR, "source_ids": _IDS})),
    "key_numbers": _arr(_obj({"value": _STR, "meaning": _STR, "source_ids": _IDS})),
    "what_changed": _STR, "why_now": _STR, "why_it_matters": _STR, "ordinary_people_impact": _STR,
    "inferences": _arr(_obj({"text": _STR, "based_on_fact_ids": _IDS})),
    "limitations": _arr(_STR), "counterpoints": _arr(_STR),
    "predictions": _arr(_obj({"text": _STR, "basis": _STR})),
    "sources": _arr(_obj({"id": {"type": "integer"}, "title": _STR, "publisher": _STR, "url": _STR,
                          "type": {"type": "string", "enum": ["official", "independent_media", "community", "other"]},
                          "used_for": _STR})),
    "visual_leads": _arr(_obj({"url": _STR, "description": _STR})),
})

# 写进 fact_pack.json，提醒下游每个字段是哪一类说法
CLAIM_TYPES = {
    "verified_facts": "FACT", "timeline": "FACT", "key_numbers": "FACT", "what_changed": "FACT",
    "why_now": "INFERENCE", "why_it_matters": "INFERENCE", "ordinary_people_impact": "INFERENCE",
    "inferences": "INFERENCE", "predictions": "PREDICTION",
}


def fetch_article_text(url: str) -> str:
    """抓报道正文。失败返回空字符串——研究仍可以靠标题、摘要和联网搜索继续。"""
    try:
        resp = httpx.get(url, headers={"User-Agent": UA}, timeout=25, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("抓取正文失败 %s: %s", url, e)
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside", "form", "noscript", "figure"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in root.find_all(["h1", "h2", "p", "li", "blockquote"])]
    text = "\n".join(p for p in paras if len(p) > 30 or p.endswith(("?", ".")))
    return text[:MAX_SOURCE_CHARS]


def event_sources(event_id: int) -> list[dict]:
    uri = (ROOT / "data" / "trend_radar.db").as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT i.title, i.source, i.url, i.summary, i.published_at, ei.relationship, "
        "json_extract(i.metadata_json, '$.tier') tier FROM event_items ei "
        "JOIN raw_items i ON i.id = ei.raw_item_id WHERE ei.event_id = ? "
        "ORDER BY ei.relationship = 'primary' DESC, i.filter_score DESC", (event_id,)).fetchall()
    db.close()
    return [{"id": n, "title": r["title"], "publisher": r["source"], "url": r["url"],
             "is_official": r["tier"] == 1, "published_at": r["published_at"], "summary": r["summary"] or ""}
            for n, r in enumerate(rows, start=1)]


def refresh_community_leads(proj: Project, cfg: dict | None, sources: list[dict] | None = None) -> dict:
    """仅根据公开标题刷新线索；看板和研究步骤可同时读取上次完整结果。"""
    st = proj.state
    if sources is None and st.get("event_id"):
        try:
            sources = event_sources(st["event_id"])
        except sqlite3.Error as exc:
            log.warning("无法读取事件来源，将使用选题标题：%s", exc)
    title = (st.get("event") or {}).get("canonical_title") or st.get("title") or ""
    query = last30days.public_query(title, sources or [])
    attempted = datetime.now(timezone.utc).isoformat(timespec="seconds")
    leads = last30days.collect(query, (cfg or {}).get("video", {}).get("last30days", {}))
    leads.update(attempted_at=attempted, from_cache=False)
    destination = proj.path("research/last30days.json")
    if leads["status"] in ("ok", "empty") and query:
        leads["last_success_at"] = leads.get("generated_at") or attempted
    elif leads["status"] in ("failed", "unavailable") and destination.is_file():
        try:
            previous = proj.read("research/last30days.json")
        except (OSError, ValueError):
            previous = None
        if isinstance(previous, dict) and previous.get("query") == query:
            last_success = previous.get("last_success_at")
            if not last_success and previous.get("status") in ("ok", "empty"):
                last_success = previous.get("generated_at") or datetime.fromtimestamp(
                    destination.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            if last_success:
                leads["last_success_at"] = last_success
                if previous.get("items"):
                    leads.update(items=previous["items"], from_cache=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".last30days-") as temp:
        temporary = Path(temp) / destination.name
        temporary.write_text(json.dumps(leads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
    log.info("last30days：%s / %d 条社区线索 %s", leads["status"], len(leads["items"]), leads["message"])
    return leads


def run_research(proj: Project, runner: AgentRunner, cfg: dict | None = None) -> dict:
    st = proj.state
    sources = event_sources(st["event_id"]) if st.get("event_id") else []
    for s in sources:
        s["text"] = fetch_article_text(s["url"])
        log.info("来源 %d %s：正文 %d 字符", s["id"], s["publisher"], len(s["text"]))
    proj.write("research/source_texts.json", sources)

    leads = refresh_community_leads(proj, cfg, sources)

    prompt = (ROOT / "prompts" / "video_research.md").read_text(encoding="utf-8").strip()
    payload = {"topic": {"event": st["event"], "angle": st["angle"]}, "sources": sources}
    fresh_leads = [] if leads.get("from_cache") else leads["items"]
    if fresh_leads:
        payload["community_leads"] = fresh_leads
    pack = runner.run(task="video_research", prompt=prompt, input_data=payload,
                      schema=FACT_PACK_SCHEMA, web_search=True)

    # 只从讨论线索取得的 URL 不能单独证明事实；已实际抓到的事件原文仍可引用。
    lead_urls = {canonicalize_url(lead["url"]) for lead in fresh_leads}
    read_urls = {canonicalize_url(s["url"]) for s in sources if s["text"]}
    leads_only = lead_urls - read_urls
    community_ids = set()
    for source in pack["sources"]:
        if leads_only and canonicalize_url(source["url"]) in leads_only:
            community_ids.add(source["id"])
            source["type"] = "community"
    known = {s["id"] for s in pack["sources"]} - community_ids
    unsupported = []
    for f in pack["verified_facts"]:
        f["source_ids"] = [i for i in f["source_ids"] if i in known]
        if not f["source_ids"]:
            unsupported.append(f)
    if unsupported:
        log.warning("有 %d 条事实没有有效出处，已降级为推断", len(unsupported))
        pack["verified_facts"] = [f for f in pack["verified_facts"] if f["source_ids"]]
        pack["inferences"] += [{"text": f["claim"], "based_on_fact_ids": []} for f in unsupported]
        verified = {f["id"] for f in pack["verified_facts"]}
        for inference in pack["inferences"]:
            inference["based_on_fact_ids"] = [i for i in inference["based_on_fact_ids"] if i in verified]
    if community_ids:
        for field in ("timeline", "key_numbers"):
            retained = []
            for entry in pack[field]:
                if community_ids.intersection(entry["source_ids"]):
                    entry["source_ids"] = [i for i in entry["source_ids"] if i in known]
                    if not entry["source_ids"]:
                        continue
                retained.append(entry)
            pack[field] = retained
    pack["claim_types"] = CLAIM_TYPES
    proj.write("fact_pack.json", pack)
    log.info("Fact Pack：%d 条事实 / %d 条推断 / %d 条预测 / %d 个来源",
             len(pack["verified_facts"]), len(pack["inferences"]), len(pack["predictions"]), len(pack["sources"]))
    return {"facts": len(pack["verified_facts"]), "sources": len(pack["sources"]),
            "source_texts": sum(1 for s in sources if s["text"]),
            "community_leads": len(fresh_leads), "last30days_status": leads["status"]}
