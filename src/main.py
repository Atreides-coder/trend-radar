"""Trend Radar 入口。

    python -m src.main                  # 完整 pipeline（目前实现到 cluster）
    python -m src.main --stage fetch    # 只抓取（不调用模型，可以一天跑多次）
    python -m src.main --stage filter   # Prefilter + Fast Filter（Codex）+ 报告
    python -m src.main --stage cluster  # Signals → Events → Global Ranking → Trends
    python -m src.main --stage filter --force     # 改了 prompt / 规则后全部重新筛选
    python -m src.main --stage filter --dry-run   # 不调用模型
    python -m src.main --debug          # 少量数据 + 打印模型输入输出
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .pipeline.cluster import run_cluster_stage
from .pipeline.fetch import run_fetch
from .pipeline.filter_stage import run_filter_stage
from .storage.database import Database

ROOT = Path(__file__).resolve().parent.parent
STAGES = ["fetch", "filter", "cluster", "research", "output"]
NOT_IMPLEMENTED = {"research": "Phase 4", "output": "Phase 5"}


def load_yaml(name: str) -> dict:
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def setup_logging(debug: bool):
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / f"{datetime.now():%Y-%m-%d}.log", encoding="utf-8"),
        ],
    )
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="Trend Radar V1")
    parser.add_argument("--stage", choices=STAGES, help="只跑某一个阶段")
    parser.add_argument("--debug", action="store_true", help="少量数据 + 详细日志")
    parser.add_argument("--dry-run", action="store_true", help="不调用任何模型")
    parser.add_argument("--force", action="store_true",
                        help="filter 阶段：窗口内条目全部重新筛选（改 prompt / 规则后使用）")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    setup_logging(args.debug)
    log = logging.getLogger("trend_radar")
    settings = load_yaml("settings.yaml")
    sources = load_yaml("sources.yaml").get("sources", [])
    db = Database(ROOT / settings.get("database", "data/trend_radar.db"))

    try:
        for stage in [args.stage] if args.stage else STAGES:
            if stage == "fetch":
                run_fetch(db, sources, settings, debug=args.debug)
            elif stage == "filter":
                run = run_filter_stage(db, ROOT, settings, debug=args.debug,
                                       dry_run=args.dry_run, force=args.force)
                if run["status"] == "failed":
                    return 1
            elif stage == "cluster":
                run = run_cluster_stage(db, ROOT, settings, dry_run=args.dry_run)
                if run["status"] == "failed":
                    return 1
            else:
                log.info("stage '%s' 尚未实现（%s）", stage, NOT_IMPLEMENTED[stage])
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
