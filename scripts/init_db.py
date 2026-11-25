"""初始化数据库（建表是幂等的，重复运行安全）。用法：python scripts/init_db.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from src.storage.database import Database  # noqa: E402

settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
db = Database(ROOT / settings.get("database", "data/trend_radar.db"))
tables = [r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print(f"DB ready: {db.path}\nTables: {', '.join(t for t in tables if not t.startswith('sqlite_'))}")
db.close()
