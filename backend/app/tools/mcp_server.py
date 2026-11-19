#!/usr/bin/env python3
"""AgentFlow 自研 MCP Server（stdio 传输）
演示平台通过 MCP 协议接入外部工具服务的能力。
工具：calc（安全四则运算/乘方，不依赖 eval）
"""
import ast
import operator

from mcp.server.mcpserver import MCPServer

server = MCPServer("agentflow-tools")

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}


def _safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    node = tree.body   # eval 模式下 body 即表达式节点

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        raise ValueError("仅支持 + - * / % ** 运算")
    return ev(node)


@server.tool()
def calc(expression: str) -> str:
    """安全计算数学表达式（支持 + - * / % ** 与括号）。
    参数 expression: 数学表达式字符串，如 '(3+5)*2**3'。
    返回：计算结果。"""
    try:
        expr = str(expression).strip().strip('"\'`')
        result = _safe_eval(expr)
        return f"{expr} = {result}"
    except Exception as e:
        return f"计算失败: {str(e)[:80]}"


if __name__ == "__main__":
    server.run()   # stdio 传输
