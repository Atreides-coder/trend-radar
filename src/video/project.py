"""Video Project：一条视频的全部中间产物和状态，都在 video_projects/<project_id>/ 下。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = ROOT / "video_projects"

# 步骤顺序，以及 Dashboard 上显示的状态名
STEPS = ["research", "script", "voice", "assets", "storyboard", "render", "qc"]
STATUS = {
    "research": "Researching", "script": "Writing", "voice": "Generating Voice",
    "assets": "Collecting Assets", "storyboard": "Collecting Assets",
    "render": "Rendering", "qc": "QC",
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "video"


def directed_skip_voice(steps: list[str]) -> bool:
    if steps in (["render"], ["render", "qc"]):
        return True
    if steps in (["voice", "render", "qc"], ["voice", "storyboard", "render", "qc"], STEPS):
        return False
    raise ValueError("导演版可重渲染、重新配音并渲染，或单独运行质检。")


class Project:
    def __init__(self, project_id: str):
        self.id = project_id
        self.dir = PROJECTS_DIR / project_id
        self.state_path = self.dir / "state.json"

    # ---- 文件 ----
    def path(self, *parts: str) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def exists(self, *parts: str) -> bool:
        return self.dir.joinpath(*parts).exists()

    @property
    def is_directed(self) -> bool:
        if (self.dir / "shots.json").is_file():
            return True
        # 旧导演版在制作记录里标明了手工分镜。分镜文件遗失时也不能把原片交给通用模板。
        storyboard = self.state.get("steps", {}).get("storyboard", {})
        return (storyboard.get("note") or "").startswith("directed：")

    def read(self, name: str, default=None):
        p = self.dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def write(self, name: str, data) -> Path:
        p = self.path(name)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    # ---- 状态 ----
    @classmethod
    def create(cls, project_id: str, *, event_id: int | None, title: str, angle: str, event: dict) -> "Project":
        proj = cls(project_id)
        for sub in ("assets", "audio", "render", "research"):
            (proj.dir / sub).mkdir(parents=True, exist_ok=True)
        proj.write("state.json", {
            "id": project_id, "event_id": event_id, "title": title, "angle": angle, "event": event,
            "status": "Created", "current_step": None, "error": None,
            "steps": {s: {"status": "pending"} for s in STEPS},
            "created_at": now(), "updated_at": now(),
        })
        return proj

    @property
    def state(self) -> dict:
        return self.read("state.json", {})

    def update(self, **fields):
        st = self.state
        st.update(fields, updated_at=now())
        self.write("state.json", st)

    def step_start(self, step: str):
        st = self.state
        st["steps"][step] = {"status": "running", "started_at": now()}
        st.update(status=STATUS[step], current_step=step, error=None, updated_at=now())
        self.write("state.json", st)

    def step_done(self, step: str, **info):
        st = self.state
        st["steps"][step].update(status="done", finished_at=now(), **info)
        st["updated_at"] = now()
        self.write("state.json", st)

    def step_failed(self, step: str, error: str):
        st = self.state
        st["steps"][step].update(status="failed", finished_at=now(), error=error)
        st.update(status="Failed", error=f"{step}: {error}", updated_at=now())
        self.write("state.json", st)


def list_projects() -> list[dict]:
    if not PROJECTS_DIR.exists():
        return []
    states = [Project(d.name).state for d in PROJECTS_DIR.iterdir() if (d / "state.json").exists()]
    return sorted(states, key=lambda s: s.get("created_at", ""), reverse=True)
