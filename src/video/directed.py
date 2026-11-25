"""Directed video：分镜由人（或导演方案）逐个镜头定好，这里只负责把它做出来。

和自动 pipeline 的区别：自动 pipeline 让模型在通用组件里挑；directed 是每条视频一个专门的 Remotion composition，
镜头时间仍然全部来自真实配音。

    python -m src.video.directed build apple-agent-permissions-v2            # 配音 + 对时 + 渲染 + QC
    python -m src.video.directed build apple-agent-permissions-v2 --skip-voice  # 只改了画面时用
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys

import yaml

from .project import ROOT, Project
from .render import REMOTION_DIR, run
from .storyboard import locate_text
from .voice import EdgeTTSProvider, build_captions, ffmpeg, synthesize_all

log = logging.getLogger("trend_radar.video.directed")
GAP, TAIL = 0.05, 0.08   # 镜头之间只留很短的气口，节奏更紧


def synthesize(proj: Project, spec: dict, voice: str) -> dict:
    """逐个镜头合成配音并拼接。没有旁白的镜头按 silent_seconds 留出静音。"""
    provider = EdgeTTSProvider(voice=voice, rate=spec.get("tts_rate", "+8%"))
    scenes = [{"scene_id": s["id"], "voice": s["voice"], "silent_seconds": s.get("silent_seconds", 2.0)}
              for s in spec["shots"]]
    return synthesize_all(proj, provider, scenes, GAP, TAIL, layout="shots", ending=0.8)


def make_sfx(proj: Project):
    """自己合成的几个简单音效（不涉及第三方素材）：点击、按键、转场、落点。"""
    out = lambda name: str(proj.path("audio", "sfx", name))  # noqa: E731
    ffmpeg("-f", "lavfi", "-i", "sine=f=1900:d=0.045", "-f", "lavfi", "-i", "anoisesrc=d=0.045:c=white:a=0.5",
           "-filter_complex", "[0][1]amix=inputs=2,afade=t=out:st=0.004:d=0.04,highpass=f=900,volume=1.6", out("click.wav"))
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=0.03:c=white:a=0.4", "-af", "afade=t=out:st=0.002:d=0.028,highpass=f=2500,volume=0.9", out("key.wav"))
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=0.42:c=pink:a=0.6", "-af",
           "afade=t=in:st=0:d=0.2,afade=t=out:st=0.22:d=0.2,highpass=f=500,lowpass=f=5000,volume=0.9", out("whoosh.wav"))
    ffmpeg("-f", "lavfi", "-i", "sine=f=62:d=0.5", "-af", "afade=t=in:st=0:d=0.01,afade=t=out:st=0.05:d=0.45,volume=2.2", out("hit.wav"))


def build_props(proj: Project, spec: dict, timings: dict, captions: list[dict]) -> dict:
    order = [t["scene_id"] for t in timings["scenes"]]
    tmap = {t["scene_id"]: t for t in timings["scenes"]}
    shots = []
    for i, sid in enumerate(order):
        start = tmap[sid]["start"]
        end = tmap[order[i + 1]]["start"] if i + 1 < len(order) else timings["duration"]
        meta = next(s for s in spec["shots"] if s["id"] == sid)
        shots.append({"id": sid, "start": round(start, 3), "end": round(end, 3), "voice": meta["voice"],
                      "words": tmap[sid]["words"]})

    def box(asset: str, snippet: str):
        b = locate_text(proj.read(f"assets/ocr/{asset}.json", []), snippet)
        if not b:
            log.warning("在 %s 上没找到「%s」", asset, snippet)
        return b

    demo = [json.loads(line) for line in (proj.dir / "capture" / "agent_events.jsonl").read_text(encoding="utf-8").splitlines()]
    pack = proj.read("fact_pack.json", {})
    return {
        "duration": timings["duration"], "shots": shots, "captions": captions,
        "demo": {
            "steps": [e["step"] for e in demo if e.get("label")][-1],
            "task": "整理这个文件夹，找出本周要跟进的事，给王经理写一封跟进邮件。",
            "files": ["会议纪要.md", "聊天记录导出.txt", "客户名单.csv", "合同草稿.txt", "待办.md"],
            "email": (proj.dir / "demo_workspace" / "邮件草稿.txt").read_text(encoding="utf-8")[:420],
            "todo": (proj.dir / "demo_workspace" / "待办.md").read_text(encoding="utf-8")[:330],
        },
        "boxes": {
            "ars_user": box("source_1_page", "Aten said he never granted Muse permissions to read his messages"),
            "ars_meta": box("source_1_page", "Your Muse can only read Messages content if macOS system-level Full Disk Access is granted"),
            "apple_title": box("source_3_page", "Updates to Full Disk Access in macOS"),
            "apple_date": box("source_3_page", "October 2, 2026"),
            "apple_explicit": box("source_3_page", "do so with very explicit user action"),
            "apple_agents": box("source_3_page", "As AI agents become increasingly capable and autonomous"),
        },
        "sources": list(dict.fromkeys(s["publisher"] for s in pack.get("sources", [])))[:3],
    }


def write_studio_files(proj: Project, spec: dict, props: dict):
    """写出和自动 pipeline 相同结构的 script / storyboard，Video Studio 和 QC 可以直接读。"""
    scenes = [{"scene_id": s["id"], "voice": s["voice"], "purpose": s["purpose"], "visual_intent": s["why"],
               "preferred_asset_type": "screen_recording" if s["real"] else "diagram", "duration_estimate": 0,
               "fact_ids": s["fact_ids"], "claim_type": s["claim_type"], "emphasis_words": []} for s in spec["shots"]]
    proj.write("script.json", {"title": spec["title"], "hooks": [{"text": spec["shots"][0]["voice"] + spec["shots"][1]["voice"],
                                                                    "style": "方案 B：一次允许，后面的每一步（见 creative_direction.md）"}],
                               "chosen_hook": 1, "hook_reason": "前 3 秒就把观点本身演出来。", "narrative": [], "scenes": scenes})
    board = []
    for s, p in zip(spec["shots"], props["shots"]):
        board.append({"scene_id": s["id"], "start": p["start"], "end": p["end"], "purpose": s["purpose"], "voice": s["voice"],
                      "shots": [{"component": "PhoneOrDesktopScene" if s["real"] else "ConceptDiagramScene", "asset": None,
                                 "asset_id": "", "start": p["start"], "end": p["end"], "headline": s["lang"], "sub": "",
                                 "highlight": None, "highlight_text": "", "diagram": {"kind": "none"}, "reason": s["why"]}]})
    lengths = [b["end"] - b["start"] for b in board]
    real = sum(n for n, s in zip(lengths, spec["shots"]) if s["real"])
    proj.write("storyboard.json", {"duration": props["duration"], "scenes": board, "notes": [],
                                   "stats": {"shots": len(board), "real_seconds": round(real, 1),
                                             "real_ratio": round(real / props["duration"], 2),
                                             "longest_shot": round(max(lengths), 1),
                                             "avg_shot": round(props["duration"] / len(board), 1)}})


def build(project_id: str, skip_voice: bool = False) -> None:
    proj = Project(project_id)
    cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    spec = json.loads((proj.dir / "shots.json").read_text(encoding="utf-8"))
    if not proj.state:
        Project.create(project_id, event_id=None, title=spec["title"], angle="见 creative_direction.md", event={})
    proj.step_start("voice")
    if skip_voice and proj.exists("audio", "timings.json"):
        timings = proj.read("audio/timings.json")
    else:
        timings = synthesize(proj, spec, cfg["video"]["tts"]["voice"])
        proj.write("audio/timings.json", timings)
        make_sfx(proj)
    voiced = [{"scene_id": s["id"], "voice": s["voice"], "emphasis_words": []} for s in spec["shots"] if s["voice"]]
    voiced_t = {"scenes": [t for t in timings["scenes"] if t["words"]]}
    captions = build_captions(voiced, voiced_t, max_chars=14)
    proj.write("captions.json", captions)
    proj.step_done("voice", duration=timings["duration"])
    log.info("配音 %.1f 秒，%d 个镜头", timings["duration"], len(spec["shots"]))

    props = build_props(proj, spec, timings, captions)
    write_studio_files(proj, spec, props)
    props_path = proj.write("render/props.json", props)

    proj.step_start("render")
    public = proj.path("render", "_public", ".keep").parent
    shutil.rmtree(public, ignore_errors=True)
    shutil.copytree(proj.dir / "assets", public / "assets", ignore=shutil.ignore_patterns("ocr", "*.json"))
    shutil.copytree(proj.dir / "audio", public / "audio", ignore=shutil.ignore_patterns("shots", "*.json"))
    final = proj.path("render", "final.mp4")
    run(["npx", "remotion", "render", "src/index.ts", spec["composition"], str(final), f"--props={props_path}",
         f"--public-dir={public}", "--codec=h264", "--crf=17", "--log=error"], cwd=REMOTION_DIR, timeout=3600)
    preview, thumb = proj.path("render", "preview.mp4"), proj.path("render", "thumbnail.png")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(final), "-vf", "scale=540:960", "-c:v", "libx264", "-crf", "30",
         "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(preview)])
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2.4", "-i", str(final), "-frames:v", "1", str(thumb)])
    shutil.rmtree(public, ignore_errors=True)
    proj.step_done("render", final_mb=round(final.stat().st_size / 1e6, 1))

    proj.step_start("qc")
    from .qc import run_qc
    try:
        info = run_qc(proj, cfg)
    except Exception as e:
        proj.step_failed("qc", str(e))
        proj.update(pid=None)
        raise
    proj.step_done("qc", **info)
    st = proj.state
    for step in ("research", "script", "assets", "storyboard"):   # 这几步在 directed 流程里是事先人工完成的
        st["steps"][step] = {"status": "done", "seconds": 0, "note": "directed：按 creative_direction.md 人工完成"}
    proj.write("state.json", st)
    proj.update(status="Ready", current_step=None, pid=None)
    log.info("完成：%s  QC=%s", final, info["result"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("project_id")
    b.add_argument("--skip-voice", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    build(args.project_id, args.skip_voice)
