"""Asset Collector：先把能拿到的真实素材都采集成一个素材库（assets/library.json），
再由 storyboard 为每一场挑最合适的一个。

素材优先级（能用真实证据，就不用抽象动画）：
  1. 真实一手素材：本机 macOS 系统设置的真实界面、官方公告和官方文档页面
  2. 报道页面截图、报道配图
  3. Remotion 动画（在 storyboard 里定义，不是文件素材）
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .project import ROOT, Project
from .research import UA

log = logging.getLogger("trend_radar.video.assets")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")

# 本机系统设置里可以安全展示的面板：打开对应面板 → 只截这个窗口（不截整个屏幕）
SETTINGS_PANES = {
    "full_disk_access": {
        "url": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles",
        "description": "本机 macOS「系统设置 → 隐私与安全性 → 完全磁盘访问权限」的真实界面：顶部有系统说明文字"
                       "（允许应用访问邮件、信息、Safari 浏览器等数据），下面是已申请该权限的应用列表和开关",
    },
    "privacy_security": {
        "url": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension",
        "description": "本机 macOS「系统设置 → 隐私与安全性」的真实界面：各类权限的列表"
                       "（定位服务、通讯录、文件与文件夹、完全磁盘访问权限等）",
    },
}
OCR_TYPES = {"official_ui", "web_screenshot", "article_screenshot"}
MAX_OCR_CHARS = 2200
SIDEBAR_FRACTION = 0.318   # 系统设置窗口左侧边栏占窗口宽度的比例
_WINLIST_JXA = """
ObjC.import('CoreGraphics');
function run(argv) {
  const list = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, 0)));
  const names = ['System Settings', '系统设置', 'System Preferences', '系统偏好设置'];
  const w = list.filter(w => names.includes(w.kCGWindowOwnerName) && w.kCGWindowLayer === 0)[0];
  return w ? String(w.kCGWindowNumber) : '';
}
"""


def image_size(path: Path) -> tuple[int, int] | None:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        w, h = p.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return None


def web_screenshot(url: str, out: Path, width: int = 540, height: int = 1500, timeout: float = 40) -> bool:
    """无头 Chrome 截图，手机版式（字大，适合竖屏）。2 倍像素密度，输出宽 1080。"""
    if not Path(CHROME).exists():
        log.warning("没有找到 Chrome，跳过网页截图")
        return False
    out.unlink(missing_ok=True)
    profile = tempfile.mkdtemp(prefix="trend-radar-chrome-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--user-data-dir={profile}", f"--window-size={width},{height}", "--force-device-scale-factor=2",
         f"--user-agent={MOBILE_UA}", "--virtual-time-budget=9000", f"--screenshot={out}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not (out.exists() and out.stat().st_size > 0):
        time.sleep(0.5)
    time.sleep(0.5)
    proc.terminate()             # 新版无头 Chrome 截完图不一定自己退出
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    subprocess.run(["pkill", "-f", f"user-data-dir={profile}"], capture_output=True)
    shutil.rmtree(profile, ignore_errors=True)
    return out.exists() and out.stat().st_size > 20_000


def og_image(url: str, out: Path) -> bool:
    """报道的题图（og:image）。"""
    try:
        html = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True).text
        tag = BeautifulSoup(html, "html.parser").find("meta", property="og:image")
        if not tag or not tag.get("content"):
            return False
        img = httpx.get(urljoin(url, tag["content"]), headers={"User-Agent": UA}, timeout=25, follow_redirects=True)
        img.raise_for_status()
        if len(img.content) < 15_000:
            return False
        out.write_bytes(img.content)
        return image_size(out) is not None
    except (httpx.HTTPError, OSError) as e:
        log.warning("题图下载失败 %s: %s", url, e)
        return False


def settings_screenshot(pane: str, out: Path) -> bool:
    """打开本机系统设置的某个面板并只截这个窗口。原本没开系统设置的话，截完就关掉。"""
    was_running = subprocess.run(["pgrep", "-x", "System Settings"], capture_output=True).returncode == 0
    try:
        subprocess.run(["open", SETTINGS_PANES[pane]["url"]], check=True, capture_output=True)
        window_id = ""
        for _ in range(12):
            time.sleep(0.6)
            window_id = subprocess.run(["osascript", "-l", "JavaScript", "-e", _WINLIST_JXA],
                                       capture_output=True, text=True).stdout.strip()
            if window_id:
                break
        if not window_id:
            log.warning("没找到系统设置窗口，跳过 %s", pane)
            return False
        time.sleep(1.2)   # 等面板内容加载完
        raw = out.with_suffix(".raw.png")
        subprocess.run(["screencapture", "-x", "-o", "-l", window_id, str(raw)], capture_output=True)
        if not raw.exists():
            return False
        # 只保留右侧内容区：左侧边栏里有本机的账户名和头像，不能进视频
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                        "-vf", f"crop=iw*{1 - SIDEBAR_FRACTION}:ih:iw*{SIDEBAR_FRACTION}:0", str(out)], capture_output=True)
        raw.unlink(missing_ok=True)
        return out.exists() and out.stat().st_size > 20_000
    except (subprocess.CalledProcessError, OSError) as e:
        log.warning("系统设置截图失败：%s", e)
        return False
    finally:
        if not was_running:
            subprocess.run(["osascript", "-e", 'tell application "System Settings" to quit'], capture_output=True)


def ocr_lines(path: Path) -> list[dict]:
    """用 macOS 自带的 Vision 识别图片里的文字，返回每行文字和位置（0~1，原点左上）。
    有了它，storyboard 才知道截图上到底写了什么，也才能精确地框出要强调的那几行。"""
    p = subprocess.run(["swift", str(ROOT / "scripts" / "ocr.swift"), str(path)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        log.warning("OCR 失败 %s: %s", path.name, p.stderr.strip()[-200:])
        return []
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return []


def update_library(proj: Project, entries: list[dict], *, replace_collected: bool = False,
                   merge_entry: Callable[[dict, dict], dict] | None = None) -> list[dict]:
    """合并上传或采集的素材。重跑采集时只刷新采集项，保留人工选用的图片和片段。"""
    path = proj.path("assets", "library.json")
    collected_types = OCR_TYPES | {"article_image"}
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = proj.read("assets/library.json", [])
        by_id = {a["id"]: a for a in old if not replace_collected or a["type"] not in collected_types}
        for entry in entries:
            key = entry["id"]
            by_id[key] = merge_entry(by_id[key], entry) if merge_entry and key in by_id else entry
        library = list(by_id.values())
        with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as tmp:
            pending = Path(tmp.name)
            try:
                json.dump(library, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.replace(pending, path)
            finally:
                pending.unlink(missing_ok=True)
    return library


def run_assets(proj: Project, cfg: dict) -> dict:
    pack = proj.read("fact_pack.json")
    if not pack:
        raise RuntimeError("还没有 fact_pack.json，请先运行 research")
    library: list[dict] = []

    def add(asset_id: str, kind: str, path: Path, **meta):
        size = image_size(path)
        if not size:
            log.warning("素材无法读取，丢弃：%s", path.name)
            return
        entry = {"id": asset_id, "type": kind, "path": f"assets/{path.name}",
                 "width": size[0], "height": size[1], **meta}
        if kind in OCR_TYPES:
            lines = ocr_lines(path)
            proj.write(f"assets/ocr/{asset_id}.json", lines)
            entry["text_on_image"] = "\n".join(line["text"] for line in lines)[:MAX_OCR_CHARS]
        library.append(entry)
        log.info("素材 %-22s %-18s %dx%d  %s", asset_id, kind, *size,
                 f"OCR {len(entry.get('text_on_image', ''))} 字符" if kind in OCR_TYPES else "")

    # 1. 本机真实界面（一手素材）
    panes = SETTINGS_PANES if cfg.get("video", {}).get("capture_macos_settings") else {}
    for pane, info in panes.items():
        out = proj.path("assets", f"macos_{pane}.png")
        if settings_screenshot(pane, out):
            add(f"macos_{pane}", "official_ui", out, source="本机 macOS 系统设置", url="",
                description=info["description"],
                license_or_usage_note="本机真实界面截图。画面里有本机的应用列表，发布前请确认可以公开。")

    # 2. 官方页面和报道页面
    leads = {v["url"]: v["description"] for v in pack.get("visual_leads", [])}
    for s in pack.get("sources", []):
        official = s["type"] == "official"
        kind = "web_screenshot" if official else "article_screenshot"
        out = proj.path("assets", f"source_{s['id']}_page.png")
        if web_screenshot(s["url"], out) or web_screenshot(s["url"], out, timeout=75):   # 慢的站点再给一次机会
            desc = (f"{s['publisher']} 官方页面《{s['title']}》的截图（手机版式，从页面顶部开始）。" + leads.get(s["url"], "")
                    if official else
                    f"{s['publisher']} 报道页面的截图（手机版式）：可见媒体名、报道标题和开头段落。报道：《{s['title']}》")
            add(f"source_{s['id']}_page", kind, out, source=s["publisher"], url=s["url"], description=desc,
                license_or_usage_note=("官方公开页面截图，用于说明和引用。" if official
                                       else "媒体报道页面截图，仅用于引用出处；版权归原媒体所有。"))
        if not official:
            img = proj.path("assets", f"source_{s['id']}_image.jpg")
            if og_image(s["url"], img):
                add(f"source_{s['id']}_image", "article_image", img, source=s["publisher"], url=s["url"],
                    description=f"{s['publisher']} 这篇报道的题图（《{s['title']}》）。内容未知，只适合作为配图或背景。",
                    license_or_usage_note="报道题图，版权归原媒体或图片作者所有；公开发布前需确认使用范围。")

    known = {s["url"] for s in pack.get("sources", [])}
    for n, (url, desc) in enumerate(((u, d) for u, d in leads.items() if u not in known), start=1):
        out = proj.path("assets", f"lead_{n}_page.png")
        if web_screenshot(url, out):
            add(f"lead_{n}_page", "web_screenshot", out, source=urlsplit(url).netloc, url=url,
                description=f"网页截图（手机版式）。{desc}", license_or_usage_note="公开网页截图，用于说明和引用。")

    library = update_library(proj, library, replace_collected=True)
    kinds = {k: sum(1 for a in library if a["type"] == k) for k in sorted({a["type"] for a in library})}
    log.info("素材库：%d 个 %s", len(library), kinds)
    return {"assets": len(library), **kinds}


def safe_asset_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)
