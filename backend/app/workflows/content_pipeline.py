"""Demo 场景：多Agent智能内容生产管线
选题 → 大纲 → [撰写 ∥ 配图提示词]（并行）→ 独立审核 → 条件门 → 润色/直发 → 排版发布
- write 节点内置交叉验证 + Self-Loop（验证不过自动修正）
- audit 为独立验证节点，gate 为条件分支节点
"""
from ..models import AgentProfile, Node, NodeType, Workflow


def build_team() -> list[AgentProfile]:
    """内容生产团队（writer 注册两个候选实例，演示能力画像调度择优）"""
    return [
        AgentProfile(
            id="planner", name="选题策划师", role="选题策划",
            system_prompt="你是资深公众号选题策划师。根据用户给出的主题方向，"
                          "产出1个具体选题：包含目标读者画像、标题方向、核心卖点。输出简洁（100字内），中文。",
        ),
        AgentProfile(
            id="outliner", name="大纲架构师", role="内容大纲",
            system_prompt="你是内容大纲架构师。根据选题，输出结构化文章大纲（3-5个部分，"
                          "每部分1-2句要点）。用Markdown列表。中文。",
        ),
        AgentProfile(
            id="writer-a", name="资深撰稿人", role="内容撰写",
            system_prompt="你是资深公众号撰稿人。根据大纲撰写完整文章："
                          "第一行为#标题，正文有感染力、有观点、有案例，Markdown格式。中文。",
        ),
        AgentProfile(
            id="writer-b", name="实习撰稿人", role="内容撰写",
            provider="glm",
            system_prompt="你是实习撰稿人。根据大纲撰写文章：第一行为#标题，"
                          "正文完整通顺，Markdown格式。中文。",
        ),
        AgentProfile(
            id="illustrator", name="视觉设计师", role="视觉设计",
            system_prompt="你是公众号视觉设计师。根据文章主题，生成3条文生图提示词"
                          "（每条一行，英文prompt风格描述+风格词），供配图使用。",
        ),
        AgentProfile(
            id="publisher", name="排版编辑", role="排版发布",
            system_prompt="你是排版编辑。把给定材料组装成一篇可直接发布的公众号推文："
                          "标题、正文、配图位置标注。保持内容原样，只做排版整合。中文。",
        ),
        AgentProfile(
            id="polisher", name="润色编辑", role="内容润色",
            system_prompt="你是润色编辑。根据评审意见润色文章，提升质量，保持原文观点不变。"
                          "输出完整润色后的文章（含#标题）。中文。",
        ),
    ]


def build_workflow() -> Workflow:
    nodes = [
        Node(id="topic", type=NodeType.AGENT, agent_id="planner",
             config={"input_template": "{task}",
                     "verify_rules": {"min_length": 20}},
             next=["outline"]),
        Node(id="outline", type=NodeType.AGENT, agent_id="outliner",
             config={"input_template": "根据以下选题生成文章大纲：\n{topic}",
                     "verify_rules": {"min_length": 50}},
             next=["gen"]),
        Node(id="gen", type=NodeType.PARALLEL,
             config={"branches": ["write", "image"]},
             next=["audit"]),
        Node(id="write", type=NodeType.AGENT, agent_id=None,
             config={"role": "内容撰写",     # 角色调度：writer-a/writer-b 画像择优
                     "input_template": "根据以下大纲撰写公众号文章（第一行为#标题）。\n"
                                       "写作要求：严格遵循【团队知识库参考】中的风格规范；"
                                       "涉及统计数据、政策、时间等事实信息时，先调用 search_web 工具核实。\n"
                                       "大纲：\n{outline}\n\n【团队知识库参考】\n{kb}",
                     "kb": "style-guide", "kb_topk": 2,
                     "tools": ["search_web"],
                     "verify_rules": {"min_length": 300, "required": ["#"]},
                     "verify_threshold": 7.0, "max_rounds": 3},
             next=[]),   # 分支节点，由 gen 汇合
        Node(id="image", type=NodeType.AGENT, agent_id="illustrator",
             config={"input_template": "根据文章主题生成3条配图提示词。主题大纲：\n{outline}",
                     "verify_rules": {"min_length": 30}},
             next=[]),   # 分支节点，由 gen 汇合
        Node(id="audit", type=NodeType.VERIFY,
             config={"target": "write", "verify_threshold": 7.0},
             next=["gate"]),
        Node(id="gate", type=NodeType.CONDITION,
             config={"condition": "verify_score>=7", "target": "audit"},
             next=["publish", "polish"]),
        Node(id="polish", type=NodeType.AGENT, agent_id="polisher",
             config={"input_template": "根据审核意见润色以下文章：\n{write}\n\n审核意见：{audit.reason}",
                     "verify_rules": {"min_length": 300}},
             next=["publish"]),
        Node(id="publish", type=NodeType.AGENT, agent_id="publisher",
             config={"input_template":
                     "请组装最终推文。\n文章正文：\n{write}\n\n润色版（如有）：\n{polish}\n\n"
                     "配图提示词：\n{image}\n\n发布前先调用 count_chars 工具检查正文字数并在推文末尾标注统计结果。",
                     "tools": ["count_chars"],
                     "verify_rules": {"min_length": 100}},
             next=[]),
    ]
    return Workflow(
        id="content-pipeline", name="多Agent内容生产管线",
        description="选题→大纲→并行[撰写∥配图]→审核→条件分支→润色/直发→排版发布",
        nodes=nodes, entry="topic",
    )
