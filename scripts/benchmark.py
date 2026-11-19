"""基线对比基准测试：三种调度策略 + 并发负载测试
实验组：能力画像调度（自研）
基线1：单 Agent 串行（固定最强候选，赛题明确要求对比）
基线2：轮询调度（Round-Robin）
指标：任务成功率（验证≥7.0）、平均验证分、总耗时、平均耗时

输出：data/benchmark.json（方案书"测试用例与性能评估"引用）
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import llm
from app.agents import AgentRegistry, AgentFactory
from app.core.scheduler import CapabilityScheduler, round_robin_select
from app.core.verifier import CrossVerifier

llm.setup_default()

# ── 测试环境 ────────────────────────────────────────────────────
TASKS = [
    "写一篇大学生时间管理推文（300字以上，第一行#标题）",
    "写一篇考研复试经验推文（300字以上，第一行#标题）",
    "写一篇宿舍关系处理推文（300字以上，第一行#标题）",
    "写一篇实习面试技巧推文（300字以上，第一行#标题）",
    "写一篇四六级备考攻略推文（300字以上，第一行#标题）",
    "写一篇大学生理财入门推文（300字以上，第一行#标题）",
]
THRESHOLD = 7.0
VERIFY_RULES = {"min_length": 300, "required": ["#"]}

WRITER_A = {
    "id": "writer-a", "name": "资深撰稿人", "role": "内容撰写", "provider": "deepseek",
    "system_prompt": "你是资深公众号撰稿人。根据任务撰写完整文章：第一行为#标题，"
                     "正文有感染力、有观点、有案例，Markdown格式。中文。",
}
WRITER_B = {
    "id": "writer-b", "name": "实习撰稿人", "role": "内容撰写", "provider": "glm",
    "system_prompt": "你是实习撰稿人。根据任务撰写文章：第一行为#标题，正文完整通顺，Markdown格式。中文。",
}


def make_registry() -> AgentRegistry:
    from app.models import AgentProfile
    r = AgentRegistry()
    r.register(AgentProfile(**WRITER_A))
    r.register(AgentProfile(**WRITER_B))
    return r


def run_one(agent, task: str, verifier: CrossVerifier) -> dict:
    """执行单任务并验证，返回指标"""
    t0 = time.time()
    try:
        output = AgentFactory.run(agent, task)
        ok = True
    except Exception as e:
        output, ok = "", False
    elapsed = time.time() - t0
    if ok:
        v = verifier.verify(task, output)
        return {"task": task[:18], "agent": agent.id, "ok": True,
                "elapsed": round(elapsed, 1), "score": v.score,
                "passed": v.passed, "output_len": len(output)}
    return {"task": task[:18], "agent": agent.id, "ok": False,
            "elapsed": round(elapsed, 1), "score": 0.0, "passed": False, "output_len": 0}


def run_batch(registry, verifier, strategy: str) -> dict:
    """顺序跑完全部任务（选择策略不同）"""
    from app.models import AgentProfile
    sched = CapabilityScheduler(registry)
    rr_counter = {}
    records = []
    t0 = time.time()

    for task in TASKS:
        if strategy == "capability":
            agent = sched.select("内容撰写")
        elif strategy == "round_robin":
            agent = round_robin_select(registry, "内容撰写", rr_counter)
        else:  # serial_single: 固定最强候选
            agent = registry.get("writer-a")
        records.append(run_one(agent, task, verifier))
        # 模拟运行间隔负载归零
        time.sleep(0.3)

    total = time.time() - t0
    passed = sum(1 for r in records if r["passed"])
    scores = [r["score"] for r in records if r["ok"]]
    pick_ratio = sum(1 for r in records if r["agent"] == "writer-a") / len(records)
    return {
        "strategy": strategy,
        "tasks": len(records),
        "total_elapsed": round(total, 1),
        "avg_elapsed": round(sum(r["elapsed"] for r in records) / len(records), 1),
        "success_rate": round(passed / len(records), 3),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "writer_a_ratio": round(pick_ratio, 2),
        "records": records,
    }


def run_concurrent(registry, verifier, n: int = 8) -> dict:
    """并发负载测试：n 个任务并发涌入，画像调度做负载均衡"""
    from app.models import AgentProfile
    sched = CapabilityScheduler(registry)
    tasks = TASKS[:n] if n <= len(TASKS) else (TASKS * (n // len(TASKS) + 1))[:n]
    lock = threading.Lock()
    peak_load = {"max": 0}
    chosen = []

    def worker(task):
        agent = sched.select("内容撰写")
        sched.acquire(agent)
        with lock:
            chosen.append(agent.id)
            peak_load["max"] = max(peak_load["max"],
                                   sum(p.capability.load for p in registry.by_role("内容撰写")))
        try:
            r = run_one(agent, task, verifier)
        finally:
            sched.release(agent)
        return r

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        records = list(ex.map(worker, tasks))
    total = time.time() - t0

    # 串行对照：同样 n 个任务顺序执行
    t0s = time.time()
    for task in tasks:
        run_one(registry.get("writer-a"), task, verifier)
    serial_total = time.time() - t0s

    return {
        "mode": "concurrent",
        "tasks": n,
        "concurrent_elapsed": round(total, 1),
        "serial_elapsed": round(serial_total, 1),
        "speedup": round(serial_total / total, 2),
        "peak_load": peak_load["max"],
        "chosen": chosen,
        "pass_rate": round(sum(1 for r in records if r["passed"]) / len(records), 3),
    }


def main():
    print("=" * 60)
    print("AgentFlow 调度策略对比基准测试")
    print(f"阈值={THRESHOLD}  任务数={len(TASKS)}  候选: writer-a(deepseek) / writer-b(glm)")
    print("=" * 60)

    verifier = CrossVerifier(threshold=THRESHOLD, rules=VERIFY_RULES)

    results = {}
    for strategy, label in [("serial_single", "基线1: 单Agent串行"),
                            ("round_robin", "基线2: 轮询调度"),
                            ("capability", "实验组: 能力画像调度")]:
        print(f"\n▶ {label}")
        registry = make_registry()
        r = run_batch(registry, verifier, strategy)
        results[strategy] = r
        print(f"  总耗时 {r['total_elapsed']}s | 平均 {r['avg_elapsed']}s/任务 | "
              f"成功率 {r['success_rate']*100:.0f}% | 平均验证分 {r['avg_score']} | "
              f"writer-a占比 {r['writer_a_ratio']}")
        for rec in r["records"]:
            print(f"    {rec['task']:<20} {rec['agent']:<9} {rec['elapsed']:>5}s "
                  f"分数{rec['score']:>4} {'✓' if rec['passed'] else '✗'}")

    print("\n▶ 并发负载测试（8任务并发 vs 串行）")
    registry = make_registry()
    c = run_concurrent(registry, verifier, n=8)
    results["concurrent"] = c
    print(f"  并发 {c['concurrent_elapsed']}s vs 串行 {c['serial_elapsed']}s → "
          f"加速 {c['speedup']}x | 峰值负载 {c['peak_load']} | 通过率 {c['pass_rate']*100:.0f}%")
    print(f"  任务分流: {c['chosen']}")

    # 保存
    out = Path(__file__).resolve().parent.parent / "backend" / "data" / "benchmark.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
