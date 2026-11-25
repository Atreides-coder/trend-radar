"""安装本项目的研究和剪辑工具。用 .venv/bin/python scripts/install_integrations.py 运行。"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


TOOLS = Path(__file__).resolve().parents[1] / ".tools"
SOURCES = (
    ("last30days", "mvanhorn/last30days-skill", "v4.6.0", "64b1f006f800640022ce07f51de5ce56aad34b76"),
    ("autoclip", "zhouxiaoka/autoclip", "v1.6.0", "2566158cf31fbc4ca19955783d56a031a233b5e4"),
)
# 仅装本地镜头检测和视频截取需要的包。与主项目的 FastAPI 环境隔离。
AUTOCLIP_DEPS = ("numpy==2.5.5", "PyYAML==6.0.4", "pydantic==2.13.5",
                 "pydantic-settings==2.15.0", "SQLAlchemy==2.0.52")


def verify_commit(path: Path, commit: str):
    actual = subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()
    if actual != commit:
        raise SystemExit(f"{path} 当前为 {actual}，本项目需要 {commit}。请先保存该目录里的改动。")


def install_source(name: str, repo: str, tag: str, commit: str):
    target = TOOLS / name
    if target.exists():
        verify_commit(target, commit)
        return
    with tempfile.TemporaryDirectory(dir=TOOLS) as temp:
        checkout = Path(temp) / name
        subprocess.run(["git", "clone", "--depth", "1", "--branch", tag,
                        f"https://github.com/{repo}.git", checkout], check=True)
        verify_commit(checkout, commit)
        checkout.rename(target)


def main():
    if sys.version_info < (3, 12):
        raise SystemExit("请使用项目的 Python 3.12 或更高版本。")
    for tool in ("git", "uv", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"找不到 {tool}，请先将其加入 PATH。")
    TOOLS.mkdir(exist_ok=True)
    for source in SOURCES:
        install_source(*source)
    env = TOOLS / "autoclip-env"
    python = env / "bin" / "python"
    if not python.exists():
        subprocess.run(["uv", "venv", "--python", sys.executable, env], check=True)
    subprocess.run(["uv", "pip", "install", "--python", python, *AUTOCLIP_DEPS], check=True)
    print(f"研究和剪辑工具已安装在 {TOOLS}")


if __name__ == "__main__":
    main()
