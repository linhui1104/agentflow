"""通用工作流模板库：展示平台的跨场景通用性
模板函数统一返回 (Workflow, [AgentProfile])。
"""
from ..models import AgentProfile, Node, NodeType, Workflow


# ═══════════ 模板2：数据分析管线 ═══════════
def data_analysis() -> tuple[Workflow, list[AgentProfile]]:
    agents = [
        AgentProfile(id="da-requirement", name="需求分析师", role="分析需求",
                     system_prompt="你是数据分析需求分析师。把用户的模糊需求转化为明确的分析目标、"
                                   "所需数据字段、分析维度与输出形式。输出简洁清单。中文。"),
        AgentProfile(id="da-cleaner", name="数据清洗师", role="数据清洗",
                     system_prompt="你是数据清洗师。针对给定的分析需求与数据字段，给出数据清洗方案："
                                   "缺失值处理、异常值检测、格式标准化。输出可执行步骤。中文。"),
        AgentProfile(id="da-analyst", name="数据分析师", role="数据分析",
                     system_prompt="你是资深数据分析师。根据清洗方案与分析目标，设计分析方法"
                                   "（描述统计/相关性/趋势/分组对比等）并给出关键分析结论。中文。"),
        AgentProfile(id="da-visual", name="可视化顾问", role="可视化建议",
                     system_prompt="你是数据可视化顾问。根据分析结论，推荐图表类型（柱状/折线/散点/热力等）"
                                   "并说明每张图的表达意图。中文。"),
        AgentProfile(id="da-writer", name="报告撰写人", role="报告撰写",
                     system_prompt="你是数据分析报告撰写人。把需求、清洗方案、分析结论与可视化建议"
                                   "整合为结构化分析报告（Markdown，# 标题开头）。中文。"),
        AgentProfile(id="da-reviewer", name="报告审核员", role="报告审核",
                     system_prompt="你是报告审核员。检查报告逻辑完整性、结论与数据一致性。中文。"),
    ]
    nodes = [
        Node(id="req", type=NodeType.AGENT, agent_id="da-requirement",
             config={"input_template": "用户需求：{task}",
                     "verify_rules": {"min_length": 30}}, next=["clean"]),
        Node(id="clean", type=NodeType.AGENT, agent_id="da-cleaner",
             config={"input_template": "分析目标与数据字段：\n{req}", "verify_rules": {"min_length": 30}},
             next=["analyze"]),
        Node(id="analyze", type=NodeType.AGENT, agent_id="da-analyst",
             config={"input_template": "清洗方案：\n{clean}", "verify_rules": {"min_length": 50}},
             next=["visual"]),
        Node(id="visual", type=NodeType.AGENT, agent_id="da-visual",
             config={"input_template": "分析结论：\n{analyze}", "verify_rules": {"min_length": 30}},
             next=["write"]),
        Node(id="write", type=NodeType.AGENT, agent_id="da-writer",
             config={"input_template": "需求：{req}\n清洗：{clean}\n结论：{analyze}\n可视化：{visual}\n"
                                       "请整合为完整分析报告（# 标题开头）",
                     "verify_rules": {"min_length": 400, "required": ["#"]},
                     "verify_threshold": 7.0, "max_rounds": 2}, next=["review"]),
        Node(id="review", type=NodeType.VERIFY,
             config={"target": "write", "verify_threshold": 7.0}, next=[]),
    ]
    wf = Workflow(id="data-analysis", name="数据分析管线",
                  description="需求澄清→清洗方案→分析→可视化建议→报告撰写→审核",
                  nodes=nodes, entry="req")
    return wf, agents


# ═══════════ 模板3：市场调研管线 ═══════════
def research_report() -> tuple[Workflow, list[AgentProfile]]:
    agents = [
        AgentProfile(id="rs-planner", name="调研策划师", role="调研策划",
                     system_prompt="你是市场调研策划师。根据调研主题，拆解调研维度："
                                   "市场规模、竞品格局、用户画像、趋势风险。输出调研框架。中文。"),
        AgentProfile(id="rs-searcher", name="情报搜集员", role="情报搜集",
                     system_prompt="你是情报搜集员。按调研框架逐项联网搜索，调用 search_web 工具获取"
                                   "真实信息，并标注每条信息的来源与时间。严禁编造数据。中文。"),
        AgentProfile(id="rs-summarizer", name="资料综述员", role="资料综述",
                     system_prompt="你是资料综述员。把搜集的情报按框架整理为结构化综述，"
                                   "保留数据来源标注，指出信息缺口。中文。"),
        AgentProfile(id="rs-writer", name="调研报告撰写人", role="报告撰写",
                     system_prompt="你是调研报告撰写人。把综述整合为完整调研报告（# 标题开头）："
                                   "结论先行、数据支撑、缺口说明。中文。"),
        AgentProfile(id="rs-reviewer", name="事实核查员", role="报告审核",
                     system_prompt="你是事实核查员。检查报告中每个数据是否有来源支撑，"
                                   "无来源的结论必须标记存疑。中文。"),
    ]
    nodes = [
        Node(id="plan", type=NodeType.AGENT, agent_id="rs-planner",
             config={"input_template": "调研主题：{task}", "verify_rules": {"min_length": 30}},
             next=["search"]),
        Node(id="search", type=NodeType.AGENT, agent_id="rs-searcher",
             config={"input_template": "按以下框架联网搜集情报（必须调用 search_web 工具，标注来源）：\n{plan}",
                     "tools": ["search_web"], "verify_rules": {"min_length": 100}},
             next=["summary"]),
        Node(id="summary", type=NodeType.AGENT, agent_id="rs-summarizer",
             config={"input_template": "情报资料：\n{search}", "verify_rules": {"min_length": 100}},
             next=["write"]),
        Node(id="write", type=NodeType.AGENT, agent_id="rs-writer",
             config={"input_template": "综述：\n{summary}\n请撰写完整调研报告（# 标题开头）",
                     "verify_rules": {"min_length": 400, "required": ["#"]},
                     "verify_threshold": 7.0, "max_rounds": 2}, next=["factcheck"]),
        Node(id="factcheck", type=NodeType.VERIFY,
             config={"target": "write", "verify_threshold": 7.0}, next=[]),
    ]
    wf = Workflow(id="research-report", name="市场调研管线",
                  description="调研策划→联网情报搜集→资料综述→报告撰写→事实核查",
                  nodes=nodes, entry="plan")
    return wf, agents


