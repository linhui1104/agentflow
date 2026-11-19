"""Agent 团队：工厂 / 注册表 / 能力画像
基于 openai-agents SDK 封装执行单元，自研注册与画像调度。
"""
from __future__ import annotations

import contextlib
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from agents import Agent as SDKAgent, Runner

from .. import config, llm
from ..models import AgentProfile, Capability

_MCP_SERVER_PATH = Path(__file__).resolve().parent.parent / "tools" / "mcp_server.py"


class AgentFactory:
    """从 AgentProfile 构建 openai-agents 可执行 Agent（支持 Function Calling + MCP 工具）"""

    @staticmethod
    def build(profile: AgentProfile, tools: list[str] = None,
              mcp_config: dict = None) -> SDKAgent:
        from ..tools import resolve_tools, mcp_tool_names
        tool_names = list(profile.tools) + [t for t in (tools or []) if t not in profile.tools]
        kwargs = dict(
            name=profile.id,
            instructions=profile.system_prompt,
            model=llm.build_model(profile.provider),
            tools=resolve_tools(tool_names),
        )
        if mcp_tool_names(tool_names):
            from agents.mcp import MCPServerStdio
            kwargs["mcp_servers"] = [MCPServerStdio(
                params={"command": sys.executable, "args": [str(_MCP_SERVER_PATH)]},
                cache_tools_list=True,
                name="agentflow-mcp",
                **(mcp_config or {}))]
        return SDKAgent(**kwargs)

    @staticmethod
    def run(profile: AgentProfile, task: str, tools: list[str] = None) -> str:
        """执行一次 Agent 调用，返回最终输出文本，并更新画像统计。
        MCP server 生命周期需包住整个 run（async with）。"""
        sdk_agent = AgentFactory.build(profile, tools=tools)
        t0 = time.time()
        try:
            if sdk_agent.mcp_servers:
                import asyncio

                async def _run():
                    async with contextlib.AsyncExitStack() as stack:
                        for s in sdk_agent.mcp_servers:
                            await stack.enter_async_context(s)
                        return await Runner.run(sdk_agent, task, max_turns=config.AGENT_MAX_TURNS)

                result = asyncio.run(_run())
            else:
                result = Runner.run_sync(sdk_agent, task, max_turns=config.AGENT_MAX_TURNS)
            output = str(result.final_output or "").strip()
            elapsed = time.time() - t0
            _update_capability(profile, success=True, latency=elapsed)
            return output
        except Exception as e:
            elapsed = time.time() - t0
            _update_capability(profile, success=False, latency=elapsed)
            raise


def _update_capability(p: AgentProfile, success: bool, latency: float) -> None:
    """滑动窗口更新能力画像（EWMA，α=0.3）"""
    c = p.capability
    alpha = 0.3
    c.success_rate = (1 - alpha) * c.success_rate + alpha * (1.0 if success else 0.0)
    c.avg_latency = (1 - alpha) * c.avg_latency + alpha * latency


class AgentRegistry:
    """Agent 团队注册表：动态注册/发现/版本管理 + 按角色分组"""

    def __init__(self) -> None:
        self._agents: dict[str, list[AgentProfile]] = {}   # role -> [profiles]
        self._lock = threading.Lock()

    def register(self, profile: AgentProfile) -> None:
        """注册 Agent（同 role 多版本/多实例共存，调度器择优）"""
        with self._lock:
            self._agents.setdefault(profile.role, []).append(profile)

    def upsert(self, profile: AgentProfile) -> None:
        """注册或更新：同 id 则替换定义（保留画像统计），否则新增"""
        with self._lock:
            for lst in self._agents.values():
                for i, p in enumerate(lst):
                    if p.id == profile.id:
                        old_cap = p.capability
                        profile.capability = old_cap
                        lst[i] = profile
                        return
            self._agents.setdefault(profile.role, []).append(profile)

    def unregister(self, agent_id: str, role: str) -> None:
        with self._lock:
            lst = self._agents.get(role, [])
            self._agents[role] = [p for p in lst if p.id != agent_id]

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        with self._lock:
            for lst in self._agents.values():
                for p in lst:
                    if p.id == agent_id:
                        return p
        return None

    def by_role(self, role: str) -> list[AgentProfile]:
        return list(self._agents.get(role, []))

    def all(self) -> list[AgentProfile]:
        with self._lock:
            return [p for lst in self._agents.values() for p in lst]

    def roles(self) -> list[str]:
        return sorted(self._agents.keys())
