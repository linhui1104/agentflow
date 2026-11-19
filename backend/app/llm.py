"""LLM 网关：provider 动态配置 + openai-agents 模型包装
API key 全部来自 data/providers.json（用户通过界面填入），代码零内置。
"""
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, set_default_openai_client, set_tracing_disabled

from . import config

_clients = {}


def _make_client(provider: str) -> AsyncOpenAI:
    """新建 OpenAI 兼容异步客户端。
    注：openai-agents 的 run_sync 每次调用创建新 event loop，
    httpx AsyncClient 绑定首次使用的 loop，因此 client 不可跨调用复用。"""
    p = config.get_provider(provider)
    if not p:
        raise ValueError(f"未知 provider: {provider}")
    if not p.get("api_key"):
        raise RuntimeError(
            f"provider {provider}（{p.get('label', '')}）未配置 API key —— "
            "请在平台「模型配置」面板填入")
    return AsyncOpenAI(base_url=p["base_url"], api_key=p["api_key"], timeout=120)


def build_model(provider: str = None) -> OpenAIChatCompletionsModel:
    """构建一次调用专用的模型包装（每次新建 client，规避跨 loop 复用问题）"""
    provider = provider or config.DEFAULT_PROVIDER
    p = config.get_provider(provider)
    if not p:
        raise ValueError(f"未知 provider: {provider}")
    return OpenAIChatCompletionsModel(model=p["model"], openai_client=_make_client(provider))


def get_client(provider: str = None) -> AsyncOpenAI:
    return _make_client(provider or config.DEFAULT_PROVIDER)


def invalidate(provider: str = None) -> None:
    """配置变更后清理客户端缓存"""
    global _clients
    if provider:
        _clients.pop(provider, None)
    else:
        _clients = {}


def test_provider(provider: str) -> dict:
    """测试 provider 连通性：发一条最小请求"""
    try:
        client = _make_client(provider)
        p = config.get_provider(provider)
        import asyncio
        async def _t():
            r = await client.chat.completions.create(
                model=p["model"], messages=[{"role": "user", "content": "回复OK"}],
                max_tokens=5, timeout=30)
            return r.choices[0].message.content
        out = asyncio.run(_t())
        return {"ok": True, "reply": out}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def setup_default() -> None:
    """初始化全局默认：关闭 tracing（避免网络噪音）+ 设置默认客户端"""
    set_tracing_disabled(True)
    try:
        set_default_openai_client(_make_client(config.DEFAULT_PROVIDER))
    except RuntimeError:
        pass   # 默认 provider 未配 key 时不阻塞启动（用户可先配置再执行）


def provider_label(provider: str) -> str:
    p = config.get_provider(provider)
    return (p or {}).get("label", provider)
