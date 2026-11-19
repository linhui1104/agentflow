"""AI 工作流生成器 ★：自然语言需求 → LLM 设计工作流 DSL → 校验注册
用户只需描述业务需求，平台自动设计 Agent 团队与 DAG 工作流，自我适配。
"""
from __future__ import annotations

import json
import re

from .. import llm
from ..models import AgentProfile, Node, NodeType, Workflow

GEN_PROMPT = """你是一个多智能体工作流架构师。请根据用户需求，设计一个多 Agent 协作工作流。

设计要求：
1. 把任务拆成 3-6 个节点，节点类型可选：agent（由某个 Agent 执行）、verify（对指定前驱产出做质量验证）、condition（条件分支，next[0]为真分支、next[1]为假分支）
2. 每个 agent 节点绑定一个 Agent（给出角色、职责、系统提示词）；重质量环节（撰写/生成类）应配置 verify_threshold（1-10 的验证阈值）与 max_rounds（最多修正轮数，≤3）
3. 信息搜集类节点应在 tools 里挂载 search_web
4. verify 节点 config 含 target（指向被验证的节点 id）
5. condition 节点 config 含 condition 表达式（格式 verify_score>=7 或 verify_score<7）与 target
6. 条件假分支可以指回被验证的生成节点或验证节点形成修正循环（推荐），此时必须在假分支节点与相关节点的 config 中设置 max_visits（循环最多执行次数，2-3 为佳）
7. 全部节点形成有向图，指定入口节点 entry
8. 只输出 JSON，不要任何其他文字。JSON 结构如下：
{
  "name": "工作流名称（中文，≤10字）",
  "description": "一句话流程说明",
  "agents": [
    {"id": "小写英文id", "name": "中文名", "role": "角色", "system_prompt": "系统提示词"}
  ],
  "nodes": [
    {"id": "node_id", "type": "agent|verify|condition", "agent_id": "agents中的id（agent节点必填）",
     "config": {"input_template": "任务模板，可用{task}与{前驱节点id}占位符"},
     "next": ["后继节点id"]}
  ],
  "entry": "入口节点id"
}

用户需求：{REQUIREMENT}
"""


def _extract_json(text: str) -> dict | None:
    """从 LLM 输出提取 JSON（容错：剥掉 markdown 代码块）"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 截取第一个 { 到最后一个 }
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                return None
        return None


def _validate(dsl: dict) -> tuple[bool, str]:
    """DSL 结构校验"""
    if not isinstance(dsl, dict):
        return False, "不是 JSON 对象"
    agents = dsl.get("agents") or []
    nodes = dsl.get("nodes") or []
    entry = dsl.get("entry")
    if not agents or not nodes or not entry:
        return False, "缺少 agents/nodes/entry"
    agent_ids = {a.get("id") for a in agents if isinstance(a, dict)}
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    if entry not in node_ids:
        return False, f"entry {entry} 不在节点中"
    for n in nodes:
        ntype = n.get("type")
        if ntype not in ("agent", "verify", "condition"):
            return False, f"节点 {n.get('id')} 类型非法: {ntype}"
        if ntype == "agent" and n.get("agent_id") not in agent_ids:
            return False, f"节点 {n.get('id')} 的 agent_id 未定义"
        for nx in (n.get("next") or []):
            if nx not in node_ids:
                return False, f"节点 {n.get('id')} 的后继 {nx} 不存在"
    return True, ""


def generate(requirement: str) -> tuple[Workflow, list[AgentProfile]]:
    """需求 → 工作流。失败抛 RuntimeError（带原因）"""
    import asyncio

    async def _gen():
        from ..config import get_provider
        prov = get_provider("deepseek")
        client = llm._make_client("deepseek")
        r = await client.chat.completions.create(
            model=prov["model"],
            messages=[{"role": "user", "content":
                       GEN_PROMPT.replace("{REQUIREMENT}", requirement)}],
            response_format={"type": "json_object"},
            temperature=0.4,
            timeout=120,
        )
        return r.choices[0].message.content

    raw = asyncio.run(_gen())
    dsl = _extract_json(raw)
    if dsl is None:
        raise RuntimeError(f"LLM 输出无法解析为 JSON：{raw[:200]}")
    ok, err = _validate(dsl)
    if not ok:
        raise RuntimeError(f"工作流 DSL 校验失败：{err}")

    agents = [AgentProfile(
        id=str(a["id"]).lower().replace(" ", "-"),
        name=str(a.get("name") or a["id"]),
        role=str(a.get("role") or a["id"]),
        system_prompt=str(a.get("system_prompt") or ""),
    ) for a in dsl["agents"]]

    nodes = []
    for n in dsl["nodes"]:
        cfg = dict(n.get("config") or {})
        nodes.append(Node(
            id=str(n["id"]), type=NodeType(n["type"]),
            agent_id=n.get("agent_id"),
            config=cfg,
            next=[str(x) for x in (n.get("next") or [])],
        ))

    # 回边检测：若存在循环（边指向祖先），自动给环上节点补 max_visits（LLM 漏配时兜底）
    succ = {n.id: list(n.next) for n in nodes}

    def _has_back_edge() -> bool:
        vis, back = set(), False

        def dfs(nid):
            nonlocal back
            vis.add(nid)
            for s in succ.get(nid, []):
                if s in vis:
                    back = True
                elif s in succ:
                    dfs(s)

        dfs(str(dsl["entry"]))
        return back

    if _has_back_edge():
        for n in nodes:
            if "max_visits" not in n.config:
                n.config["max_visits"] = 3

    wf_id = "gen-" + re.sub(r"[^a-z0-9]+", "-", str(dsl.get("name", "workflow")).lower()).strip("-")[:24]
    if wf_id in ("gen-", "gen"):
        import time as _t
        wf_id = f"gen-{int(_t.time()) % 100000}"
    wf = Workflow(
        id=wf_id, name=str(dsl.get("name") or "AI生成工作流"),
        description=str(dsl.get("description") or ""),
        nodes=nodes, entry=str(dsl["entry"]),
    )
    return wf, agents
