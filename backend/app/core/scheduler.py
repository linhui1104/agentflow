"""智能调度器 ★创新点1：基于 Agent 能力画像的负载均衡调度
对同一角色的多个候选 Agent（不同版本/provider），根据四维画像打分择优，
超载自动路由到次优实例。对比基线：串行调度 / 轮询调度。
"""
from __future__ import annotations

import threading
from typing import Optional

from ..agents import AgentRegistry
from ..models import AgentProfile

# 打分权重（方案书 8.3 节可引用）
W_SUCCESS, W_LATENCY, W_COST, W_LOAD = 0.50, 0.20, 0.10, 0.20
MAX_LOAD = 3          # 单 Agent 并发上限


class CapabilityScheduler:
    """能力画像调度器"""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self._load_lock = threading.Lock()

    # ── 画像打分 ──────────────────────────────────────────────
    def _score(self, p: AgentProfile) -> float:
        c = p.capability
        latency_norm = min(c.avg_latency / 120.0, 1.0)      # 归一化到 [0,1]
        cost_norm = min(c.cost_per_task * 50.0, 1.0)
        load_norm = min(c.load / MAX_LOAD, 1.0)
        return (
            W_SUCCESS * c.success_rate
            - W_LATENCY * latency_norm
            - W_COST * cost_norm
            - W_LOAD * load_norm
        )

    def select(self, role_or_id: str) -> Optional[AgentProfile]:
        """任务分配：优先按 agent_id 精确匹配；否则对同角色候选按能力画像择优
        （全部超载时选负载最低者排队降级）"""
        # 精确匹配（节点绑定具体 Agent）
        exact = self.registry.get(role_or_id)
        if exact is not None:
            return exact
        # 按角色择优（多候选 → 能力画像调度）
        candidates = self.registry.by_role(role_or_id)
        if not candidates:
            return None
        idle = [p for p in candidates if p.capability.load < MAX_LOAD]
        pool = idle if idle else candidates
        best = max(pool, key=self._score)
        return best

    # ── 负载管理 ──────────────────────────────────────────────
    def acquire(self, p: AgentProfile) -> None:
        with self._load_lock:
            p.capability.load += 1

    def release(self, p: AgentProfile) -> None:
        with self._load_lock:
            p.capability.load = max(0, p.capability.load - 1)

    def snapshot(self) -> dict:
        """调度器状态快照（供监控面板与基线对比实验）"""
        return {
            "policy": "capability-weighted load balancing",
            "max_load": MAX_LOAD,
            "weights": {"success": W_SUCCESS, "latency": W_LATENCY,
                        "cost": W_COST, "load": W_LOAD},
            "agents": [
                {"id": p.id, "role": p.role, **p.capability.model_dump()}
                for p in self.registry.all()
            ],
        }


# 基线调度策略（用于对比实验）
def round_robin_select(registry: AgentRegistry, role: str, counter: dict) -> Optional[AgentProfile]:
    """基线：轮询调度"""
    candidates = registry.by_role(role)
    if not candidates:
        return None
    idx = counter.get(role, 0) % len(candidates)
    counter[role] = idx + 1
    return candidates[idx]
