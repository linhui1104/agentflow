"""运行快照存储：每次 Run 完整存档（JSON），可回放、可复现"""
import json
import os
from datetime import datetime

from . import config
from .models import Run


def save_snapshot(run: Run) -> str:
    """保存 Run 快照（临时文件+rename 原子写），返回文件路径"""
    path = config.DATA_DIR / "runs" / f"{run.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(run.model_dump_json())
    payload["saved_at"] = datetime.now().isoformat()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp, path)
    return str(path)


def list_snapshots() -> list[str]:
    d = config.DATA_DIR / "runs"
    if not d.exists():
        return []
    return sorted((p.name for p in d.glob("*.json")), reverse=True)


def load_snapshot(run_id: str) -> dict | None:
    """读取快照；解析失败（写入中/损坏）返回 None，不抛异常"""
    p = config.DATA_DIR / "runs" / f"{run_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
