"""Agent 演示：让一个真实的 Agent（Codex CLI）在只有示例文件的沙盒文件夹里完成一个多步骤任务，
把它的每一个动作实时打印出来（供录屏），同时把事件和时间戳存下来（供成片对时和数步数）。

沙盒是 workspace-write：它只能读写这个演示文件夹，不能联网，也碰不到别的文件。

用法：python scripts/agent_demo.py <演示文件夹> <事件输出.jsonl>
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK = "整理这个文件夹，找出本周要跟进的事，给王经理写一封跟进邮件。"
PROMPT = (
    "这是我的工作文件夹。请你：先看看里面有什么；读一读相关文件，找出本周需要跟进的事；"
    "给王经理写一封跟进邮件，存成 邮件草稿.txt；最后把 待办.md 更新一下。"
    "直接动手做，不用问我。每一步用单独的命令完成。"
)
AMBER, DIM, BOLD, GREEN, RESET = "\033[38;5;214m", "\033[2m", "\033[1m", "\033[32m", "\033[0m"
WIDTH = 44


def env(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return os.environ.get(name, "")


def clip(text: str, width: int) -> str:
    """按显示宽度截断（中文占两格）。"""
    out, used = "", 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + w > width - 1:
            return out + "…"
        out, used = out + ch, used + w
    return out


def clean(command: str) -> str:
    m = re.match(r"^\S*(?:ba|z)?sh\s+-l?c\s+(.*)$", command.strip(), re.S)
    if m:
        command = m.group(1).strip()
        if len(command) > 1 and command[0] == command[-1] and command[0] in "'\"":
            command = command[1:-1]
    return " ".join(command.split())


def main():
    workdir, events_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    t0 = time.time()
    print(f"{BOLD}你{RESET}  整理这个文件夹，找出本周要跟进")
    print("    的事，给王经理写一封跟进邮件。\n")
    time.sleep(1.2)
    print(f"{AMBER}AI Agent 开始工作{RESET}\n", flush=True)

    proc = subprocess.Popen(
        [shutil.which("codex") or "codex", "exec", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
         "--sandbox", "workspace-write", "--color", "never", "-C", str(workdir),
         "-m", env("CODEX_MODEL"), "-c", f'model_reasoning_effort="{env("CODEX_REASONING_EFFORT")}"', "--json", "-"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=workdir)
    proc.stdin.write(PROMPT)
    proc.stdin.close()

    steps, seen = 0, set()
    with events_path.open("w", encoding="utf-8") as log:
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = ev.get("item") or {}
            kind = item.get("type")
            label = None
            if kind == "command_execution" and item.get("id") not in seen:
                seen.add(item.get("id"))
                label = clean(item.get("command", ""))
            elif kind == "file_change" and ev.get("type") == "item.completed":
                label = "写入 " + "、".join(Path(c.get("path", "")).name for c in item.get("changes", []))
            if label:
                steps += 1
                print(f" {AMBER}{steps:02d}{RESET}  {clip(label, WIDTH)}", flush=True)
            log.write(json.dumps({"t": round(time.time() - t0, 3), "step": steps if label else None,
                                  "label": label, "event": ev}, ensure_ascii=False) + "\n")
            log.flush()
    proc.wait()
    print(f"\n{GREEN}完成{RESET} · 共 {BOLD}{steps}{RESET} 步 · 没有一步向你确认", flush=True)
    with events_path.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"t": round(time.time() - t0, 3), "done": True, "steps": steps}) + "\n")


if __name__ == "__main__":
    main()
