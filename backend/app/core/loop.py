"""Self-Loop 引擎 ★创新点3：PDCA 执行-验证-修正循环 + Prompt 自适应优化
Plan（任务拆解/prompt生成）→ Do（Agent执行）→ Check（交叉验证）→ Act（修正），
每轮修正轨迹留痕，形成可复用的 Prompt 优化经验。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..agents import AgentFactory
from ..models import AgentProfile, LoopRecord
from .verifier import CrossVerifier


@dataclass
class LoopResult:
    final_output: str
    final_score: float
    rounds: int
    records: list[LoopRecord] = field(default_factory=list)
    accepted: bool = False


class SelfLoopEngine:
    """PDCA 循环执行器：最多 max_rounds 轮修正"""

    def __init__(self, verifier: CrossVerifier, max_rounds: int = 3) -> None:
        self.verifier = verifier
        self.max_rounds = max_rounds

    def run(self, agent: AgentProfile, task: str,
            tools: list[str] = None, on_round=None) -> LoopResult:
        """on_round(round_no, status, record) 回调供监控/日志使用"""
        output = ""
        records: list[LoopRecord] = []
        score = 0.0

        for rnd in range(self.max_rounds + 1):   # rnd 0 = 首次执行
            if rnd == 0:
                prompt = task
            else:
                # Act：把评审意见注入修正提示（Prompt 自适应优化）
                prompt = (
                    f"{task}\n\n"
                    f"【上一轮评审意见】{records[-1].feedback}\n"
                    f"【上一轮得分】{records[-1].score}/10\n"
                    "请针对以上意见全面改进输出质量，直接给出修改后的完整内容。"
                )

            output = AgentFactory.run(agent, prompt, tools=tools)
            v = self.verifier.verify(task, output)
            score = v.score

            if rnd == 0:
                rec = LoopRecord(round=rnd, feedback=v.reason, score=v.score,
                                 revised_prompt=prompt, output_before="", output_after=output)
            else:
                rec = LoopRecord(round=rnd, feedback=v.reason, score=v.score,
                                 revised_prompt=prompt,
                                 output_before=records[-1].output_after,
                                 output_after=output)
            records.append(rec)
            if on_round:
                on_round(rnd, v.passed, rec)

            if v.passed:
                return LoopResult(output, score, rnd, records, accepted=True)

        return LoopResult(output, score, self.max_rounds, records, accepted=False)
