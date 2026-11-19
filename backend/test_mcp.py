import asyncio, sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app import llm
llm.setup_default()

async def main():
    import contextlib
    from agents import Agent, Runner
    from agents.mcp import MCPServerStdio
    from app.llm import build_model
    mcp_path = str(Path("app/tools/mcp_server.py").resolve())
    server = MCPServerStdio(
        params={"command": sys.executable, "args": [mcp_path]},
        cache_tools_list=True, name="agentflow-mcp")
    agent = Agent(name="calc-probe",
                  instructions="你是计算助手。用户给出算式时，调用 calc 工具计算并给出结果。",
                  model=build_model(),
                  mcp_servers=[server])
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(server)
        print("server entered")
        result = await Runner.run(agent, "请用工具计算 (3+5)*2**3", max_turns=8)
        print("OUTPUT:", result.final_output)

try:
    asyncio.run(main())
except Exception:
    traceback.print_exc()
