"""工作流存储层：多工作流持久化（data/workflows/*.json）
用户可在前端编辑并保存自己的设计；模板目录内置多个通用场景。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .. import config
from ..models import Workflow

WF_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "workflows"
WF_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _path(wf_id: str) -> Path:
    # 安全：id 只允许字母数字中划线
    safe = "".join(c for c in wf_id if c.isalnum() or c in "-_")
    return WF_DIR / f"{safe}.json"


def save_workflow(wf: Workflow) -> str:
    with _lock:
        _path(wf.id).write_text(json.dumps(wf.model_dump(), ensure_ascii=False, indent=2),
                                encoding="utf-8")
    return str(_path(wf.id))


def load_workflow(wf_id: str) -> Workflow | None:
    p = _path(wf_id)
    if not p.exists():
        return None
    try:
        return Workflow.model_validate(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


def list_workflows() -> list[Workflow]:
    out = []
    for p in sorted(WF_DIR.glob("*.json")):
        wf = load_workflow(p.stem)
        if wf:
            out.append(wf)
    return out


def delete_workflow(wf_id: str) -> bool:
    p = _path(wf_id)
    if p.exists():
        with _lock:
            p.unlink()
        return True
    return False


# ── 工作流绑定的 Agent 团队持久化 ──────────────────────────────
def save_agents(wf_id: str, agents: list) -> str:
    """保存工作流绑定的 Agent 定义（AI 生成的工作流需要持久化其团队）"""
    p = _path(wf_id).with_suffix(".agents.json")
    with _lock:
        p.write_text(json.dumps([a.model_dump() for a in agents], ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return str(p)


def load_agents(wf_id: str) -> list:
    from ..models import AgentProfile
    p = _path(wf_id).with_suffix(".agents.json")
    if not p.exists():
        return []
    try:
        return [AgentProfile.model_validate(x)
                for x in json.loads(p.read_text(encoding="utf-8"))]
    except Exception:
        return []
