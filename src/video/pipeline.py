"""Video Pipeline V0 编排。

    python -m src.video.pipeline create --event-id 2 --id apple-agent-permissions --angle "..."
    python -m src.video.pipeline run apple-agent-permissions              # 从头跑到 final.mp4
    python -m src.video.pipeline run apple-agent-permissions --from voice  # 从某一步开始重跑（改稿后重新配音等）
    python -m src.video.pipeline run apple-agent-permissions --only render
    python -m src.video.pipeline run apple-agent-permissions --steps voice,storyboard,render,qc   # 改稿后
    python -m src.video.pipeline regen-scene apple-agent-permissions 4 --instruction "更口语一点"

Python 是 orchestrator；需要模型判断的步骤（research / script / storyboard）走 CodexRunner。
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import time
import traceback

import yaml
from dotenv import load_dotenv

from ..ai.codex_runner import CodexRunner
from .project import ROOT, STEPS, Project, directed_skip_voice, slugify

log = logging.getLogger("trend_radar.video")


def settings() -> dict:
    return yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}


def create_project(event_id: int, project_id: str | None = None, angle: str = "") -> Project:
    db = sqlite3.connect(ROOT / "data" / "trend_radar.db")
    db.row_factory = sqlite3.Row
    ev = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    db.close()
    if not ev:
        raise SystemExit(f"找不到 event {event_id}")
    event = {k: ev[k] for k in ("id", "canonical_title", "summary", "core_change",
                                 "why_it_matters", "possible_bigger_trend", "rank")}
    project_id = project_id or f"event-{event_id}-{slugify(ev['canonical_title']) or int(time.time())}"
    if Project(project_id).state:
        raise SystemExit(f"项目已存在：{project_id}")
    return Project.create(project_id, event_id=event_id, title=ev["canonical_title"],
                          angle=angle or ev["possible_bigger_trend"] or ev["core_change"], event=event)


def run_step(proj: Project, step: str, cfg: dict, runner_factory) -> dict:
    if step == "research":
        from .research import run_research
        return run_research(proj, runner_factory(), cfg)
    if step == "script":
        from .writer import run_script
        return run_script(proj, runner_factory())
    if step == "voice":
        from .voice import run_voice
        return run_voice(proj, cfg, runner_factory)
    if step == "assets":
        from .assets import run_assets
        return run_assets(proj, cfg)
    if step == "storyboard":
        from .storyboard import run_storyboard
        return run_storyboard(proj, runner_factory())
    if step == "render":
        from .render import run_render
        return run_render(proj, cfg)
    if step == "qc":
        from .qc import run_qc
        return run_qc(proj, cfg)
    raise ValueError(step)


def run_pipeline(project_id: str, start: str | None = None, only: str | None = None,
                 steps: list[str] | None = None) -> bool:
    proj = Project(project_id)
    if not proj.state:
        raise SystemExit(f"找不到项目：{project_id}")
    steps = steps or ([only] if only else STEPS[STEPS.index(start):] if start else STEPS)
    if proj.is_directed and steps != ["qc"]:
        try:
            skip_voice = directed_skip_voice(steps)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        proj.update(pid=os.getpid(), current_step=None, error=None)
        try:
            from .directed import build
            if skip_voice and not (proj.exists("audio", "voice.wav") and proj.exists("audio", "timings.json")):
                raise ValueError("缺少已有配音或时间轴，请选择重新配音并渲染。")
            build(proj.id, skip_voice=skip_voice)
        except Exception as e:
            log.exception("导演版制作失败")
            step = proj.state.get("current_step") or ("render" if skip_voice else "voice")
            proj.step_failed(step, str(e))
            proj.update(pid=None)
            return False
        return True

    cfg = settings()
    proj.update(pid=os.getpid())

    runner = None

    def runner_factory():
        nonlocal runner
        runner = runner or CodexRunner.from_env(cfg.get("codex", {}))
        return runner

    for step in steps:
        proj.step_start(step)
        log.info("▶ %s", step)
        t0 = time.monotonic()
        try:
            info = run_step(proj, step, cfg, runner_factory) or {}
        except Exception as e:  # 任何一步失败都记录下来，Dashboard 能看到卡在哪
            log.error("✗ %s 失败：%s\n%s", step, e, traceback.format_exc())
            proj.step_failed(step, f"{type(e).__name__}: {e}")
            proj.update(pid=None)
            return False
        proj.step_done(step, seconds=round(time.monotonic() - t0, 1), **info)
        log.info("✓ %s（%.1fs）%s", step, time.monotonic() - t0, info)
    if runner:
        proj.update(codex_usage=runner.usage.as_dict(), model=runner.model, reasoning_effort=runner.reasoning_effort)
    # 跑到了 QC 且成片存在 → Ready；否则停在中间，等下一步
    ready = steps[-1] == STEPS[-1] and proj.exists("render", "final.mp4")
    proj.update(status="Ready" if ready else "Paused", current_step=None, pid=None)
    return True


def main():
    parser = argparse.ArgumentParser(description="Trend Radar Video Pipeline V0")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--event-id", type=int, required=True)
    c.add_argument("--id")
    c.add_argument("--angle", default="")
    r = sub.add_parser("run")
    r.add_argument("project_id")
    r.add_argument("--from", dest="start", choices=STEPS)
    r.add_argument("--only", choices=STEPS)
    r.add_argument("--steps", help="逗号分隔的步骤列表，按给定顺序执行")
    g = sub.add_parser("regen-scene", help="只重写某一场的口播，然后重新配音、分镜、渲染")
    g.add_argument("project_id")
    g.add_argument("scene_id", type=int)
    g.add_argument("--instruction", default="")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if args.cmd == "create":
        proj = create_project(args.event_id, args.id, args.angle)
        print(proj.id)
        return
    proj = Project(args.project_id)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(proj.path("pipeline.log"), encoding="utf-8")])
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if args.cmd == "regen-scene":
        if proj.is_directed:
            raise SystemExit("导演版口播和分镜请在 shots.json 中修改。")
        from .writer import regenerate_scene
        proj.update(status="Writing", current_step="script", error=None, pid=os.getpid())
        try:
            regenerate_scene(proj, CodexRunner.from_env(settings().get("codex", {})), args.scene_id, args.instruction)
        except Exception as e:  # noqa: BLE001
            log.error("重写第 %d 场失败：%s", args.scene_id, e)
            proj.update(status="Failed", error=f"regen-scene: {e}", pid=None)
            sys.exit(1)
        sys.exit(0 if run_pipeline(args.project_id, steps=["voice", "storyboard", "render", "qc"]) else 1)
    steps = [s.strip() for s in args.steps.split(",")] if args.steps else None
    if steps and any(s not in STEPS for s in steps):
        raise SystemExit(f"未知步骤：{steps}")
    sys.exit(0 if run_pipeline(args.project_id, args.start, args.only, steps) else 1)


if __name__ == "__main__":
    main()
