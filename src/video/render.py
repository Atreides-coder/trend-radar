"""Render：storyboard + captions + voice → Remotion → render/final.mp4，再用 FFmpeg 出预览和封面。"""
from __future__ import annotations

import logging
import shutil
import subprocess

from .project import ROOT, Project

log = logging.getLogger("trend_radar.video.render")
REMOTION_DIR = ROOT / "video"
SHOT_FIELDS = ("component", "start", "end", "highlight", "headline", "sub", "diagram", "quote", "data")
ASSET_FIELDS = ("id", "type", "path", "source", "url", "width", "height", "duration")
EMPTY_DIAGRAM = {"kind": "none", "title": "", "left_label": "", "left_items": [], "right_label": "",
                 "right_items": [], "steps": []}


def build_props(proj: Project) -> dict:
    board, script = proj.read("storyboard.json"), proj.read("script.json")
    captions, pack = proj.read("captions.json"), proj.read("fact_pack.json", {})
    if not board or not captions:
        raise RuntimeError("需要先有 storyboard.json 和 captions.json")
    scenes = []
    for sc in board["scenes"]:
        shots = []
        for sh in sc["shots"]:
            shot = {k: sh.get(k) for k in SHOT_FIELDS}
            shot["diagram"] = {**EMPTY_DIAGRAM, **(sh.get("diagram") or {})}
            shot["quote"] = {"text": "", "attribution": "", **(sh.get("quote") or {})}
            shot["data"] = {"value": "", "label": "", **(sh.get("data") or {})}
            shot["asset"] = {k: sh["asset"][k] for k in ASSET_FIELDS if k in sh["asset"]} if sh.get("asset") else None
            shots.append(shot)
        scenes.append({"scene_id": sc["scene_id"], "start": sc["start"], "end": sc["end"],
                       "purpose": sc["purpose"], "shots": shots})
    publishers = list(dict.fromkeys(s["publisher"] for s in pack.get("sources", [])))
    return {"title": script["title"], "duration": board["duration"], "audio": "audio/voice.wav",
            "scenes": scenes, "captions": captions, "sources": publishers}


def run(cmd: list[str], cwd=None, timeout: int = 1800):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} 失败：{(p.stderr or p.stdout).strip()[-900:]}")
    return p


def run_render(proj: Project, cfg: dict) -> dict:
    props = build_props(proj)
    props_path = proj.write("render/props.json", props)

    # Remotion 的 public 目录：只放这次渲染要用的素材和配音（不把旧的成片也打包进去）
    public = proj.path("render", "_public", ".keep").parent
    shutil.rmtree(public, ignore_errors=True)
    (public / "audio").mkdir(parents=True)
    (public / "assets").mkdir()
    shutil.copy2(proj.dir / "audio" / "voice.wav", public / "audio" / "voice.wav")
    used = {sh["asset"]["path"] for sc in props["scenes"] for sh in sc["shots"] if sh["asset"]}
    for rel in used:
        (public / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(proj.dir / rel, public / rel)

    if not (REMOTION_DIR / "node_modules").exists():
        log.info("安装 Remotion 依赖…")
        run(["npm", "install", "--silent"], cwd=REMOTION_DIR)

    final = proj.path("render", "final.mp4")
    log.info("Remotion 渲染中（%d 个镜头，%.1f 秒）…", sum(len(s["shots"]) for s in props["scenes"]), props["duration"])
    run(["npx", "remotion", "render", "src/index.ts", "TrendVideo", str(final), f"--props={props_path}",
         f"--public-dir={public}", "--codec=h264", "--crf=18", "--log=error"], cwd=REMOTION_DIR, timeout=3600)

    # 预览（小文件，方便在 Dashboard 里快速看）和封面
    preview, thumb = proj.path("render", "preview.mp4"), proj.path("render", "thumbnail.png")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(final), "-vf", "scale=540:960", "-c:v", "libx264",
         "-crf", "30", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(preview)])
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.6", "-i", str(final), "-frames:v", "1", str(thumb)])
    shutil.rmtree(public, ignore_errors=True)
    size = final.stat().st_size / 1e6
    log.info("成片：%s（%.1f MB）", final, size)
    return {"final_mb": round(size, 1), "duration": props["duration"]}
