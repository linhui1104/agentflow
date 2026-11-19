"""交叉验证器 ★创新点2：生成者-评审者-仲裁者三段式验证 + 双通道置信度
LLM 评审通道（独立视角打分）+ 确定性规则通道（长度/非空/要素检查），
双通道加权合成置信度，低于阈值触发 Self-Loop 重做。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents import Agent as SDKAgent, Runner

from .. import llm

REVIEWER_PROMPT = """你是一名独立质量评审员（Reviewer）。请对以下产出内容进行严格评审：
1. 是否完整响应了任务要求（内容完整性）
2. 事实与逻辑是否自洽（准确性）
3. 格式与表达是否符合该任务类型（规范性）

任务要求：
{task}

待评审产出：
{output}

请输出两行：
第一行：分数（1-10 的整数，10 为最佳）
第二行：评审意见（一句话，指出主要问题；若无明显问题写"合格"）
"""


@dataclass
class VerifyResult:
    score: float                 # 合成置信度（0-10）
    passed: bool                 # 是否通过阈值
    llm_score: float = 0.0       # 评审者打分
    rule_score: float = 0.0      # 规则通道得分（0-10）
    reason: str = ""             # 评审意见
    details: dict = field(default_factory=dict)


def rule_check(output: str, rules: dict) -> tuple[float, list[str]]:
    """确定性规则通道：返回 (得分0-10, 违规项列表)"""
    problems = []
    if not output or not output.strip():
        return 0.0, ["输出为空"]
    if rules.get("min_length") and len(output) < rules["min_length"]:
        problems.append(f"长度不足 {rules['min_length']} 字符")
    if rules.get("forbidden"):
        for w in rules["forbidden"]:
            if w in output:
                problems.append(f"含违禁词: {w}")
    if rules.get("required"):
        for w in rules["required"]:
            if w not in output:
                problems.append(f"缺少必要要素: {w}")
    score = 10.0 - 2.5 * len(problems)
    return max(0.0, score), problems


def llm_review(task: str, output: str, provider: str = None) -> tuple[float, str]:
    """LLM 评审通道：独立评审 Agent 打分"""
    reviewer = SDKAgent(
        name="reviewer",
        instructions="你是严格的质量评审员，只输出分数和意见，不多说其他内容。",
        model=llm.build_model(provider),
    )
    prompt = REVIEWER_PROMPT.format(task=task[:2000], output=output[:4000])
    result = Runner.run_sync(reviewer, prompt, max_turns=1)
    text = str(result.final_output or "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*分", text) or re.match(r"\s*(\d+(?:\.\d+)?)", text)
    score = float(m.group(1)) if m else 5.0
    score = min(10.0, max(0.0, score))
    reason = text.splitlines()[1].strip() if len(text.splitlines()) > 1 else text
    return score, reason


class CrossVerifier:
    """双通道交叉验证器"""

    def __init__(self, threshold: float = 7.0, rules: dict = None, provider: str = None) -> None:
        self.threshold = threshold
        self.rules = rules or {}
        self.provider = provider

    def verify(self, task: str, output: str) -> VerifyResult:
        rule_score, problems = rule_check(output, self.rules)
        try:
            llm_score, reason = llm_review(task, output, self.provider)
        except Exception as e:   # LLM 通道故障时降级为规则通道
            llm_score, reason = 5.0, f"评审通道异常: {e}"
        # 双通道加权：LLM 0.7 + 规则 0.3
        score = 0.7 * llm_score + 0.3 * rule_score
        return VerifyResult(
            score=round(score, 1),
            passed=score >= self.threshold,
            llm_score=round(llm_score, 1),
            rule_score=round(rule_score, 1),
            reason=reason,
            details={"problems": problems, "threshold": self.threshold},
        )
