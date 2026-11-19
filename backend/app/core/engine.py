"""工作流引擎：DAG 拓扑执行器，串联调度器/验证器/Self-Loop
支持顺序、并行分支、条件分支、循环修正、验证节点。
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Callable, Optional

from ..agents import AgentFactory, AgentRegistry
from .. import llm
from ..models import Node, NodeRun, NodeStatus, NodeType, Run, Workflow
from .loop import SelfLoopEngine
from .scheduler import CapabilityScheduler
from .verifier import CrossVerifier

# 事件回调: (node_id, status, payload_dict)
EventFn = Callable[[str, str, dict], None]


class WorkflowEngine:
    def __init__(self, registry: AgentRegistry,
                 on_event: Optional[EventFn] = None) -> None:
        self.registry = registry
        self.scheduler = CapabilityScheduler(registry)
        self.on_event = on_event
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    # ── 事件 ─────────────────────────────────────────────────
    def _emit(self, run: Run, nr: NodeRun, status: str, **payload) -> None:
        nr.status = NodeStatus(status)
        nr.started_at = nr.started_at or datetime.now()
        if status in (NodeStatus.DONE, NodeStatus.FAILED, NodeStatus.SKIPPED):
            nr.finished_at = datetime.now()
        if self.on_event:
            try:
                self.on_event(run.id, nr.node_id, {
                    "status": status, "output_len": len(nr.output),
                    "verify_score": nr.verify_score,
                    **payload,
                })
            except Exception:
                pass

    # ── 输入组装 ─────────────────────────────────────────────
    def _resolve(self, text: str, run: Run, node: Node, task: str) -> str:
        """模板占位符解析：{task} 总任务 / {节点id} 前驱输出 / {prev} 上一条输出 / {kb} 知识库检索"""
        out = text
        if "{task}" in out:
            out = out.replace("{task}", task)
        for nid, nr in run.nodes.items():
            out = out.replace("{" + nid + "}", nr.output)
            out = out.replace("{" + nid + ".reason}", nr.verify_reason)
        if "{prev}" in out:
            out = out.replace("{prev}", self._prev_output(run, node) or "")
        if "{kb}" in out:
            out = out.replace("{kb}", self._kb_context(node, task))
        return out

    @staticmethod
    def _kb_context(node: Node, task: str) -> str:
        """知识库检索（RAG）：按节点绑定的知识库检索 top-k 片段"""
        kb_name = node.config.get("kb")
        if not kb_name:
            return ""
        from .. import rag
        hits = rag.search(kb_name, task[:300], k=int(node.config.get("kb_topk", 2)))
        if not hits:
            return "（知识库无匹配内容）"
        parts = []
        for i, h in enumerate(hits, 1):
            parts.append(f"[知识库片段{i}·相关度{h['score']}]\n{h['chunk']}")
        return "\n\n".join(parts)

    @staticmethod
    def _prev_output(run: Run, node: Node) -> str:
        return "".join(run.nodes[nid].output for nid in node.config.get("inputs", []) if nid in run.nodes)

    # ── 节点执行 ─────────────────────────────────────────────
    def _run_agent_node(self, run: Run, node: Node, task: str) -> None:
        nr = run.nodes[node.id]
        role = node.config.get("role") or node.agent_id
        profile = self.scheduler.select(role)          # ★ 能力画像调度
        if not profile:
            raise RuntimeError(f"角色 {role} 无可用 Agent")
        input_text = self._resolve(node.config.get("input_template", "{prev}\n{task}"), run, node, task)
        nr.input = input_text
        nr.agent_id = profile.id

        self._emit(run, nr, "running", agent=profile.id, role=role)
        self.scheduler.acquire(profile)
        try:
            verifier = CrossVerifier(
                threshold=float(node.config.get("verify_threshold", 7.0)),
                rules=node.config.get("verify_rules") or {},
                provider=profile.provider,
            )
            engine = SelfLoopEngine(verifier, max_rounds=int(node.config.get("max_rounds", 3)))
            node_tools = node.config.get("tools") or []

            def on_round(rnd: int, passed: bool, rec) -> None:
                nr.loops.append(rec)
                self._emit(run, nr, "looping" if not passed else "verifying",
                           round=rnd, score=rec.score, feedback=rec.feedback)

            result = engine.run(profile, input_text, tools=node_tools, on_round=on_round)
            nr.output = result.final_output
            nr.verify_score = result.final_score
            if result.accepted:
                nr.status = NodeStatus.DONE
            else:
                nr.status = NodeStatus.DONE   # 达到最大轮次仍接受最终产出，验证报告记录分数
                nr.verify_reason = "达到最大修正轮数"
            self._emit(run, nr, "done", rounds=len(result.records),
                       accepted=result.accepted)
        except Exception as e:
            nr.error = str(e)
            self._emit(run, nr, "failed", error=str(e))
        finally:
            self.scheduler.release(profile)

    def _run_verify_node(self, run: Run, node: Node, task: str) -> None:
        """独立验证节点：对指定前驱输出做交叉验证"""
        nr = run.nodes[node.id]
        target = node.config.get("target")
        self._emit(run, nr, "verifying", target=target)
        try:
            output = run.nodes[target].output if target in run.nodes else ""
            verifier = CrossVerifier(
                threshold=float(node.config.get("verify_threshold", 7.0)),
                rules=node.config.get("verify_rules") or {})
            v = verifier.verify(task, output)
            nr.output = output
            nr.verify_score = v.score
            nr.verify_reason = v.reason
            nr.status = NodeStatus.DONE
            self._emit(run, nr, "done", passed=v.passed, score=v.score, reason=v.reason)
        except Exception as e:
            nr.error = str(e)
            self._emit(run, nr, "failed", error=str(e))

    def _run_condition_node(self, run: Run, node: Node, task: str) -> None:
        """条件分支节点：next[0]=条件真，next[1]=条件假"""
        nr = run.nodes[node.id]
        expr = node.config.get("condition", "")   # 如 "verify_score>=7"
        cond = True
        if expr.startswith("verify_score"):
            # 取指定目标节点（或上一个节点）的验证分数
            target = node.config.get("target")
            score = run.nodes[target].verify_score if target in run.nodes else None
            op = ">=" if ">=" in expr else "<"
            thresh = float(expr.split(op)[1])
            cond = (score >= thresh) if (score is not None and op == ">=") else (score is not None and score < thresh)
        nr.status = NodeStatus.DONE
        nr.output = "true" if cond else "false"
        self._emit(run, nr, "done", branch=cond)

    # ── 主执行 ───────────────────────────────────────────────
    def execute(self, workflow: Workflow, task: str) -> Run:
        run = Run(id=f"run-{int(time.time()*1000)}", workflow_id=workflow.id)
        for n in workflow.nodes:
            run.nodes[n.id] = NodeRun(node_id=n.id)
        with self._lock:
            self._runs[run.id] = run

        nodes = {n.id: n for n in workflow.nodes}
        preds: dict[str, set[str]] = defaultdict(set)
        succ: dict[str, list[str]] = defaultdict(list)
        for n in workflow.nodes:
            for nxt in n.next:
                succ[n.id].append(nxt)
                preds[nxt].add(n.id)

        # parallel 节点：branches 是它的子任务（前驱=parallel，完成后 parallel 才 DONE）
        for n in workflow.nodes:
            if n.type == NodeType.PARALLEL:
                for b in n.config.get("branches", []):
                    succ[n.id].append(b)
                    preds[b].add(n.id)

        # DFS 构建生成树，标记回边（循环边）——回边前驱不阻塞节点首次执行
        back_edges: set[tuple[str, str]] = set()
        visited: set[str] = set()
        _seq = [0]

        def _next_seq() -> int:
            _seq[0] += 1
            return _seq[0]

        def dfs(nid: str) -> None:
            visited.add(nid)
            for s in succ[nid]:
                if s in visited:
                    back_edges.add((nid, s))     # 指向已访问节点 = 回边（循环）
                else:
                    dfs(s)

        dfs(workflow.entry)
        for nid in nodes:                        # 孤立节点（入口不可达）直接跳过
            if nid not in visited:
                run.nodes[nid].status = NodeStatus.SKIPPED
                self._emit(run, run.nodes[nid], "skipped", reason="入口不可达")

        def run_node(nid: str) -> None:
            n = nodes[nid]
            nr = run.nodes[nid]
            nr.visit_count += 1
            nr.status = NodeStatus.RUNNING
            if n.type == NodeType.AGENT:
                self._run_agent_node(run, n, task)
            elif n.type == NodeType.VERIFY:
                self._run_verify_node(run, n, task)
            elif n.type == NodeType.CONDITION:
                self._run_condition_node(run, n, task)
            elif n.type == NodeType.PARALLEL:
                _run_parallel_node(run, n, nodes, run_node)
            nr.last_seq = _next_seq()

        def _run_parallel_node(run, node, nodes, runner) -> None:
            nr = run.nodes[node.id]
            self._emit(run, nr, "running")
            branches = node.config.get("branches", [])
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(branches)) as ex:
                list(ex.map(runner, branches))
            nr.status = NodeStatus.DONE
            self._emit(run, nr, "done")

        # 起始：entry
        run_node(workflow.entry)
        # 迭代：前驱完成且执行次数未达上限的节点（支持工作流级有限循环）
        progress = True
        while progress:
            progress = False
            for nid, n in nodes.items():
                nr = run.nodes[nid]
                max_v = int(n.config.get("max_visits", 1))
                if nr.visit_count >= max_v:
                    continue
                if nr.status == NodeStatus.SKIPPED:
                    continue
                if preds[nid] and not all(
                        run.nodes[p].status in (NodeStatus.DONE, NodeStatus.SKIPPED)
                        for p in preds[nid] if (p, nid) not in back_edges):
                    continue
                # 变化驱动重跑：已执行的节点，仅当存在非回边前驱比它更晚执行过（修正链传播）才重跑
                if nr.visit_count > 0:
                    stale = False
                    for p in preds[nid]:
                        if (p, nid) in back_edges:
                            continue
                        pnr = run.nodes[p]
                        if pnr.last_seq > nr.last_seq and pnr.visit_count > 0:
                            stale = True
                            break
                    if not stale:
                        continue
                if nr.visit_count == 0:
                    # 首次执行前：前驱失败 → 跳过；条件活跃性判定（已执行过的节点由前驱重跑驱动，不再判定）
                    if preds[nid] and any(run.nodes[p].status == NodeStatus.FAILED for p in preds[nid]):
                        nr.status = NodeStatus.SKIPPED
                        self._emit(run, nr, "skipped", reason="前驱失败")
                        continue
                    active = False
                    for p in preds[nid]:
                        pn = nodes[p]
                        if pn.type == NodeType.CONDITION:
                            idx = succ[p].index(nid)
                            cond_true = run.nodes[p].output == "true"
                            if (idx == 0) == cond_true:
                                active = True      # 条件选中了指向本节点的分支
                        else:
                            active = True          # 非条件前驱 = 活跃路径
                    if not active:
                        # 若所有条件前驱都已用尽执行次数，则本节点最终跳过
                        cond_preds = [p for p in preds[nid] if nodes[p].type == NodeType.CONDITION]
                        if all(run.nodes[p].visit_count >= int(nodes[p].config.get("max_visits", 1))
                               for p in cond_preds):
                            nr.status = NodeStatus.SKIPPED
                            self._emit(run, nr, "skipped", reason="条件分支未选中")
                        continue
                run_node(nid)
                progress = True

        # 汇总（残留 PENDING 标为 SKIPPED）
        for nid, nr in run.nodes.items():
            if nr.status == NodeStatus.PENDING:
                nr.status = NodeStatus.SKIPPED
                self._emit(run, nr, "skipped", reason="未达激活条件")

        # 汇总
        run.status = NodeStatus.DONE
        run.finished_at = datetime.now()
        terminal = [nid for nid in nodes if not succ[nid] or all(
            run.nodes[s].status in (NodeStatus.DONE, NodeStatus.SKIPPED) for s in succ[nid])]
        run.final_output = "\n\n".join(run.nodes[t].output for t in terminal if run.nodes[t].output)
        return run

    def get_run(self, run_id: str) -> Optional[Run]:
        return self._runs.get(run_id)
