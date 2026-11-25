"""Narrative + Script：Fact Pack → 10 个 Hook → 口播稿（script.json / script.md）。"""
from __future__ import annotations

import logging

from ..ai.base import AgentRunner
from .project import ROOT, Project
from .research import _arr, _obj

log = logging.getLogger("trend_radar.video.writer")
_STR = {"type": "string"}
_INT = {"type": "integer"}

PURPOSES = ["hook", "background", "shift", "risk", "evidence", "meaning", "trend", "conclusion"]
ASSET_TYPES = ["official_ui", "article_screenshot", "web_screenshot", "screen_recording", "diagram", "text_only"]
BANNED_OPENERS = ["今天给大家介绍", "最近", "大家好", "你知道吗", "今天我们聊聊"]

SCENE_SCHEMA = _obj({
    "scene_id": _INT, "voice": _STR,
    "purpose": {"type": "string", "enum": PURPOSES},
    "visual_intent": _STR,
    "preferred_asset_type": {"type": "string", "enum": ASSET_TYPES},
    "duration_estimate": {"type": "number"},
    "fact_ids": _arr(_INT),
    "claim_type": {"type": "string", "enum": ["FACT", "INFERENCE", "PREDICTION", "NARRATION"]},
    "emphasis_words": _arr(_STR),
})
SCRIPT_SCHEMA = _obj({
    "title": _STR,
    "hooks": _arr(_obj({"text": _STR, "style": _STR})),
    "chosen_hook": _INT, "hook_reason": _STR,
    "narrative": _arr(_STR),
    "scenes": _arr(SCENE_SCHEMA),
})
REVISE_SCHEMA = _obj({"scenes": _arr(SCENE_SCHEMA), "what_changed": _STR})


def voice_chars(scenes: list[dict]) -> int:
    return sum(len(s["voice"]) for s in scenes)


def normalize(script: dict, pack: dict) -> dict:
    """重新编号；去掉不存在的 fact id 和口播里没出现的强调词。"""
    fact_ids = {f["id"] for f in pack.get("verified_facts", [])}
    for n, s in enumerate(script["scenes"], start=1):
        s["scene_id"] = n
        s["voice"] = s["voice"].strip()
        s["fact_ids"] = [i for i in s["fact_ids"] if i in fact_ids]
        s["emphasis_words"] = [w for w in s["emphasis_words"] if w and w in s["voice"]][:3]
    return script


def write_markdown(proj: Project, script: dict, pack: dict):
    facts = {f["id"]: f["claim"] for f in pack.get("verified_facts", [])}
    L = [f"# {script['title']}", "", f"口播约 {voice_chars(script['scenes'])} 字 · {len(script['scenes'])} 场", "",
         "## Hook 备选", ""]
    for n, h in enumerate(script["hooks"], start=1):
        L.append(f"{n}. {'**' if n == script['chosen_hook'] else ''}{h['text']}"
                 f"{'** ← 选用' if n == script['chosen_hook'] else ''}  _（{h['style']}）_")
    L += ["", f"选用理由：{script['hook_reason']}", "", "## 叙事", ""]
    L += [f"{n}. {step}" for n, step in enumerate(script["narrative"], start=1)]
    L += ["", "## 分场", ""]
    for s in script["scenes"]:
        L += [f"### {s['scene_id']}. {s['purpose']} · {s['claim_type']}", "", f"> {s['voice']}", "",
              f"- 画面：{s['visual_intent']}（{s['preferred_asset_type']}）"]
        if s["fact_ids"]:
            L += [f"- 依据：" + "；".join(f"[{i}] {facts.get(i, '')}" for i in s["fact_ids"])]
        L.append("")
    proj.path("script.md").write_text("\n".join(L), encoding="utf-8")


def save_script(proj: Project, script: dict) -> dict:
    pack = proj.read("fact_pack.json", {})
    script = normalize(script, pack)
    proj.write("script.json", script)
    write_markdown(proj, script, pack)
    return script


