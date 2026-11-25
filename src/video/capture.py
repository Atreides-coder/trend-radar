"""真实操作录屏：只录某一个窗口所在的区域，不接管鼠标，不需要"辅助功能"权限。

- 系统设置：用系统自带的面板链接跳转，录下真实的界面切换
- 终端：把要演示的脚本交给 Terminal.app 运行，录下真实的输入和输出
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

log = logging.getLogger("trend_radar.video.capture")

_BOUNDS_JXA = """
ObjC.import('CoreGraphics');
function run(argv) {
  const list = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, 0)));
  const names = argv;
  const w = list.filter(w => names.includes(w.kCGWindowOwnerName) && w.kCGWindowLayer === 0)[0];
  return w ? JSON.stringify({id: w.kCGWindowNumber, ...w.kCGWindowBounds}) : '';
}
"""
SETTINGS = ["System Settings", "系统设置"]
TERMINAL = ["Terminal", "终端"]


def window(owner_names: list[str], tries: int = 20) -> dict | None:
    for _ in range(tries):
        out = subprocess.run(["osascript", "-l", "JavaScript", "-e", _BOUNDS_JXA, *owner_names],
                             capture_output=True, text=True).stdout.strip()
        if out:
            return json.loads(out)
        time.sleep(0.4)
    return None


def is_running(process: str) -> bool:
    return subprocess.run(["pgrep", "-x", process], capture_output=True).returncode == 0


def record(bounds: dict, seconds: float, out: Path) -> subprocess.Popen:
    """开始录制窗口所在的屏幕区域（非阻塞）。录制时这个窗口不能被别的窗口挡住。"""
    out.unlink(missing_ok=True)
    region = f"{int(bounds['X'])},{int(bounds['Y'])},{int(bounds['Width'])},{int(bounds['Height'])}"
    return subprocess.Popen(["screencapture", "-x", "-v", "-V", str(int(seconds)), "-R", region, str(out)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def record_terminal_script(script: str, workdir: Path, out: Path, seconds: float, cols: int = 52, rows: int = 16) -> bool:
    """在 Terminal.app 里运行一段脚本并录下窗口。脚本开头会留出几秒让录制先开始。

    绝不结束 Terminal 进程：运行这条 pipeline 的会话自己可能就在 Terminal 里。
    演示窗口在脚本结束后会留在那里，需要手动关掉。
    """
    cmd = workdir / "_demo.command"
    cmd.write_text(f"#!/bin/bash\nprintf '\\e[8;{rows};{cols}t'\nclear\nsleep 4\n{script}\nsleep 2\n", encoding="utf-8")
    cmd.chmod(0o755)
    subprocess.run(["open", "-a", "Terminal", str(cmd)], check=True)
    time.sleep(2.2)                      # 等窗口出现并完成调整大小
    bounds = window(TERMINAL)
    if not bounds:
        log.warning("没找到终端窗口")
        return False
    proc = record(bounds, seconds, out)
    proc.wait(timeout=seconds + 30)
    cmd.unlink(missing_ok=True)
    return out.exists() and out.stat().st_size > 10_000


def record_settings(panes: list[tuple[str, float]], out: Path) -> bool:
    """依次打开系统设置的几个面板并录下真实的切换过程。panes: [(面板链接, 停留秒数)]"""
    was_running = is_running("System Settings")
    subprocess.run(["open", panes[0][0]], check=True)
    time.sleep(2.5)
    bounds = window(SETTINGS)
    if not bounds:
        log.warning("没找到系统设置窗口")
        return False
    total = sum(s for _, s in panes) + 1
    proc = record(bounds, total, out)
    time.sleep(panes[0][1])
    for url, stay in panes[1:]:
        subprocess.run(["open", url], check=True)
        time.sleep(stay)
    proc.wait(timeout=total + 30)
    if not was_running:
        subprocess.run(["osascript", "-e", 'tell application "System Settings" to quit'], capture_output=True)
    return out.exists() and out.stat().st_size > 10_000
