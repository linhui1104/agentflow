"""图像生成工具：多模型调度（豆包Seedream → GLM CogView → Pollinations 免费兜底）
图片下载保存到平台 outputs 目录，返回可访问 URL。
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.request
from pathlib import Path

from .. import config

OUTPUTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "outputs"
IMAGES_DIR = OUTPUTS_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def _download(url: str, filename: str) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
    data = urllib.request.urlopen(req, timeout=120).read()
    p = IMAGES_DIR / filename
    p.write_bytes(data)
    return p


def _seedream(prompt: str) -> str | None:
    """豆包 Seedream（用户配置 key + 端点）"""
    from ..config import get_provider
    p = get_provider("doubao")
    if not p or not p.get("api_key") or not p.get("image_model"):
        return None
    from openai import OpenAI
    import asyncio
    client = OpenAI(base_url=p["base_url"], api_key=p["api_key"], timeout=90)
    async def _g():
        r = client.images.generate(model=p["image_model"], prompt=prompt[:500],
                                   size="1024x1024", n=1)
        return r.data[0].url if r.data else None
    try:
        return asyncio.run(_g())
    except Exception:
        return None


def _cogview(prompt: str) -> str | None:
    """GLM CogView（用户配置 key）"""
    from ..config import get_provider
    p = get_provider("glm")
    if not p or not p.get("api_key"):
        return None
    from openai import OpenAI
    import asyncio
    client = OpenAI(base_url=p["base_url"], api_key=p["api_key"], timeout=90)
    async def _g():
        r = client.images.generate(model=p.get("image_model") or "cogview-3-flash",
                                   prompt=prompt[:500], size="1024x1024")
        return r.data[0].url if r.data else None
    try:
        return asyncio.run(_g())
    except Exception:
        return None


def _pollinations(prompt: str) -> str | None:
    """Pollinations 免费文生图（无 key 兜底）"""
    url = ("https://image.pollinations.ai/prompt/"
           + urllib.parse.quote(prompt[:400]) + "?width=1024&height=1024&nologo=true")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
        with urllib.request.urlopen(req, timeout=120) as r:
            if r.headers.get("content-type", "").startswith("image"):
                return url
    except Exception:
        pass
    return None


def generate_image(prompt: str) -> str:
    """多模型调度生成图片，返回平台内 URL（/api/files/images/xxx.png）"""
    ts = int(time.time() * 1000)
    filename = f"gen-{ts}.png"
    url = None
    used = ""
    for name, fn in (("seedream", _seedream), ("cogview", _cogview), ("pollinations", _pollinations)):
        try:
            url = fn(prompt)
        except Exception:
            url = None
        if url:
            used = name
            break
    if not url:
        raise RuntimeError("全部图像模型调度失败")
    _download(url, filename)
    return f"/api/files/images/{filename}"


def save_output_file(filename: str, content: str) -> str:
    """保存文本文件（md/csv/txt/html），返回平台内 URL"""
    safe = "".join(c for c in filename if c.isalnum() or c in ".-_")
    if not safe.endswith((".md", ".csv", ".txt", ".html", ".json")):
        safe += ".txt"
    p = OUTPUTS_DIR / safe
    p.write_text(content, encoding="utf-8")
    return f"/api/files/{safe}"
