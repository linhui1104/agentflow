# AgentFlow 复现指南（评审专用）

> 第五届"未来杯"创新大赛 · 赛题一 · 队伍 aplx23 · 项目：多智能体编排平台
> 仓库：https://github.com/linhui1104/agentflow

本指南帮助评审专家在 10 分钟内完成从零部署、体验平台全部核心能力，并复现白皮书中的全部数据。

---

## 一、环境要求

| 组件 | 版本 |
|---|---|
| Python | 3.11+ |
| Node.js | 18+（推荐 20+） |
| 大模型 API Key | 任选一家国产大模型（见下文） |

> 平台不内置任何 API Key。评审使用自己的 Key（DeepSeek 或 GLM 均可，注册 5 分钟内可获取）。

## 二、部署（3 步）

```bash
# 1. 获取代码
git clone https://github.com/linhui1104/agentflow.git
cd agentflow

# 2. 安装后端依赖
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. 安装前端依赖
cd ../frontend
npm install
```

## 三、启动（2 个终端）

```bash
# 终端 1：后端（端口 8900）
cd backend && ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8900

# 终端 2：前端（端口 5173）
cd frontend && npm run dev -- --host 0.0.0.0
```

浏览器打开 `http://localhost:5173`。

## 四、配置模型 Key（30 秒）

1. 右侧面板 → 「模型配置」
2. 在 DeepSeek 卡片填入 API Key → 「测试连通」→ 显示 ✓
3. （可选）GLM 卡片填入 Key，作为第二候选模型

## 五、核心能力体验路径（建议 15 分钟）

### ① 多智能体协作执行（3 分钟）
1. 顶部下拉选「公众号成品管线」
2. 任务框输入：`写一篇大学生宿舍好物推荐推文`
3. ▶ 执行 → 观察：节点实时状态流转、右侧执行日志、验证分数
4. 「最终产出」面板：完整推文 + **AI 生成的真实配图** + 可下载的 article.md

### ② 可视化工作流编辑（2 分钟）
1. 左侧节点库拖入 Agent/验证/条件节点 → 拖拽连线 → 点击节点改配置 → 💾 保存
2. 点选节点/连线 → 按 Delete 删除

### ③ AI 自适应生成（2 分钟）
1. 顶部紫色栏输入：`把会议纪要整理成行动清单和周报`
2. 「AI 生成工作流」→ 平台自动设计 Agent 团队与工作流 DAG（含修正循环）
3. 直接 ▶ 执行，观察"验证不通过 → 自动修正重跑"的循环过程

### ④ 调度策略对比（命令行，3 分钟）
```bash
cd backend && ../venv/bin/python ../scripts/benchmark.py
```
产出三种调度策略的逐任务数据（对应白皮书 4.2 节与表 7-1）。

### ⑤ 知识库 RAG 与工具调用（2 分钟）
- 「工具/知识库」面板：输入关键词测试知识库检索
- 执行「市场调研管线」：观察 Agent 自主调用联网搜索工具、标注来源

## 六、白皮书数据复现对照表

| 白皮书数据 | 复现方法 |
|---|---|
| 调度对比（33% 提速 / 2.8x 加速） | `scripts/benchmark.py`，原始数据存 backend/data/benchmark.json |
| 验证分（9.3 分等） | 任一工作流执行时节点的 verify_score；计算原理见白皮书 5.1 节 |
| 公众号成品（article.md + 配图） | 执行「公众号成品管线」，成品存 backend/data/outputs/ |
| 修正循环（4.4→9.3 分） | 执行「公众号成品管线」或 AI 生成工作流，观察 Self-Loop 轨迹（运行快照 backend/data/runs/*.json 可回放） |

## 七、常见问题

| 现象 | 处理 |
|---|---|
| 执行失败 402 Insufficient Balance | 模型账户余额不足，换一家模型或充值 |
| 图像生成失败 | 平台自动降级（Seedream→CogView→Pollinations 免费源），全部失败检查网络 |
| 前端打不开 | 确认两个终端都在运行；Windows 访问 WSL 用 `hostname -I` 查 IP |
| 端口占用 | 换端口（uvicorn --port、vite.config.js 代理同步改） |

## 八、作品结构速览

```
agentflow/
├── backend/app/
│   ├── core/          # ★ 自研：引擎 / 能力画像调度器 / 交叉验证器 / Self-Loop / AI生成器
│   ├── agents/        # Agent 团队（注册表/画像/工厂）
│   ├── tools/         # 工具注册中心（Function Calling + MCP Server）
│   ├── rag/           # 知识库（jieba+TF-IDF+余弦检索）
│   └── workflows/     # 4 套场景模板 + 持久化存储
├── frontend/          # Vue3 + Vue Flow 可视化编辑器
├── scripts/benchmark.py    # 调度策略对比基准测试
└── backend/data/
    ├── benchmark.json      # 白皮书全部性能数据的原始来源
    ├── runs/               # 每次执行的完整轨迹（可回放）
    └── kb_docs/            # 知识库文档
```

> 全部性能数据均可通过上述命令重新测得，无任何预置结果。