# ═══════════ 模板4：公众号完整作品管线（真实配图 + 成品文件）═══════════
def wechat_article() -> tuple[Workflow, list[AgentProfile]]:
    agents = [
        AgentProfile(id="wa-planner", name="选题策划师", role="选题策划",
                     system_prompt="你是资深公众号选题策划师。根据用户主题产出1个具体选题："
                                   "目标读者、标题方向、核心卖点。输出简洁（100字内）。中文。"),
        AgentProfile(id="wa-outliner", name="大纲架构师", role="内容大纲",
                     system_prompt="你是内容大纲架构师。根据选题输出结构化文章大纲（3-5部分）。Markdown列表。中文。"),
        AgentProfile(id="wa-writer", name="资深撰稿人", role="内容撰写",
                     system_prompt="你是资深公众号撰稿人。根据大纲撰写完整文章：第一行为#标题，"
                                   "正文有感染力、有观点、有案例，Markdown格式。中文。"),
        AgentProfile(id="wa-illustrator", name="插画设计师", role="图像生成",
                     system_prompt="你是公众号插画设计师。根据文章主题与大纲，为文章设计配图："
                                   "调用 image_generate 工具生成1张封面图（主题意象，扁平插画风格，"
                                   "明亮色调，包含主题视觉隐喻）。生成后输出图片URL，一行一张。"),
        AgentProfile(id="wa-reviewer", name="内容审核员", role="内容审核",
                     system_prompt="你是公众号内容审核员。检查文章质量：标题吸引力、结构完整性、"
                                   "语言流畅度、事实准确性。输出分数（1-10）和意见。中文。"),
        AgentProfile(id="wa-publisher", name="排版发布员", role="排版发布",
                     system_prompt="你是公众号排版编辑。把文章正文与配图URL组装成一篇完整的公众号推文"
                                   "（Markdown格式，图片用 ![](URL) 嵌入正确位置，标题、正文、"
                                   "配图齐全），然后调用 save_file 工具保存为 article.md，"
                                   "最后输出文件URL和文章摘要。"),
    ]
    nodes = [
        Node(id="topic", type=NodeType.AGENT, agent_id="wa-planner",
             config={"input_template": "{task}", "verify_rules": {"min_length": 20}},
             next=["outline"]),
        Node(id="outline", type=NodeType.AGENT, agent_id="wa-outliner",
             config={"input_template": "根据选题生成大纲：\n{topic}", "verify_rules": {"min_length": 50}},
             next=["gen"]),
        Node(id="gen", type=NodeType.PARALLEL,
             config={"branches": ["write", "illustrate"]}, next=["audit"]),
        Node(id="write", type=NodeType.AGENT, agent_id="wa-writer",
             config={"input_template": "根据大纲撰写公众号文章（第一行为#标题）：\n{outline}",
                     "verify_rules": {"min_length": 300, "required": ["#"]},
                     "verify_threshold": 7.0, "max_rounds": 2},
             next=[]),
        Node(id="illustrate", type=NodeType.AGENT, agent_id="wa-illustrator",
             config={"input_template": "文章主题：{topic}\n大纲：{outline}\n"
                                       "请调用 image_generate 工具生成封面配图。",
                     "tools": ["image_generate"],
                     "verify_rules": {"min_length": 10}},
             next=[]),
        Node(id="audit", type=NodeType.VERIFY,
             config={"target": "write", "verify_threshold": 7.0}, next=["gate"]),
        Node(id="gate", type=NodeType.CONDITION,
             config={"condition": "verify_score>=7", "target": "audit"},
             next=["publish", "publish"]),   # 双分支都到发布（润色内置于撰写Self-Loop）
        Node(id="publish", type=NodeType.AGENT, agent_id="wa-publisher",
             config={"input_template": "文章正文：\n{write}\n\n配图URL：\n{illustrate}\n\n"
                                       "请组装完整推文（Markdown，图片嵌入正文），"
                                       "调用 save_file 保存为 article.md 并输出文件URL。",
                     "tools": ["save_file"],
                     "verify_rules": {"min_length": 100}},
             next=[]),
    ]
    wf = Workflow(id="wechat-article", name="公众号成品管线",
                  description="选题→大纲→并行[撰写∥AI配图]→审核→组装成品文件（真实配图）",
                  nodes=nodes, entry="topic")
    return wf, agents