def run_script(proj: Project, runner: AgentRunner) -> dict:
    pack = proj.read("fact_pack.json")
    if not pack:
        raise RuntimeError("还没有 fact_pack.json，请先运行 research")
    prompt = (ROOT / "prompts" / "video_script.md").read_text(encoding="utf-8").strip()
    payload = {"angle": proj.state["angle"], "fact_pack": {k: v for k, v in pack.items() if k != "claim_types"}}
    script = runner.run(task="video_script", prompt=prompt, input_data=payload, schema=SCRIPT_SCHEMA)
    script["chosen_hook"] = min(max(script["chosen_hook"], 1), max(len(script["hooks"]), 1))
    script = save_script(proj, script)
    first = script["scenes"][0]["voice"]
    banned = [b for b in BANNED_OPENERS if first.startswith(b)]
    if banned:
        log.warning("Hook 用了禁用的开头：%s", banned)
    log.info("Script：%d 个 Hook 备选 / %d 场 / 约 %d 字", len(script["hooks"]), len(script["scenes"]),
             voice_chars(script["scenes"]))
    return {"hooks": len(script["hooks"]), "scenes": len(script["scenes"]), "chars": voice_chars(script["scenes"]),
            "banned_opener": bool(banned)}


def revise_length(proj: Project, runner: AgentRunner, measured_seconds: float, target_chars: int) -> dict:
    """配音实测时长不在 45–60 秒时，按真实语速让编剧改到目标字数。"""
    script, pack = proj.read("script.json"), proj.read("fact_pack.json", {})
    current = voice_chars(script["scenes"])
    prompt = (ROOT / "prompts" / "video_script.md").read_text(encoding="utf-8").strip() + f"""

## 这一次的任务：调整长度

下面的 `scenes` 是已经写好的口播稿。按真实配音实测，它现在是 {measured_seconds:.1f} 秒、{current} 个字，目标是 45–60 秒。
请把口播总长度改到大约 {target_chars} 个字（上下浮动 10 个字以内）。

- {'删掉最不重要的话，合并重复的意思；不要删 Hook、核心事实和结尾。' if target_chars < current else '补充一两句让故事更完整的话，只能用 fact_pack 里的内容。'}
- 保持原来的结构、语气和事实，不要引入新的事实。
- 返回完整的 `scenes`（全部场次，字段齐全），并在 `what_changed` 里用一句话说明改了什么。"""
    out = runner.run(task="video_script_revise", prompt=prompt,
                     input_data={"scenes": script["scenes"], "fact_pack": {k: v for k, v in pack.items() if k != "claim_types"}},
                     schema=REVISE_SCHEMA)
    script["scenes"] = out["scenes"]
    script.setdefault("revisions", []).append(
        {"reason": f"实测 {measured_seconds:.1f}s / {current} 字 → 目标 {target_chars} 字", "what_changed": out["what_changed"]})
    script = save_script(proj, script)
    log.info("改稿：%d 字 → %d 字（%s）", current, voice_chars(script["scenes"]), out["what_changed"])
    return script


def regenerate_scene(proj: Project, runner: AgentRunner, scene_id: int, instruction: str = "") -> dict:
    """人工干预：只重写某一场的口播，其余场次不动。"""
    script, pack = proj.read("script.json"), proj.read("fact_pack.json", {})
    prompt = (ROOT / "prompts" / "video_script.md").read_text(encoding="utf-8").strip() + f"""

## 这一次的任务：只重写第 {scene_id} 场

下面的 `scenes` 是完整的口播稿。只重写第 {scene_id} 场，让它更好；其余场次原样返回，一个字都不要改。
重写后的这一场要和前后场衔接自然，长度和原来接近，只能用 fact_pack 里的内容。
{f'编辑的要求：{instruction}' if instruction else ''}
返回完整的 `scenes`，并在 `what_changed` 里说明改了什么。"""
    out = runner.run(task="video_scene_rewrite", prompt=prompt,
                     input_data={"scenes": script["scenes"], "fact_pack": {k: v for k, v in pack.items() if k != "claim_types"}},
                     schema=REVISE_SCHEMA)
    new = {s["scene_id"]: s for s in out["scenes"]}
    script["scenes"] = [new.get(scene_id, s) if s["scene_id"] == scene_id else s for s in script["scenes"]]
    script.setdefault("revisions", []).append({"reason": f"重写第 {scene_id} 场：{instruction}", "what_changed": out["what_changed"]})
    return save_script(proj, script)
