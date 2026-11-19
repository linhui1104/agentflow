"""端到端测试：直接调用引擎跑通内容生产管线（含工具调用+知识库）"""
import sys, time
from pathlib import Path
sys.path.insert(0, ".")

from app import llm, rag
from app.agents import AgentRegistry
from app.core.engine import WorkflowEngine
from app.workflows import content_pipeline

llm.setup_default()

# 加载知识库
rag.add_document("style-guide",
                 Path("data/kb_docs/style-guide.txt").read_text(encoding="utf-8"),
                 meta={"source": "style-guide.txt"})
print("知识库已加载:", rag.list_documents())

registry = AgentRegistry()
for p in content_pipeline.build_team():
    registry.register(p)

def on_event(run_id, node_id, payload):
    status = payload.get("status", "")
    extra = ""
    if status == "running":
        extra = f"agent={payload.get('agent', '')} role={payload.get('role', '')}"
    elif status in ("looping", "verifying"):
        extra = f"round={payload.get('round')} score={payload.get('score')}"
    elif status == "done":
        extra = f"score={payload.get('score', '')} rounds={payload.get('rounds', '')} passed={payload.get('passed', '')}"
    print(f"  [{run_id[:9]}] {node_id:<10} {status:<10} {extra}", flush=True)

engine = WorkflowEngine(registry, on_event=on_event)
wf = content_pipeline.build_workflow()

task = "写一篇面向大学生的公众号推文，主题：时间管理"
print(f"== 任务：{task} ==")
t0 = time.time()
run = engine.execute(wf, task)
elapsed = time.time() - t0

print(f"\n== 完成，耗时 {elapsed:.0f}s ==")
for nid, nr in run.nodes.items():
    flag = "✓" if nr.status.value == "done" else f"[{nr.status.value}]"
    score = f" 验证分={nr.verify_score}" if nr.verify_score is not None else ""
    loops = f" 修正轮数={len(nr.loops)}" if nr.loops else ""
    err = f" ERROR: {nr.error[:60]}" if nr.error else ""
    print(f"  {flag} {nid:<10} 输出{len(nr.output)}字{score}{loops}{err}")

print("\n===== 最终产出（发布节点）=====")
print(run.nodes.get("publish", run.nodes.get("topic")).output[:800])

# 调度器状态
print("\n===== 能力画像（调度后）=====")
for a in registry.all():
    c = a.capability
    print(f"  {a.id:<12} role={a.role:<6} 成功率={c.success_rate:.2f} 均耗时={c.avg_latency:.0f}s 负载={c.load}")
