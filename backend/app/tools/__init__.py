"""工具注册中心：Function Calling 工具（联网搜索/字数统计/时间）
赛题考点「工具与外部系统集成」：支持 Function Calling 与 MCP 双协议工具。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from agents import function_tool

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 research"}


# ══════════════════ 底层实现（可独立测试） ══════════════════

def _search_web_impl(query: str) -> str:
    """联网搜索（必应 + 百度百科）"""
    results = []
    # 源1：必应搜索
    try:
        url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=zh-cn"
        req = urllib.request.Request(url, headers=_HEADERS)
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="replace")
        items = re.findall(r'<li class="b_algo".*?<h2><a[^>]*>(.*?)</a></h2>.*?<p[^>]*>(.*?)</p>',
                           html, re.S)
        for title, snip in items[:5]:
            title = re.sub(r"<[^>]+>", "", title).strip()
            snip = re.sub(r"<[^>]+>", "", snip).strip()
            if title:
                results.append(f"【必应】{title}\n{snip[:150]}")
    except Exception as e:
        results.append(f"【必应】搜索失败: {str(e)[:60]}")

    # 源2：百度百科（结构化摘要）
    try:
        api = ("https://baike.baidu.com/api/openapi/BaikeLemmaCardApi?scope=103&format=json"
               "&appid=379020&bk_key=" + urllib.parse.quote(query))
        req = urllib.request.Request(api, headers=_HEADERS)
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace"))
        for card in data.get("card", [])[:2]:
            abstract = re.sub(r"<[^>]+>", "", card.get("abstract", "")).strip()
            if abstract:
                results.append(f"【百科】{card.get('name', query)}\n{abstract[:150]}")
    except Exception as e:
        results.append(f"【百科】查询失败: {str(e)[:60]}")

    if not results:
        return "未找到相关信息"
    return "\n\n".join(results)


def _count_chars_impl(text: str) -> str:
    """字数统计"""
    chars = len(text.replace("\n", "").replace(" ", ""))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    return f"总字符数 {chars}（含标点），英文单词/数字 {words} 个"


def _get_current_time_impl() -> str:
    """当前北京时间"""
    now = datetime.now(timezone(timedelta(hours=8)))
    return f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M')}（北京时间）"


# ══════════════════ function_tool 包装 ══════════════════

@function_tool
def search_web(query: str) -> str:
    """联网搜索最新信息（必应搜索 + 百度百科），用于事实核查与资料补充。
    参数 query: 搜索关键词。返回：相关结果的标题与摘要（最多5条）。"""
    return _search_web_impl(query)


@function_tool
def count_chars(text: str) -> str:
    """统计文本的字数（含中文/英文/标点）。用于发布前的字数合规检查。
    参数 text: 待统计的文本。返回：字数统计结果。"""
    return _count_chars_impl(text)


@function_tool
def get_current_time() -> str:
    """获取当前日期和时间（北京时间）。"""
    return _get_current_time_impl()


@function_tool
def image_generate(prompt: str) -> str:
    """生成图片。平台自动调度多个图像生成模型（豆包Seedream/GLM CogView/Pollinations）完成文生图，
    图片自动保存到平台文件库。
    参数 prompt: 详细的图片描述（包含主体、风格、色调、构图）。返回：图片的平台内访问URL。"""
    from .files import generate_image
    return generate_image(prompt)


@function_tool
def save_file(filename: str, content: str) -> str:
    """保存文件到平台文件库。用于产出表格(CSV)、文档(Markdown)、网页(HTML)等文件。
    参数 filename: 文件名（含扩展名，如 report.md / data.csv）
    参数 content: 文件完整内容。
    返回：文件的平台内访问URL。"""
    from .files import save_output_file
    return save_output_file(filename, content)


# ══════════════════ 注册表 ══════════════════
TOOL_REGISTRY: dict[str, object] = {
    "search_web": search_web,
    "count_chars": count_chars,
    "get_current_time": get_current_time,
    "image_generate": image_generate,
    "save_file": save_file,
}

TOOL_META = {
    "search_web": {"name": "search_web", "label": "联网搜索", "protocol": "Function Calling",
                   "desc": "必应搜索+百度百科，事实核查"},
    "count_chars": {"name": "count_chars", "label": "字数统计", "protocol": "Function Calling",
                    "desc": "发布前字数合规检查"},
    "get_current_time": {"name": "get_current_time", "label": "当前时间", "protocol": "Function Calling",
                         "desc": "北京时间查询"},
    "image_generate": {"name": "image_generate", "label": "AI 图像生成", "protocol": "Function Calling",
                       "desc": "多模型调度文生图（Seedream/CogView/Pollinations）"},
    "save_file": {"name": "save_file", "label": "文件产出", "protocol": "Function Calling",
                  "desc": "保存表格CSV/文档MD/网页HTML到平台文件库"},
    "calc": {"name": "calc", "label": "科学计算器", "protocol": "MCP stdio",
             "desc": "自研 MCP Server 提供的四则运算/乘方工具"},
}


def resolve_tools(names: list[str]) -> list[object]:
    """按名称解析 Function Calling 工具；MCP 工具返回空（由 MCP server 提供）"""
    return [TOOL_REGISTRY[n] for n in names if n in TOOL_REGISTRY]


def mcp_tool_names(names: list[str]) -> list[str]:
    """过滤出需要 MCP server 提供的工具名"""
    return [n for n in names if n not in TOOL_REGISTRY and n in TOOL_META]
