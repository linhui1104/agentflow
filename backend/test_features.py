"""快速验证：搜索工具 / MCP工具 / 知识库检索 / LLM tool-calling 全链路"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import llm
llm.setup_default()

# 1) 底层函数直接调用
print("== 1. 搜索/统计/时间工具 ==")
from app.tools import _search_web_impl, _count_chars_impl, _get_current_time_impl
r = _search_web_impl("大学生 时间管理 调查数据")
print(r[:300])
print("---")
print(_count_chars_impl("这是一段测试文字，共多少个字符呢？"))
print(_get_current_time_impl())

# 2) 知识库检索
print("\n== 2. 知识库检索（style-guide） ==")
from app import rag
rag.add_document("style-guide",
                 Path("data/kb_docs/style-guide.txt").read_text(encoding="utf-8"),
                 meta={"source": "style-guide.txt"})
for q in ["文章结构规范", "配图风格要求", "语言风格"]:
    hits = rag.search("style-guide", q, k=2)
    print(f"查询[{q}] → {[(h['score'], h['chunk'][:25]) for h in hits]}")

# 3) LLM tool-calling 真实调用（带 search_web 工具的 Agent）
print("\n== 3. LLM 工具调用（deepseek + function_tool） ==")
from app.agents import AgentFactory
from app.models import AgentProfile
probe = AgentProfile(id="probe", name="工具测试", role="测试",
                     system_prompt="你是信息核查助手。回答用户问题时，对不确定的事实先调用 search_web 工具核实，"
                                   "再给出答案。回答要简洁。")
try:
    out = AgentFactory.run(probe, "2026年考研报名人数是多少？请用工具查证后回答。",
                           tools=["search_web"])
    print("Agent输出:", out[:400])
except Exception as e:
    print("FAIL:", str(e)[:300])

# 4) MCP 工具（calc）通过 openai-agents MCP stdio 调用
print("\n== 4. MCP 工具调用（自研 MCP Server） ==")
probe2 = AgentProfile(id="calc-probe", name="计算助手", role="测试",
                      system_prompt="你是计算助手。用户给出算式时，调用 calc 工具计算并给出结果。")
try:
    out = AgentFactory.run(probe2, "请用工具计算 (3+5)*2**3", tools=["calc"])
    print("MCP Agent输出:", out[:200])
except Exception as e:
    print("FAIL:", str(e)[:400])
