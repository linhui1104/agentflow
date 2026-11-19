"""AgentFlow API 服务：REST + WebSocket 实时事件推送
支持多工作流管理、可视化编辑保存、自然语言生成工作流。
"""
import asyncio
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, store
from .agents import AgentRegistry
from .core.engine import WorkflowEngine
from .models import AgentProfile, Workflow
from .workflows import content_pipeline, templates, store as wf_store

app = FastAPI(title="AgentFlow - 多智能体编排平台", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 全局状态：Agent 注册表 + 工作流表 ──────────────────────────
registry = AgentRegistry()
WORKFLOWS: dict[str, Workflow] = {}
_wf_lock = threading.Lock()


def _register_team(agents: list[AgentProfile]) -> None:
    for a in agents:
        registry.register(a)


def _load_all_workflows() -> None:
    """启动加载：3 个内置模板 + 已保存的用户工作流"""
    builtins = [
        (content_pipeline.build_workflow(), content_pipeline.build_team()),
        templates.data_analysis(),
        templates.research_report(),
        templates.wechat_article(),
    ]
    for wf, team in builtins:
        _register_team(team)
        WORKFLOWS[wf.id] = wf
    # 已保存的用户工作流（AI 生成的 / 用户编辑保存的）
    for wf in wf_store.list_workflows():
        if wf.id not in WORKFLOWS:
            for a in wf_store.load_agents(wf.id):
                registry.upsert(a)
            WORKFLOWS[wf.id] = wf


_load_all_workflows()


def _init_kb() -> None:
    """启动时把 kb_docs 目录下的文档自动导入知识库"""
    from . import rag
    kb_docs = Path(__file__).resolve().parent.parent / "data" / "kb_docs"
    if kb_docs.exists():
        for f in kb_docs.glob("*.txt"):
            rag.add_document(f.stem, f.read_text(encoding="utf-8"),
                             meta={"source": f.name})


_init_kb()

# ── 事件总线（engine 线程 → asyncio WebSocket）──────────────────
_event_loop: asyncio.AbstractEventLoop | None = None
_subscribers: list[asyncio.Queue] = []


def on_run_event(run_id: str, node_id: str, payload: dict) -> None:
    if _event_loop and _subscribers:
        for q in list(_subscribers):
            try:
                _event_loop.call_soon_threadsafe(
                    q.put_nowait, {"run_id": run_id, "node_id": node_id, **payload})
            except Exception:
                pass


engine = WorkflowEngine(registry, on_event=on_run_event)


@app.on_event("startup")
async def _startup() -> None:
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    llm.setup_default()


# ── REST API ─────────────────────────────────────────────────
@app.get("/api/agents")
def list_agents():
    return [p.model_dump() for p in registry.all()]


@app.get("/api/workflows")
def list_workflows():
    return [{"id": w.id, "name": w.name, "description": w.description,
             "nodes": [n.model_dump() for n in w.nodes], "entry": w.entry}
            for w in WORKFLOWS.values()]


@app.get("/api/workflows/{wf_id}")
def get_workflow(wf_id: str):
    w = WORKFLOWS.get(wf_id)
    if not w:
        raise HTTPException(404, "workflow not found")
    return w.model_dump()


class WorkflowSave(BaseModel):
    workflow: dict
    agents: list[dict] = []


@app.post("/api/workflows")
def save_workflow(req: WorkflowSave):
    """保存用户编辑的工作流：注册/更新绑定的 Agent，工作流持久化"""
    try:
        wf = Workflow.model_validate(req.workflow)
    except Exception as e:
        raise HTTPException(400, f"工作流定义非法: {e}")
    for a_dict in req.agents:
        try:
            registry.upsert(AgentProfile.model_validate(a_dict))
        except Exception:
            continue
    with _wf_lock:
        WORKFLOWS[wf.id] = wf
    wf_store.save_workflow(wf)
    if req.agents:
        wf_store.save_agents(wf.id, [AgentProfile.model_validate(a) for a in req.agents])
    return {"ok": True, "id": wf.id, "name": wf.name}


class WorkflowGenerate(BaseModel):
    requirement: str


@app.post("/api/workflows/generate")
def generate_workflow(req: WorkflowGenerate):
    """自然语言需求 → AI 设计工作流 → 自动注册（平台自适应）"""
    from .core.generator import generate
    try:
        wf, agents = generate(req.requirement)
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    for a in agents:
        registry.upsert(a)
    with _wf_lock:
        WORKFLOWS[wf.id] = wf
    wf_store.save_workflow(wf)
    wf_store.save_agents(wf.id, agents)
    return {"ok": True, "workflow": wf.model_dump(), "agents": [a.model_dump() for a in agents]}


@app.delete("/api/workflows/{wf_id}")
def remove_workflow(wf_id: str):
    if wf_id not in WORKFLOWS:
        raise HTTPException(404, "workflow not found")
    with _wf_lock:
        WORKFLOWS.pop(wf_id, None)
    wf_store.delete_workflow(wf_id)
    return {"ok": True}


class RunRequest(BaseModel):
    workflow_id: str
    task: str


@app.post("/api/runs")
def create_run(req: RunRequest):
    wf = WORKFLOWS.get(req.workflow_id)
    if not wf:
        raise HTTPException(404, "workflow not found")

    def _execute():
        try:
            run = engine.execute(wf, req.task)
            store.save_snapshot(run)
        except Exception as e:
            print(f"[engine] 执行失败: {e}")

    threading.Thread(target=_execute, daemon=True).start()
    return {"started": True, "workflow_id": req.workflow_id, "task": req.task[:80]}


@app.get("/api/runs")
def list_runs():
    snaps = store.list_snapshots()
    result = []
    for name in snaps[:20]:
        d = store.load_snapshot(name.replace(".json", ""))
        if d:
            result.append({
                "id": d["id"], "workflow_id": d["workflow_id"],
                "status": d["status"], "created_at": d["created_at"],
                "finished_at": d.get("finished_at"),
            })
    return result


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    d = store.load_snapshot(run_id)
    if not d:
        raise HTTPException(404, "run not found")
    return d


@app.get("/api/scheduler")
def scheduler_snapshot():
    return engine.scheduler.snapshot()


# ── 工具与知识库 ─────────────────────────────────────────────
@app.get("/api/tools")
def list_tools():
    from .tools import TOOL_META
    return list(TOOL_META.values())


@app.get("/api/kb/documents")
def list_kb():
    from . import rag
    return rag.list_documents()


class KBDoc(BaseModel):
    name: str
    text: str


@app.post("/api/kb/documents")
def add_kb(req: KBDoc):
    from . import rag
    return rag.add_document(req.name, req.text, meta={"source": "api"})


@app.get("/api/kb/query")
def query_kb(q: str, name: str = "style-guide", k: int = 2):
    from . import rag
    return rag.search(name, q, k=k)


# ── Provider 配置（API key 由用户填入，代码零内置）───────────────
@app.get("/api/providers")
def list_providers():
    return config.list_providers()


class ProviderUpdate(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    enabled: bool | None = None


@app.put("/api/providers/{name}")
def put_provider(name: str, req: ProviderUpdate):
    try:
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        updated = config.update_provider(name, updates)
        return {"ok": True, "provider": name,
                "masked_key": updated["api_key"][:4] + "***" + updated["api_key"][-4:]
                if len(updated.get("api_key", "")) > 8 else "***"}
    except KeyError:
        raise HTTPException(404, f"未知 provider: {name}")


@app.post("/api/providers/{name}/test")
def test_provider_api(name: str):
    from . import llm
    return llm.test_provider(name)


# ── 文件库（多 AI 合力产出的图片/表格/文档）───────────────────
@app.get("/api/files")
def list_files():
    from .tools.files import OUTPUTS_DIR
    out = []
    if OUTPUTS_DIR.exists():
        for p in sorted(OUTPUTS_DIR.rglob("*")):
            if p.is_file():
                rel = p.relative_to(OUTPUTS_DIR).as_posix()
                out.append({"name": rel, "size": p.stat().st_size,
                            "url": f"/api/files/{rel}"})
    return out


try:
    from .tools.files import OUTPUTS_DIR
    if OUTPUTS_DIR.exists():
        app.mount("/api/files", StaticFiles(directory=str(OUTPUTS_DIR)), name="files")
except Exception:
    pass


# ── WebSocket 实时事件流 ─────────────────────────────────────
@app.websocket("/ws/runs")
async def ws_runs(ws: WebSocket):
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)
    try:
        while True:
            event = await q.get()
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if q in _subscribers:
            _subscribers.remove(q)


# ── 前端静态资源（构建后挂载）──────────────────────────────────
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
