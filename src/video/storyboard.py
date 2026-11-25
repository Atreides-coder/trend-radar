"""Storyboard：为每一场决定镜头、组件和素材；把镜头对到真实的配音时间上。

模型负责"看什么"，Python 负责"什么时候看"和"框哪里"：
  - at_text → 用逐词时间轴换算成镜头的起止时间
  - highlight_text → 用 OCR 的行位置换算成截图上的高亮区域
"""
from __future__ import annotations

import difflib
import logging
import re

from ..ai.base import AgentRunner
from .project import ROOT, Project
from .research import _arr, _obj

log = logging.getLogger("trend_radar.video.storyboard")
_STR = {"type": "string"}

COMPONENTS = {
    "HookScene": "开场大字。headline 是画面中央的大字。可以选一个真实素材作为压暗的背景（填 asset_id），也可以不用。",
    "RealMediaScene": "真实图片或 AutoClip 视频占据画面主体。视频按原速静音播放，按镜头长度截取或循环。需要 asset_id。",
    "BrowserScreenshotScene": "网页截图放在浏览器外框里，显示域名；滚动到 highlight_text 并高亮它。"
                              "用于报道页面和官方页面（article_screenshot / web_screenshot）。需要 asset_id。",
    "PhoneOrDesktopScene": "系统或应用的真实界面放在桌面窗口外框里；推近到 highlight_text 并高亮它。"
                           "用于 official_ui。需要 asset_id。",
    "DataScene": "一个大数字或关键词加一行说明。用 data。",
    "ConceptDiagramScene": "解释概念的图解动画：compare / flow / grid。用 diagram。",
    "QuoteScene": "一句引语加出处。用 quote。",
    "ConclusionScene": "结尾。headline 是结论或留给观众的问题，sub 是补充的一行。",
}
REAL_COMPONENTS = {"RealMediaScene", "BrowserScreenshotScene", "PhoneOrDesktopScene"}
NEEDS_ASSET = REAL_COMPONENTS
MIN_SHOT_SECONDS = 1.3

SHOT_SCHEMA = _obj({
    "component": {"type": "string", "enum": list(COMPONENTS)},
    "asset_id": _STR, "at_text": _STR, "highlight_text": _STR, "headline": _STR, "sub": _STR,
    "diagram": _obj({"kind": {"type": "string", "enum": ["none", "compare", "flow", "grid"]}, "title": _STR,
                     "left_label": _STR, "left_items": _arr(_STR), "right_label": _STR, "right_items": _arr(_STR),
                     "steps": _arr(_STR)}),
    "quote": _obj({"text": _STR, "attribution": _STR}),
    "data": _obj({"value": _STR, "label": _STR}),
    "reason": _STR,
})
STORYBOARD_SCHEMA = _obj({"scenes": _arr(_obj({"scene_id": {"type": "integer"}, "shots": _arr(SHOT_SCHEMA)}))})


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def locate_text(lines: list[dict], snippet: str) -> dict | None:
    """在 OCR 行里找 snippet，返回覆盖它的那几行的包围盒（0~1）。找不到返回 None。"""
    target = _norm(snippet)
    if not target or not lines:
        return None
    joined, owner = "", []
    for idx, line in enumerate(lines):
        t = _norm(line["text"])
        joined += t
        owner += [idx] * len(t)
    pos = joined.find(target)
    if pos < 0:   # OCR 和模型抄写可能差一两个字符：找最长的公共片段
        m = difflib.SequenceMatcher(None, joined, target, autojunk=False).find_longest_match(0, len(joined), 0, len(target))
        if m.size < max(6, len(target) * 0.5):
            return None
        pos, length = m.a, m.size
    else:
        length = len(target)
    hit = [lines[i] for i in sorted(set(owner[pos:pos + length]))]
    x0, y0 = min(h["x"] for h in hit), min(h["y"] for h in hit)
    x1, y1 = max(h["x"] + h["w"] for h in hit), max(h["y"] + h["h"] for h in hit)
    return {"x": round(x0, 4), "y": round(y0, 4), "w": round(x1 - x0, 4), "h": round(y1 - y0, 4)}


def time_of_text(scene_voice: str, words: list[dict], at_text: str) -> float | None:
    """at_text 在这一场口播里出现的位置 → 对应的那个词开始的时间。"""
    pos = scene_voice.find(at_text.strip()) if at_text.strip() else -1
    if pos < 0:
        return None
    cursor = 0
    for w in words:
        p = scene_voice.find(w["text"], cursor)
        if p < 0:
            continue
        cursor = p + len(w["text"])
        if cursor > pos:
            return w["start"]
    return None


