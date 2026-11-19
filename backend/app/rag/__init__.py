"""知识库（RAG）：文档导入 → jieba 分词 → TF-IDF 向量 → 余弦检索
赛题考点「知识库定义与集成」：Agent 执行前自动检索知识库并注入上下文。
轻量实现（TF-IDF + 余弦相似度），无外部向量库依赖，可替换为 embedding 模型。
"""
from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter
from pathlib import Path

import jieba

from .. import config

KB_DIR = config.DATA_DIR / "kb"
KB_DIR.mkdir(parents=True, exist_ok=True)

_index_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _tokenize(text: str) -> list[str]:
    """中文分词 + 英文小写化 + 过滤单字符虚词"""
    words = [w.strip().lower() for w in jieba.cut(text) if w.strip()]
    return [w for w in words if len(w) > 1 or re.match(r"[a-z0-9]", w)]


def _split_chunks(text: str, size: int = 200, overlap: int = 30) -> list[str]:
    """按段落+长度切块（200 字符，30 重叠）"""
    paras = [p.strip() for p in text.splitlines() if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        buf = (buf + "\n" + p).strip()
        while len(buf) > size:
            chunks.append(buf[:size])
            buf = buf[size - overlap:]
    if buf:
        chunks.append(buf)
    return chunks


def add_document(name: str, text: str, meta: dict = None) -> dict:
    """导入文档：切块 → TF-IDF 索引 → 持久化。返回统计信息。"""
    chunks = _split_chunks(text)
    if not chunks:
        return {"name": name, "chunks": 0, "error": "空文档"}
    tokens = [_tokenize(c) for c in chunks]
    df = Counter()
    for tk in tokens:
        df.update(set(tk))
    n = len(chunks)
    # TF-IDF 向量（稀疏 dict）
    vectors = []
    for tk in tokens:
        tf = Counter(tk)
        vec = {w: (c / max(len(tk), 1)) * math.log((n + 1) / (df[w] + 1)) + 1.0
               for w, c in tf.items()}
        vectors.append(vec)
    index = {
        "name": name, "meta": meta or {}, "chunks": chunks,
        "vectors": vectors, "created": __import__("datetime").datetime.now().isoformat(),
    }
    (KB_DIR / f"{name}.json").write_text(json.dumps(index, ensure_ascii=False))
    with _lock:
        _index_cache[name] = index
    return {"name": name, "chunks": n, "vocab": len(df)}


def _load(name: str) -> dict | None:
    if name in _index_cache:
        return _index_cache[name]
    p = KB_DIR / f"{name}.json"
    if not p.exists():
        return None
    index = json.loads(p.read_text())
    with _lock:
        _index_cache[name] = index
    return index


def search(name: str, query: str, k: int = 2) -> list[dict]:
    """余弦相似度检索 top-k 片段"""
    index = _load(name)
    if not index:
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    q_tf = Counter(q_tokens)
    # 词表来自全部文档向量
    vocab = set()
    for v in index["vectors"]:
        vocab.update(v)
    n = len(index["chunks"])
    df = Counter()
    for v in index["vectors"]:
        df.update(v.keys())
    q_vec = {w: (c / len(q_tokens)) * math.log((n + 1) / (df[w] + 1)) + 1.0
             for w, c in q_tf.items() if w in vocab}
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

    scored = []
    for i, vec in enumerate(index["vectors"]):
        dot = sum(q_vec.get(w, 0.0) * c for w, c in vec.items())
        v_norm = math.sqrt(sum(c * c for c in vec.values())) or 1.0
        sim = dot / (q_norm * v_norm)
        scored.append((sim, i))
    scored.sort(reverse=True)
    return [{"score": round(s, 3), "chunk": index["chunks"][i][:600]}
            for s, i in scored[:k] if s > 0.01]


def list_documents() -> list[dict]:
    return [{"name": p.stem, "size": p.stat().st_size}
            for p in sorted(KB_DIR.glob("*.json"))]


def get_document(name: str) -> dict | None:
    index = _load(name)
    if not index:
        return None
    return {"name": name, "meta": index["meta"], "chunks": len(index["chunks"]),
            "text": "\n".join(index["chunks"])}
