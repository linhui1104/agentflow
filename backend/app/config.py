"""全局配置：provider 动态加载（用户通过界面/API 填入 API key，代码不内置任何 key）
Provider 配置存于 data/providers.json，支持 7 家国产大模型接入模板。
"""
import json
import os
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROVIDERS_FILE = DATA_DIR / "providers.json"

_lock = threading.Lock()

DEFAULT_PROVIDER = "deepseek"

# ── 平台参数 ─────────────────────────────────────────────────────
MAX_LOOP_ROUNDS = 3          # Self-Loop 最多修正轮数
VERIFY_THRESHOLD = 7.0       # 交叉验证置信阈值（1-10 分制）
AGENT_MAX_TURNS = 15         # 单 Agent 最大轮次（工具调用循环上限，搜索类任务需要更多轮）


def _load_providers() -> dict:
    """读取 providers.json；不存在则创建空模板"""
    if PROVIDERS_FILE.exists():
        try:
            return json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _read_user_env() -> dict:
    """读取用户本地环境文件（~/.hermes/.env，如存在）+ 系统环境变量"""
    d = {}
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    d.update(os.environ)
    return d


def _migrate_from_env(providers: dict) -> dict:
    """一次性迁移：把用户本地已有的 key 迁入平台配置（不硬编码，仅读取用户环境）"""
    env = _read_user_env()
    env_map = {
        "deepseek": ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY"),
        "glm": ("GLM_BASE_URL", "GLM_API_KEY"),
        "doubao": ("DOUBAO_BASE_URL", "DOUBAO_API_KEY"),
    }
    changed = False
    for name, (base_env, key_env) in env_map.items():
        if name in providers and not providers[name].get("api_key"):
            k = env.get(key_env, "")
            b = env.get(base_env, "")
            if k:
                providers[name]["api_key"] = k
                if b:
                    providers[name]["base_url"] = b
                changed = True
    if changed:
        _save_providers(providers)
    return providers


def _save_providers(providers: dict) -> None:
    with _lock:
        PROVIDERS_FILE.write_text(json.dumps(providers, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


def get_providers() -> dict:
    """返回全部 provider 配置（含 key）——内部使用"""
    return _migrate_from_env(_load_providers())


def get_provider(name: str) -> dict | None:
    p = get_providers().get(name)
    if not p:
        return None
    p = dict(p)
    p["name"] = name
    return p


def list_providers() -> list[dict]:
    """API 用：key 脱敏后返回"""
    out = []
    for name, p in get_providers().items():
        key = p.get("api_key", "")
        masked = (key[:4] + "***" + key[-4:]) if len(key) > 8 else ("***" if key else "")
        out.append({
            "name": name, "label": p.get("label", name),
            "base_url": p.get("base_url", ""), "model": p.get("model", ""),
            "api_key": p.get("api_key", ""),
            "masked_key": masked,
            "configured": bool(key),
            "enabled": p.get("enabled", False),
        })
    return out


def update_provider(name: str, updates: dict) -> dict:
    """更新 provider 配置（API 用）。updates 支持: base_url/model/api_key/enabled"""
    providers = get_providers()
    if name not in providers:
        raise KeyError(f"未知 provider: {name}")
    for k in ("base_url", "model", "api_key", "enabled", "label"):
        if k in updates:
            providers[name][k] = updates[k]
    _save_providers(providers)
    # 使 LLM 客户端缓存失效
    from . import llm
    llm.invalidate(provider=name)
    return providers[name]
