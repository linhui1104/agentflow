"""核心数据模型：Agent 画像 / 工作流 DAG / 运行状态"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Agent ────────────────────────────────────────────────────────
class Capability(BaseModel):
    """能力画像四维指标（滑动窗口统计）"""
    success_rate: float = 1.0        # 成功率 0-1
    avg_latency: float = 30.0        # 平均耗时（秒）
    cost_per_task: float = 0.01      # 平均成本（元/任务）
    load: int = 0                    # 当前并发负载


class AgentProfile(BaseModel):
    """Agent 定义（团队注册表中的一员）"""
    id: str
    name: str
    role: str                        # 角色描述
    system_prompt: str
    provider: str = "deepseek"
    tools: list[str] = Field(default_factory=list)
    capability: Capability = Field(default_factory=Capability)
    version: int = 1


# ── Workflow ─────────────────────────────────────────────────────
class NodeType(str, Enum):
    AGENT = "agent"                  # 单个 Agent 执行节点
    PARALLEL = "parallel"            # 并行块
    CONDITION = "condition"          # 条件分支
    VERIFY = "verify"                # 交叉验证节点
    TOOL = "tool"                    # 工具节点


class Node(BaseModel):
    id: str
    type: NodeType
    agent_id: Optional[str] = None   # type=agent/verify 时绑定
    config: dict = Field(default_factory=dict)   # 如 {input_from, prompt_template, verify_threshold}
    next: list[str] = Field(default_factory=list)   # 后继节点 id 列表


class Workflow(BaseModel):
    id: str
    name: str
    description: str = ""
    nodes: list[Node] = Field(default_factory=list)
    entry: str = ""                  # 入口节点 id
    version: int = 1


# ── Run 状态 ─────────────────────────────────────────────────────
class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    LOOPING = "looping"              # Self-Loop 修正中
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class LoopRecord(BaseModel):
    """Self-Loop 一轮修正轨迹"""
    round: int
    feedback: str                    # 评审意见
    score: float
    revised_prompt: str              # 修正后注入的提示
    output_before: str
    output_after: str


class NodeRun(BaseModel):
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    input: str = ""
    output: str = ""
    agent_id: str = ""
    verify_score: Optional[float] = None
    verify_reason: str = ""
    loops: list[LoopRecord] = Field(default_factory=list)
    visit_count: int = 0            # 已执行次数（支持工作流级有限循环）
    last_seq: int = 0               # 最近一次执行序号（变化驱动重跑判定）
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: str = ""


class Run(BaseModel):
    id: str
    workflow_id: str
    status: NodeStatus = NodeStatus.PENDING
    nodes: dict[str, NodeRun] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    final_output: str = ""
