"""测试 .env 中各 LLM provider 可用性（key 不打印）"""
import os
from openai import OpenAI

def load_env(path):
    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d

env = load_env(os.path.expanduser("~/.hermes/.env"))

candidates = [
    ("deepseek", env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), env.get("DEEPSEEK_API_KEY", ""),
     ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro"]),
    ("glm", env.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"), env.get("GLM_API_KEY", ""),
     ["glm-4-flash", "glm-4-plus", "glm-4.5"]),
    ("doubao", env.get("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"), env.get("DOUBAO_API_KEY", ""),
     ["doubao-1.5-vision-pro-32k-250115", "deepseek-v3.2", "doubao-seed-1-8-251228"]),
]

for name, base, key, models in candidates:
    if not key:
        print(f"[SKIP] {name}: 无key")
        continue
    print(f"[{name}] base={base}")
    for m in models:
        try:
            c = OpenAI(base_url=base, api_key=key, timeout=25)
            r = c.chat.completions.create(model=m, messages=[{"role": "user", "content": "回复OK"}], max_tokens=5)
            print(f"  [OK] {m} -> {r.choices[0].message.content!r}")
        except Exception as e:
            print(f"  [FAIL] {m} -> {str(e)[:90]}")