def run_storyboard(proj: Project, runner: AgentRunner) -> dict:
    script, timings = proj.read("script.json"), proj.read("audio/timings.json")
    library = proj.read("assets/library.json", [])
    if not script or not timings:
        raise RuntimeError("需要先有 script.json 和 audio/timings.json")
    assets = {a["id"]: a for a in library}
    tmap = {t["scene_id"]: t for t in timings["scenes"]}
    order = [t["scene_id"] for t in timings["scenes"]]
    # 每一场一直持续到下一场开始，画面不留空档
    bounds = {sid: (tmap[sid]["start"], tmap[order[i + 1]]["start"] if i + 1 < len(order) else timings["duration"])
              for i, sid in enumerate(order)}

    payload = {
        "scenes": [{"scene_id": s["scene_id"], "voice": s["voice"], "purpose": s["purpose"],
                    "visual_intent": s["visual_intent"], "preferred_asset_type": s["preferred_asset_type"],
                    "seconds": round(bounds[s["scene_id"]][1] - bounds[s["scene_id"]][0], 1)} for s in script["scenes"]],
        "assets": [{k: a[k] for k in ("id", "type", "source", "description", "duration", "text_on_image") if k in a} for a in library],
        "components": COMPONENTS,
    }
    prompt = (ROOT / "prompts" / "video_storyboard.md").read_text(encoding="utf-8").strip()
    out = runner.run(task="video_storyboard", prompt=prompt, input_data=payload, schema=STORYBOARD_SCHEMA)
    by_id = {s["scene_id"]: s for s in out["scenes"]}

    scenes, notes = [], []
    for s in script["scenes"]:
        sid = s["scene_id"]
        start, end = bounds[sid]
        shots = []
        for shot in (by_id.get(sid) or {}).get("shots", []):
            asset = assets.get(shot["asset_id"])
            if asset and asset["type"] == "autoclip_video":
                if shot["component"] not in ("HookScene", "ConclusionScene"):
                    shot["component"] = "RealMediaScene"
                shot["highlight_text"] = ""
            if shot["component"] in NEEDS_ASSET and not asset:
                notes.append(f"第 {sid} 场：{shot['component']} 没有可用素材（{shot['asset_id'] or '空'}），已丢弃这个镜头")
                continue
            highlight = None
            if asset and shot["highlight_text"]:
                highlight = locate_text(proj.read(f"assets/ocr/{asset['id']}.json", []), shot["highlight_text"])
                if not highlight:
                    notes.append(f"第 {sid} 场：在 {asset['id']} 上没找到「{shot['highlight_text'][:20]}」，不做高亮")
            at = time_of_text(s["voice"], tmap[sid]["words"], shot["at_text"]) if shots else start
            shots.append({**shot, "asset": asset, "highlight": highlight,
                          "start": start if not shots or at is None else max(start, at - 0.12), "_anchored": at is not None})
        if not shots:   # 模型没给出可用镜头：退回成只有大字，保证这一场不是空画面
            shots = [{"component": "HookScene" if s["purpose"] == "hook" else "ConclusionScene", "asset": None,
                      "asset_id": "", "headline": "".join(s.get("emphasis_words", [])[:1]) or s["voice"][:10], "sub": "",
                      "highlight": None, "diagram": {"kind": "none"}, "quote": {"text": ""}, "data": {"value": ""},
                      "reason": "自动兜底", "start": start, "_anchored": True, "at_text": "", "highlight_text": ""}]
            notes.append(f"第 {sid} 场：没有可用镜头，已用大字兜底")
        # 没对上口播的镜头：平均分配时间
        for i, shot in enumerate(shots):
            if not shot.pop("_anchored") and i > 0:
                shot["start"] = start + (end - start) * i / len(shots)
        shots.sort(key=lambda x: x["start"])
        # 太短的镜头并到前一个
        kept = [shots[0]]
        for shot in shots[1:]:
            if shot["start"] - kept[-1]["start"] < MIN_SHOT_SECONDS or end - shot["start"] < MIN_SHOT_SECONDS:
                notes.append(f"第 {sid} 场：一个镜头不足 {MIN_SHOT_SECONDS}s，已合并")
            else:
                kept.append(shot)
        for i, shot in enumerate(kept):
            shot["start"] = round(shot["start"], 3)
            shot["end"] = round(kept[i + 1]["start"] if i + 1 < len(kept) else end, 3)
        scenes.append({"scene_id": sid, "start": round(start, 3), "end": round(end, 3), "purpose": s["purpose"],
                       "voice": s["voice"], "shots": kept})

    stats = save_storyboard(proj, {"duration": timings["duration"], "scenes": scenes, "notes": notes})
    for n in notes:
        log.warning(n)
    log.info("Storyboard：%d 个镜头，真实素材 %.0f%%，平均 %.1fs/镜头，最长 %.1fs",
             stats["shots"], stats["real_ratio"] * 100, stats["avg_shot"], stats["longest_shot"])
    return {**stats, "notes": len(notes)}


def save_storyboard(proj: Project, board: dict) -> dict:
    """在自动分镜或人工换素材后同步保存镜头、时长统计和素材出处。"""
    scenes = board["scenes"]
    all_shots = [sh for sc in scenes for sh in sc["shots"]]
    real = sum(sh["end"] - sh["start"] for sh in all_shots if sh["component"] in REAL_COMPONENTS)
    total = board["duration"]
    stats = {"shots": len(all_shots), "real_seconds": round(real, 1), "real_ratio": round(real / total, 2),
             "longest_shot": round(max(sh["end"] - sh["start"] for sh in all_shots), 1),
             "avg_shot": round(total / len(all_shots), 1)}
    board["stats"] = stats
    proj.write("storyboard.json", board)

    # assets.json：每一场用了哪些素材、为什么
    proj.write("assets.json", [{
        "scene_id": sc["scene_id"],
        "assets": [{"type": sh["asset"]["type"], "path": sh["asset"]["path"], "source": sh["asset"]["source"],
                    "license_or_usage_note": sh["asset"]["license_or_usage_note"], "reason": sh["reason"]}
                   if sh["asset"] else
                   {"type": "remotion_animation", "path": "", "source": sh["component"],
                    "license_or_usage_note": "代码生成的动画，无第三方素材。", "reason": sh["reason"]}
                   for sh in sc["shots"]],
    } for sc in scenes])
    return stats
