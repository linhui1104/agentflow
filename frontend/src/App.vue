<template>
  <div class="app">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="brand">
        <span class="logo">⬡</span>
        <div>
          <h1>AgentFlow</h1>
          <p>多智能体编排平台 · 可视化设计 · AI 自动生成</p>
        </div>
      </div>

      <div class="wf-selector">
        <select v-model="currentWfId" @change="switchWorkflow">
          <option v-for="w in workflowList" :key="w.id" :value="w.id">{{ w.name }}</option>
        </select>
        <button class="btn-ghost" title="删除当前工作流" @click="deleteCurrent">🗑</button>
      </div>

      <div class="task-bar">
        <input v-model="task" placeholder="输入任务，例如：写一篇大学生时间管理推文" @keyup.enter="run" />
        <button class="btn-run" :disabled="running" @click="run">{{ running ? '执行中…' : '▶ 执行' }}</button>
        <button class="btn-save" @click="saveCurrent">💾 保存</button>
      </div>
    </header>

    <!-- AI 生成栏 -->
    <div class="gen-bar">
      <span class="gen-icon">✨</span>
      <input v-model="genRequirement" placeholder="用一句话描述需求，AI 自动设计工作流。例如：把小红书笔记改写成知乎专业回答"
             @keyup.enter="generateWorkflow" :disabled="generating" />
      <button class="btn-gen" :disabled="generating || !genRequirement.trim()" @click="generateWorkflow">
        {{ generating ? 'AI 设计中…' : 'AI 生成工作流' }}
      </button>
      <span v-if="genError" class="gen-error">✗ {{ genError }}</span>
    </div>

    <!-- 主区 -->
    <main class="main">
      <!-- 左：节点库 -->
      <aside class="node-lib">
        <div class="lib-title">节点库</div>
        <p class="lib-tip">拖入画布</p>
        <div v-for="t in NODE_TYPES" :key="t.type" class="lib-item" :draggable="true"
             @dragstart="onDragStart($event, t.type)">
          <span class="lib-icon">{{ t.icon }}</span>
          <div><b>{{ t.label }}</b><p>{{ t.desc }}</p></div>
        </div>
        <div class="lib-title" style="margin-top:14px">编辑提示</div>
        <p class="lib-tip">点击节点 → 右侧配置<br/>点击连线/节点后按 Delete 删除<br/>拖动节点圆点连线</p>
      </aside>

      <!-- 中：画布 -->
      <section class="canvas" @drop="onDrop" @dragover="onDragOver" @dragleave="onDragLeave">
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" :min-zoom="0.2" :max-zoom="1.8"
                 :default-viewport="{ zoom: 0.85 }" fit-view-on-init
                 :delete-key-code="['Backspace', 'Delete']"
                 @connect="onConnect" @node-click="onNodeClick" @pane-click="onPaneClick"
                 @nodes-delete="onNodesDelete" @edges-delete="onEdgesDelete">
          <Background pattern-color="#e5e7eb" :gap="24" />
          <Controls />
          <template #node-custom="props">
            <div class="wf-node" :class="statusClass(props.data.status)" :title="props.data.tooltip"
                 @click.stop="selectNode(props.id)">
              <Handle type="target" :position="Position.Left" class="node-handle" />
              <div class="wf-node-type">{{ typeIcon(props.data.nodeType) }} {{ typeLabel(props.data.nodeType) }}</div>
              <div class="wf-node-name">{{ props.data.label }}</div>
              <div class="wf-node-meta">
                <span v-if="props.data.status">{{ statusLabel(props.data.status) }}</span>
                <span v-if="props.data.score != null" class="score">验证 {{ props.data.score }}</span>
                <span v-if="props.data.visits > 1" class="loops">循环×{{ props.data.visits }}</span>
              </div>
              <Handle type="source" :position="Position.Right" class="node-handle" />
            </div>
          </template>
        </VueFlow>
        <div class="legend">
          <span><i class="dot" style="background:#94a3b8"></i>待执行</span>
          <span><i class="dot" style="background:#3b82f6"></i>执行中</span>
          <span><i class="dot" style="background:#f59e0b"></i>验证/修正</span>
          <span><i class="dot" style="background:#22c55e"></i>完成</span>
          <span><i class="dot" style="background:#ef4444"></i>失败</span>
        </div>
      </section>

      <!-- 右：面板 -->
      <aside class="panel">
        <div v-if="!selectedNode" class="tabs">
          <button :class="{ active: tab === 'log' }" @click="tab = 'log'">执行日志</button>
          <button :class="{ active: tab === 'output' }" @click="tab = 'output'">最终产出</button>
          <button :class="{ active: tab === 'agents' }" @click="tab = 'agents'">Agent 团队</button>
          <button :class="{ active: tab === 'tools' }" @click="tab = 'tools'">工具/知识库</button>
          <button :class="{ active: tab === 'models' }" @click="tab = 'models'">模型配置</button>
        </div>

        <!-- 节点配置面板 -->
        <div v-if="selectedNode" class="tab-body node-config">
          <div class="cfg-head">
            <b>⚙ 节点配置</b>
            <button class="btn-close" @click="selectedNode = null">✕</button>
          </div>
          <label>节点名称</label>
          <input v-model="selectedNode.data.label" />
          <label>类型</label>
          <select v-model="selectedNode.data.nodeType" @change="onTypeChange">
            <option value="agent">Agent 节点</option>
            <option value="verify">验证节点</option>
            <option value="condition">条件节点</option>
          </select>

          <template v-if="selectedNode.data.nodeType === 'agent'">
            <label>绑定 Agent</label>
            <select v-model="selectedNode.data.agent_id">
              <option value="">— 按角色调度（填写角色名）—</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.name }}（{{ a.id }}）</option>
            </select>
            <label>角色调度（不绑定时生效）</label>
            <input v-model="selectedNode.data.role" placeholder="如：内容撰写" />
            <label>输入模板（{task} {节点id} {prev} {kb} {节点id.reason}）</label>
            <textarea v-model="selectedNode.data.input_template" rows="4" />
            <label>验证阈值（留空=不内置验证）</label>
            <input v-model.number="selectedNode.data.verify_threshold" type="number" step="0.5" placeholder="如 7" />
            <label>规则校验（JSON：min_length / required / forbidden）</label>
            <textarea v-model="selectedNode.data.verify_rules_text" rows="2" placeholder='{"min_length": 300, "required": ["#"]}' />
            <label>工具</label>
            <div class="tool-checks">
              <label v-for="t in toolList" :key="t.name"><input type="checkbox" :value="t.name"
                     v-model="selectedNode.data.tools" /> {{ t.label }}</label>
            </div>
            <label>知识库（RAG 注入 {kb}）</label>
            <input v-model="selectedNode.data.kb" placeholder="如 style-guide" />
          </template>

          <template v-if="selectedNode.data.nodeType === 'verify'">
            <label>验证目标节点</label>
            <select v-model="selectedNode.data.target">
              <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.data.label || n.id }}</option>
            </select>
            <label>阈值</label>
            <input v-model.number="selectedNode.data.verify_threshold" type="number" step="0.5" />
          </template>

          <template v-if="selectedNode.data.nodeType === 'condition'">
            <label>条件表达式</label>
            <select v-model="selectedNode.data.condition">
              <option value="verify_score>=7">verify_score &gt;= 7</option>
              <option value="verify_score>=8">verify_score &gt;= 8</option>
              <option value="verify_score>=6">verify_score &gt;= 6</option>
            </select>
            <label>参考分数节点</label>
            <select v-model="selectedNode.data.target">
              <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.data.label || n.id }}</option>
            </select>
            <p class="cfg-tip">两条出边：第 1 条 = 条件真，第 2 条 = 条件假</p>
            <label>最大执行次数（循环用）</label>
            <input v-model.number="selectedNode.data.max_visits" type="number" min="1" />
          </template>

          <template v-if="selectedNode.data.nodeType === 'agent'">
            <label>最大执行次数（循环用，默认1）</label>
            <input v-model.number="selectedNode.data.max_visits" type="number" min="1" />
          </template>
        </div>

        <!-- 日志 -->
        <div v-if="!selectedNode && tab === 'log'" class="tab-body">
          <div v-for="(e, i) in log" :key="i" class="log-line">
            <span class="log-time">{{ e.time }}</span>
            <span class="log-node">{{ e.nodeLabel }}</span>
            <span class="log-status" :class="e.status">{{ statusLabel(e.status) }}</span>
            <span class="log-detail">{{ e.detail }}</span>
          </div>
          <p v-if="!log.length" class="empty">点击「执行」后，此处实时显示各节点事件</p>
        </div>

        <!-- 产出 -->
        <div v-if="!selectedNode && tab === 'output'" class="tab-body">
          <p v-if="!finalOutput" class="empty">执行完成后此处显示最终产出</p>
          <div v-else>
            <div class="output-md" v-html="renderMarkdown(finalOutput)"></div>
            <h3 v-if="fileList.length" class="section-title">📁 文件库（多 AI 合力产出）</h3>
            <div v-for="f in fileList" :key="f.name" class="file-card">
              <span class="file-icon">{{ fileIcon(f.name) }}</span>
              <div class="file-info">
                <b>{{ f.name }}</b>
                <p>{{ (f.size / 1024).toFixed(1) }} KB</p>
              </div>
              <a class="file-open" :href="f.url" target="_blank">打开</a>
              <a class="file-open" :href="f.url" :download="f.name">下载</a>
            </div>
          </div>
        </div>

        <!-- Agents -->
        <div v-if="!selectedNode && tab === 'agents'" class="tab-body">
          <div v-for="a in agents" :key="a.id" class="agent-card">
            <div class="agent-head">
              <b>{{ a.name }}</b>
              <span class="agent-id">{{ a.id }}</span>
              <span class="agent-provider">{{ a.provider }}</span>
            </div>
            <div class="agent-stats">
              成功率 <b>{{ (a.capability.success_rate * 100).toFixed(0) }}%</b>
              · 均耗时 <b>{{ a.capability.avg_latency.toFixed(0) }}s</b>
              · 负载 <b>{{ a.capability.load }}</b>
            </div>
            <div class="agent-role">角色：{{ a.role }}</div>
          </div>
        </div>

        <!-- 工具与知识库 -->
        <div v-if="!selectedNode && tab === 'tools'" class="tab-body">
          <h3 class="section-title">🔧 工具注册中心</h3>
          <div v-for="t in toolList" :key="t.name" class="tool-card">
            <div class="tool-head">
              <b>{{ t.label }}</b>
              <code>{{ t.name }}</code>
              <span class="tool-proto" :class="t.protocol === 'MCP stdio' ? 'mcp' : 'fn'">{{ t.protocol }}</span>
            </div>
            <div class="tool-desc">{{ t.desc }}</div>
          </div>
          <h3 class="section-title">📚 知识库（RAG）</h3>
          <div v-for="d in kbDocs" :key="d.name" class="tool-card">
            <div class="tool-head">
              <b>📄 {{ d.name }}</b>
              <span class="tool-proto kb">{{ (d.size / 1024).toFixed(1) }} KB</span>
            </div>
            <div class="tool-desc">TF-IDF 向量索引 · 执行时自动检索注入 Agent 上下文</div>
          </div>
          <div class="kb-query">
            <input v-model="kbQuery" placeholder="测试检索：输入关键词" @keyup.enter="doKbQuery" />
            <button @click="doKbQuery">检索</button>
          </div>
          <div v-for="(h, i) in kbHits" :key="i" class="kb-hit">
            <span class="kb-score">相关度 {{ h.score }}</span>
            <p>{{ h.chunk.slice(0, 120) }}…</p>
          </div>
        </div>

        <!-- 模型配置 -->
        <div v-if="!selectedNode && tab === 'models'" class="tab-body">
          <p class="models-tip">平台不内置任何 API Key。在此填入各家大模型的接入信息（Key 仅保存在本机配置文件）。</p>
          <div v-for="p in providers" :key="p.name" class="provider-card">
            <div class="provider-head">
              <b>{{ p.label }}</b>
              <code>{{ p.name }}</code>
              <span class="provider-state" :class="p.configured ? 'ok' : 'empty'">
                {{ p.configured ? '已配置 ' + p.masked_key : '未配置' }}</span>
              <label class="switch"><input type="checkbox" v-model="p.enabled" @change="saveProvider(p)" /><span>启用</span></label>
            </div>
            <div class="provider-fields">
              <input v-model="p.base_url" placeholder="Base URL（接口地址）" />
              <input v-model="p.model" placeholder="模型名称" />
              <input v-model="p.api_key" type="password" placeholder="API Key" />
            </div>
            <div class="provider-actions">
              <button class="btn-mini" @click="saveProvider(p)">保存</button>
              <button class="btn-mini test" :disabled="p.testing" @click="testProvider(p)">{{ p.testing ? '测试中…' : '测试连通' }}</button>
              <span v-if="p.testResult" class="test-result" :class="p.testResult.ok ? 'ok' : 'bad'">
                {{ p.testResult.ok ? '✓ ' + p.testResult.reply : '✗ ' + (p.testResult.error || '').slice(0, 60) }}</span>
            </div>
          </div>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { VueFlow, useVueFlow, Position, Handle } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const { fitView, screenToFlowCoordinate, onNodesInitialized, updateNode, addNodes, addEdges, removeNodes } = useVueFlow()

// ── 状态 ──────────────────────────────────────────────
const task = ref('写一篇面向大学生的公众号推文，主题：时间管理')
const genRequirement = ref('')
const generating = ref(false)
const genError = ref('')
const running = ref(false)
const tab = ref('log')
const nodes = ref([])
const edges = ref([])
const log = ref([])
const finalOutput = ref('')
const agents = ref([])
const toolList = ref([])
const kbDocs = ref([])
const kbQuery = ref('')
const kbHits = ref([])
const providers = ref([])
const fileList = ref([])
const workflowList = ref([])
const currentWfId = ref('')
const currentEntry = ref('')
const selectedNode = ref(null)
const nodeStatus = ref({})
let ws = null
let nodeIdCounter = 0

const NODE_TYPES = [
  { type: 'agent', icon: '🤖', label: 'Agent 节点', desc: '由 Agent 执行的任务' },
  { type: 'verify', icon: '✓', label: '验证节点', desc: '对产出交叉验证' },
  { type: 'condition', icon: '◇', label: '条件节点', desc: '按分数分流' },
]

const TYPE_LABEL = { agent: 'Agent', verify: '验证', condition: '条件', parallel: '并行' }
const typeIcon = t => ({ agent: '🤖', verify: '✓', condition: '◇', parallel: '⇉' }[t] || '•')
const typeLabel = t => TYPE_LABEL[t] || t

const STATUS_LABEL = {
  pending: '待执行', running: '执行中', verifying: '验证中', looping: '修正中',
  done: '完成', failed: '失败', skipped: '跳过',
}
const statusLabel = s => STATUS_LABEL[s] || s
const statusClass = s => `st-${s || 'pending'}`

// ── 工作流 ↔ 画布映射 ─────────────────────────────────
function wfToGraph(wf) {
  const nodeMap = {}
  wf.nodes.forEach(n => { nodeMap[n.id] = n })
  // 分层布局
  const depth = { [wf.entry]: 0 }
  const queue = [wf.entry]
  while (queue.length) {
    const id = queue.shift()
    const n = nodeMap[id]
    const nexts = [...(n.next || [])]
    if (n.type === 'parallel') nexts.push(...(n.config.branches || []))
    nexts.forEach(nx => {
      if (nx in nodeMap && !(nx in depth)) { depth[nx] = depth[id] + 1; queue.push(nx) }
    })
  }
  const layers = {}
  Object.entries(depth).forEach(([id, d]) => { (layers[d] = layers[d] || []).push(id) })
  const W = 190, H = 150, Y0 = 60
  const nl = []
  Object.entries(layers).forEach(([d, ids]) => {
    const totalW = ids.length * W
    ids.forEach((id, i) => {
      const n = nodeMap[id]
      const cfg = n.config || {}
      nl.push({
        id, type: 'custom',
        position: { x: 120 + i * W - totalW / 2, y: Y0 + Number(d) * H },
        data: {
          label: id, nodeType: n.type, agent_id: n.agent_id || '',
          role: cfg.role || '', input_template: cfg.input_template || '',
          verify_threshold: cfg.verify_threshold ?? null,
          verify_rules_text: JSON.stringify(cfg.verify_rules || {}),
          tools: cfg.tools || [], kb: cfg.kb || '', target: cfg.target || '',
          condition: cfg.condition || 'verify_score>=7', max_visits: cfg.max_visits ?? 1,
          status: nodeStatus.value[id]?.status || 'pending',
          score: nodeStatus.value[id]?.score ?? null,
          visits: nodeStatus.value[id]?.visits || 0,
          tooltip: `${n.type}${n.agent_id ? ' → ' + n.agent_id : ''}`,
        },
      })
    })
  })
  // 边
  const el = []
  wf.nodes.forEach(n => {
    (n.next || []).forEach((t, i) => {
      el.push({
        id: `e-${n.id}-${t}-${i}`, source: n.id, target: t, animated: true,
        label: n.type === 'condition' ? (i === 0 ? '通过' : '不通过') : '',
        style: n.type === 'condition' ? { stroke: i === 0 ? '#22c55e' : '#f59e0b', strokeWidth: 2 } : {},
      })
    })
    if (n.type === 'parallel') {
      (n.config.branches || []).forEach(t => {
        el.push({ id: `e-${n.id}-b-${t}`, source: n.id, target: t, animated: true,
                  style: { strokeDasharray: '6 4' } })
      })
    }
  })
  nodes.value = nl
  edges.value = el
  setTimeout(() => fitView({ padding: 0.3 }), 120)
}

function graphToWf() {
  const wfNodes = nodes.value.map(n => {
    const d = n.data
    const cfg = { max_visits: d.max_visits ?? 1 }
    if (d.role) cfg.role = d.role
    if (d.input_template) cfg.input_template = d.input_template
    if (d.verify_threshold != null && d.verify_threshold !== '') cfg.verify_threshold = Number(d.verify_threshold)
    if (d.verify_rules_text) {
      try { const r = JSON.parse(d.verify_rules_text); if (Object.keys(r).length) cfg.verify_rules = r } catch (e) {}
    }
    if (d.tools?.length) cfg.tools = d.tools
    if (d.kb) cfg.kb = d.kb
    if (d.target) cfg.target = d.target
    if (d.nodeType === 'condition') cfg.condition = d.condition || 'verify_score>=7'
    // 出边（condition 的出边顺序按 y 排序：上=真分支，下=假分支）
    const outs = edges.value
      .filter(e => e.source === n.id)
      .map(e => ({ target: e.target, y: nodes.value.find(x => x.id === e.target)?.position.y ?? 0 }))
      .sort((a, b) => a.y - b.y)
      .map(e => e.target)
    return {
      id: n.id, type: d.nodeType,
      agent_id: d.nodeType === 'agent' ? (d.agent_id || null) : null,
      config: cfg, next: outs,
    }
  })
  return {
    id: currentWfId.value, name: workflowList.value.find(w => w.id === currentWfId.value)?.name || '未命名工作流',
    description: '', nodes: wfNodes, entry: currentEntry.value, version: 1,
  }
}

// ── 编辑交互 ─────────────────────────────────────────
let dragType = null
function onDragStart(event, type) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/vueflow', type)
    event.dataTransfer.effectAllowed = 'move'
  }
  dragType = type
}
function onDragOver(event) { event.preventDefault(); if (dragType) event.dataTransfer.dropEffect = 'move' }
function onDragLeave() { dragType = null }
function onDrop(event) {
  if (!dragType) return
  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  const id = `node_${++nodeIdCounter}`
  const base = {
    agent: { label: '新任务', agent_id: agents.value[0]?.id || '', role: '', input_template: '{prev}\\n{task}',
             verify_threshold: null, verify_rules_text: '{}', tools: [], kb: '', max_visits: 1 },
    verify: { label: '验证', target: '', verify_threshold: 7, max_visits: 1 },
    condition: { label: '分流', condition: 'verify_score>=7', target: '', max_visits: 3 },
  }[dragType]
  const newNode = {
    id, type: 'custom', position,
    data: { ...base, nodeType: dragType, status: 'pending', score: null, visits: 0 },
  }
  addNodes(newNode)
  const { off } = onNodesInitialized(() => {
    updateNode(id, node => ({ position: { x: node.position.x - node.dimensions.width / 2, y: node.position.y - node.dimensions.height / 2 } }))
    off()
  })
  dragType = null
}

function onConnect(params) {
  const exists = edges.value.some(e => e.source === params.source && e.target === params.target)
  if (exists) return
  addEdges({
    id: `e-${params.source}-${params.target}-${Date.now()}`,
    source: params.source, target: params.target, animated: true,
  })
}

function onNodesDelete(deleted) {
  // 清理与被删节点关联的边 + 关闭配置面板
  const gone = new Set(deleted.map(n => n.id))
  edges.value = edges.value.filter(e => !gone.has(e.source) && !gone.has(e.target))
  if (selectedNode.value && gone.has(selectedNode.value.id)) selectedNode.value = null
  // 若删的是入口节点，把入口切到第一个剩余节点
  if (gone.has(currentEntry.value) && nodes.value.length) {
    currentEntry.value = nodes.value[0].id
  }
}

function onEdgesDelete(deleted) {
  // v-model 已同步 edges；这里仅保证条件边 label 顺序一致性（保存时按 y 排序）
  void deleted
}

function onNodeClick({ node }) { selectNode(node.id) }
function onPaneClick() { selectedNode.value = null }
function selectNode(id) {
  const n = nodes.value.find(x => x.id === id)
  selectedNode.value = n || null
}
function onTypeChange() {
  const d = selectedNode.value?.data
  if (!d) return
  if (d.nodeType === 'agent') { d.agent_id = d.agent_id || '' }
  if (d.nodeType === 'condition') { d.max_visits = d.max_visits ?? 3 }
  if (d.nodeType === 'verify') { d.verify_threshold = d.verify_threshold ?? 7 }
}

// ── 工作流管理 ────────────────────────────────────────
async function loadWorkflowList() {
  const res = await fetch('/api/workflows')
  workflowList.value = await res.json()
  if (!workflowList.value.some(w => w.id === currentWfId.value)) {
    currentWfId.value = workflowList.value[0]?.id || ''
  }
}
async function switchWorkflow() {
  const res = await fetch(`/api/workflows/${currentWfId.value}`)
  const wf = await res.json()
  currentEntry.value = wf.entry
  nodeStatus.value = {}
  wfToGraph(wf)
}
async function saveCurrent() {
  const wf = graphToWf()
  // 收集画布引用的 agents 定义（保存绑定团队）
  const usedAgentIds = new Set(wf.nodes.filter(n => n.agent_id).map(n => n.agent_id))
  const usedAgents = agents.value.filter(a => usedAgentIds.has(a.id))
  const res = await fetch('/api/workflows', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow: wf, agents: usedAgents }),
  })
  if (res.ok) { await loadWorkflowList(); alert('已保存 ✓') }
  else alert('保存失败: ' + (await res.text()).slice(0, 100))
}
async function deleteCurrent() {
  if (!confirm(`删除工作流「${workflowList.value.find(w => w.id === currentWfId.value)?.name}」？`)) return
  await fetch(`/api/workflows/${currentWfId.value}`, { method: 'DELETE' })
  await loadWorkflowList()
  currentWfId.value = workflowList.value[0]?.id || ''
  if (currentWfId.value) await switchWorkflow()
}
async function generateWorkflow() {
  generating.value = true
  genError.value = ''
  try {
    const res = await fetch('/api/workflows/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requirement: genRequirement.value }),
    })
    const d = await res.json()
    if (!res.ok) { genError.value = d.detail || '生成失败'; return }
    await loadWorkflowList()
    currentWfId.value = d.workflow.id
    currentEntry.value = d.workflow.entry
    nodeStatus.value = {}
    wfToGraph(d.workflow)
    genRequirement.value = ''
    // 刷新 agents 列表
    const ar = await fetch('/api/agents'); agents.value = await ar.json()
  } finally {
    generating.value = false
  }
}

// ── 执行 ─────────────────────────────────────────────
function refreshGraph() {
  nodes.value = nodes.value.map(n => ({
    ...n,
    data: {
      ...n.data,
      status: nodeStatus.value[n.id]?.status || 'pending',
      score: nodeStatus.value[n.id]?.score ?? null,
      visits: nodeStatus.value[n.id]?.visits || 0,
    },
  }))
}
async function run() {
  if (running.value) return
  running.value = true
  finalOutput.value = ''
  log.value = []
  nodeStatus.value = {}
  refreshGraph()
  const res = await fetch('/api/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow_id: currentWfId.value, task: task.value }),
  })
  if (!res.ok) { alert('启动失败'); running.value = false; return }
  connectWS()
}
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/runs`)
  ws.onmessage = ev => {
    const e = JSON.parse(ev.data)
    const cur = nodeStatus.value[e.node_id] || { status: 'pending', score: null, visits: 0 }
    if (e.status === 'looping' || e.status === 'verifying') {
      cur.loops = (e.round ?? 0) + 1
      cur.score = e.score ?? cur.score
    }
    if (e.status === 'done' && e.score != null) cur.score = e.score
    cur.status = e.status
    cur.visits = (cur.visits || 0) + 1
    nodeStatus.value[e.node_id] = cur
    refreshGraph()
    log.value.push({
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      nodeLabel: e.node_id, status: e.status, detail: buildDetail(e),
    })
    if (e.status === 'done' && e.node_id === 'publish') {
      setTimeout(loadFinalOutput, 800); running.value = false
    }
    // 通用完成判定：end/发布类节点完成后
    if (['done', 'failed', 'skipped'].includes(e.status) && isLastNode(e.node_id)) {
      running.value = false
    }
  }
  ws.onerror = () => { running.value = false }
}
function isLastNode() {
  // 简单判定：所有画布节点都已出终态
  return Object.values(nodeStatus.value).every(s =>
    ['done', 'failed', 'skipped'].includes(s.status))
}
function buildDetail(e) {
  const parts = []
  if (e.agent) parts.push(`Agent: ${e.agent}`)
  if (e.round != null) parts.push(`第${e.round + 1}轮`)
  if (e.score != null) parts.push(`得分 ${e.score}`)
  if (e.feedback) parts.push(e.feedback.slice(0, 60))
  if (e.reason) parts.push(e.reason)
  if (e.branch != null) parts.push(e.branch ? '→ 通过分支' : '→ 修正分支')
  if (e.error) parts.push(`错误: ${e.error.slice(0, 60)}`)
  return parts.join(' · ')
}
async function loadFinalOutput() {
  const res = await fetch('/api/runs')
  const runs = await res.json()
  if (!runs.length) return
  const detail = await (await fetch(`/api/runs/${runs[0].id}`)).json()
  finalOutput.value = detail.final_output || '（无产出）'
  const ar = await fetch('/api/agents'); agents.value = await ar.json()
  const fr = await fetch('/api/files'); fileList.value = await fr.json()
}

// ── 轻量 Markdown 渲染（图片/标题/粗体/列表/表格）──────────
function renderMarkdown(text) {
  if (!text) return ''
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = text.split('\n')
  let html = '', inTable = false, tableHtml = '', inCode = false, codeHtml = ''
  for (const raw of lines) {
    const line = raw
    if (line.trim().startsWith('```')) {
      if (inCode) { html += `<pre>${esc(codeHtml)}</pre>`; codeHtml = '' } else { inCode = true }
      continue
    }
    if (inCode) { codeHtml += line + '\n'; continue }
    // 图片
    const imgM = line.match(/!\[([^\]]*)\]\(([^)]+)\)/)
    if (imgM) {
      html += `<p class="md-img"><img src="${imgM[2]}" alt="${esc(imgM[1])}" onerror="this.parentElement.textContent='[图片加载失败]'"/></p>`
      continue
    }
    // 表格
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      const cells = line.trim().split('|').slice(1, -1).map(c => c.trim())
      if (cells.every(c => /^-+$/.test(c))) continue   // 分隔行
      const tag = inTable ? 'td' : 'th'
      if (!inTable) { tableHtml = '<table><tr>'; inTable = true }
      else tableHtml += '<tr>'
      tableHtml += cells.map(c => `<${tag}>${esc(c)}</${tag}>`).join('')
      tableHtml += '</tr>'
      continue
    }
    if (inTable) { html += tableHtml + '</table>'; tableHtml = ''; inTable = false }
    // 标题
    const hM = line.match(/^(#{1,4})\s+(.*)/)
    if (hM) { const lv = hM[1].length; html += `<h${lv} class="md-h">${esc(hM[2])}</h${lv}>`; continue }
    // 列表
    const ulM = line.match(/^\s*[-*]\s+(.*)/)
    if (ulM) { html += `<li class="md-li">${esc(ulM[1])}</li>`; continue }
    // 粗体
    const bolded = line.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    if (line.trim()) html += `<p class="md-p">${esc(bolded)}</p>`
  }
  if (inTable) html += tableHtml + '</table>'
  if (inCode) html += `<pre>${esc(codeHtml)}</pre>`
  return html
}

function fileIcon(name) {
  if (/\.(png|jpe?g|gif|webp)$/i.test(name)) return '🖼'
  if (/\.(md|txt)$/i.test(name)) return '📄'
  if (/\.(csv|xlsx?)$/i.test(name)) return '📊'
  if (/\.html?$/i.test(name)) return '🌐'
  return '📁'
}

// ── 数据加载 ─────────────────────────────────────────
async function loadData() {
  const [wfRes, agentRes, toolRes, kbRes, provRes] = await Promise.all([
    fetch('/api/workflows'), fetch('/api/agents'), fetch('/api/tools'),
    fetch('/api/kb/documents'), fetch('/api/providers'),
  ])
  const wfs = await wfRes.json()
  agents.value = await agentRes.json()
  toolList.value = await toolRes.json()
  kbDocs.value = await kbRes.json()
  providers.value = (await provRes.json()).map(p => ({ ...p, testing: false, testResult: null }))
  workflowList.value = wfs
  if (wfs.length) {
    currentWfId.value = wfs[0].id
    await switchWorkflow()
  }
}
async function saveProvider(p) {
  const res = await fetch(`/api/providers/${p.name}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: p.base_url, model: p.model, api_key: p.api_key, enabled: p.enabled }),
  })
  if (res.ok) {
    p.configured = !!p.api_key
    p.masked_key = p.api_key.length > 8 ? p.api_key.slice(0, 4) + '***' + p.api_key.slice(-4) : '***'
  }
}
async function testProvider(p) {
  p.testing = true; p.testResult = null
  try {
    const res = await fetch(`/api/providers/${p.name}/test`, { method: 'POST' })
    p.testResult = await res.json()
  } finally { p.testing = false }
}
async function doKbQuery() {
  if (!kbQuery.value.trim()) return
  const res = await fetch(`/api/kb/query?q=${encodeURIComponent(kbQuery.value)}&name=style-guide&k=3`)
  kbHits.value = await res.json()
}

onMounted(loadData)
onUnmounted(() => { if (ws) ws.close() })
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f8fafc; }
.app { display: flex; flex-direction: column; height: 100vh; }
.topbar { display: flex; align-items: center; gap: 14px; padding: 8px 16px; background: #fff; border-bottom: 1px solid #e2e8f0; }
.brand { display: flex; align-items: center; gap: 10px; }
.brand .logo { font-size: 24px; color: #6366f1; }
.brand h1 { font-size: 16px; color: #1e293b; }
.brand p { font-size: 10px; color: #64748b; }
.wf-selector { display: flex; gap: 4px; }
.wf-selector select { padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; min-width: 170px; }
.btn-ghost { padding: 8px 10px; border: 1px solid #e2e8f0; background: #fff; border-radius: 8px; cursor: pointer; }
.task-bar { display: flex; gap: 8px; flex: 1; max-width: 640px; }
.task-bar input { flex: 1; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; }
.btn-run { padding: 8px 18px; border: 0; border-radius: 8px; background: #6366f1; color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.btn-run:disabled { background: #a5b4fc; cursor: not-allowed; }
.btn-save { padding: 8px 14px; border: 1px solid #6366f1; background: #fff; color: #6366f1; border-radius: 8px; font-size: 13px; cursor: pointer; white-space: nowrap; }

.gen-bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; background: #eef2ff; border-bottom: 1px solid #c7d2fe; }
.gen-icon { font-size: 16px; }
.gen-bar input { flex: 1; padding: 8px 12px; border: 1px solid #c7d2fe; border-radius: 8px; font-size: 13px; background: #fff; }
.btn-gen { padding: 8px 16px; border: 0; border-radius: 8px; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.btn-gen:disabled { opacity: .5; cursor: not-allowed; }
.gen-error { color: #b91c1c; font-size: 12px; }

.main { display: flex; flex: 1; overflow: hidden; }
.node-lib { width: 150px; background: #fff; border-right: 1px solid #e2e8f0; padding: 10px; overflow-y: auto; }
.lib-title { font-size: 12px; font-weight: 700; color: #334155; margin-bottom: 6px; }
.lib-tip { font-size: 10.5px; color: #94a3b8; margin-bottom: 8px; line-height: 1.6; }
.lib-item { display: flex; gap: 8px; align-items: center; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 8px; margin-bottom: 8px; cursor: grab; background: #f8fafc; }
.lib-item:hover { border-color: #6366f1; background: #eef2ff; }
.lib-icon { font-size: 18px; }
.lib-item b { font-size: 12px; color: #1e293b; }
.lib-item p { font-size: 10px; color: #94a3b8; }

.canvas { flex: 1; position: relative; background: #fff; }
.legend { position: absolute; left: 16px; bottom: 14px; display: flex; gap: 12px; padding: 7px 12px; background: #fffd; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 11px; color: #475569; }
.legend .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 4px; }

.panel { width: 400px; background: #fff; border-left: 1px solid #e2e8f0; display: flex; flex-direction: column; }
.tabs { display: flex; border-bottom: 1px solid #e2e8f0; }
.tabs button { flex: 1; padding: 11px 4px; border: 0; background: none; font-size: 12px; color: #64748b; cursor: pointer; border-bottom: 2px solid transparent; }
.tabs button.active { color: #6366f1; border-bottom-color: #6366f1; font-weight: 600; }
.tab-body { flex: 1; overflow-y: auto; padding: 12px; }
.empty { color: #94a3b8; font-size: 13px; padding: 20px; text-align: center; }

.log-line { display: flex; gap: 8px; padding: 6px 4px; border-bottom: 1px solid #f1f5f9; font-size: 12px; align-items: baseline; }
.log-time { color: #94a3b8; flex-shrink: 0; }
.log-node { font-weight: 600; color: #334155; flex-shrink: 0; }
.log-status { flex-shrink: 0; padding: 1px 6px; border-radius: 4px; font-size: 11px; }
.log-status.running { background: #dbeafe; color: #1d4ed8; }
.log-status.verifying { background: #fef9c3; color: #a16207; }
.log-status.looping { background: #ffedd5; color: #c2410c; }
.log-status.done { background: #dcfce7; color: #15803d; }
.log-status.failed { background: #fee2e2; color: #b91c1c; }
.log-status.skipped { background: #f1f5f9; color: #64748b; }
.log-detail { color: #64748b; }
.output { white-space: pre-wrap; font-family: inherit; font-size: 13px; line-height: 1.7; color: #1e293b; }

/* Markdown 产出渲染 */
.output-md { font-size: 13px; line-height: 1.75; color: #1e293b; }
.output-md .md-h { margin: 12px 0 6px; color: #1f2937; }
.output-md .md-h1, .output-md h1 { font-size: 17px; }
.output-md h2 { font-size: 15px; }
.output-md h3 { font-size: 14px; }
.output-md .md-p { margin: 5px 0; }
.output-md .md-li { margin: 3px 0 3px 18px; }
.output-md .md-img img { max-width: 100%; border-radius: 8px; margin: 6px 0; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.output-md table { border-collapse: collapse; margin: 8px 0; font-size: 12px; width: 100%; }
.output-md th, .output-md td { border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left; }
.output-md th { background: #f1f5f9; }
.output-md pre { background: #f8fafc; border-left: 3px solid #6366f1; padding: 8px; font-size: 11.5px; white-space: pre-wrap; margin: 6px 0; }
.file-card { display: flex; align-items: center; gap: 10px; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 11px; margin-bottom: 8px; }
.file-icon { font-size: 20px; }
.file-info { flex: 1; }
.file-info b { font-size: 12.5px; display: block; }
.file-info p { font-size: 10.5px; color: #94a3b8; }
.file-open { font-size: 11.5px; color: #6366f1; text-decoration: none; padding: 3px 10px; border: 1px solid #c7d2fe; border-radius: 6px; }
.file-open:hover { background: #eef2ff; }

.agent-card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; margin-bottom: 10px; }
.agent-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.agent-head b { font-size: 14px; }
.agent-id { font-size: 11px; color: #94a3b8; }
.agent-provider { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: #ede9fe; color: #6d28d9; }
.agent-stats { font-size: 12px; color: #475569; margin-bottom: 4px; }
.agent-role { font-size: 12px; color: #64748b; }

.section-title { font-size: 13px; color: #334155; margin: 10px 0 8px; }
.tool-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 9px 11px; margin-bottom: 8px; }
.tool-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.tool-head b { font-size: 13px; }
.tool-head code { font-size: 11px; color: #64748b; background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
.tool-proto { font-size: 10px; padding: 1px 7px; border-radius: 10px; }
.tool-proto.fn { background: #dbeafe; color: #1d4ed8; }
.tool-proto.mcp { background: #dcfce7; color: #15803d; }
.tool-proto.kb { background: #fef3c7; color: #b45309; }
.tool-desc { font-size: 11.5px; color: #64748b; }
.kb-query { display: flex; gap: 8px; margin: 10px 0; }
.kb-query input { flex: 1; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px; }
.kb-query button { padding: 7px 14px; border: 0; border-radius: 6px; background: #6366f1; color: #fff; font-size: 12px; cursor: pointer; }
.kb-hit { border-left: 3px solid #f59e0b; background: #fffbeb; border-radius: 0 6px 6px 0; padding: 7px 10px; margin-bottom: 7px; }
.kb-score { font-size: 10px; color: #b45309; font-weight: 600; }
.kb-hit p { font-size: 11.5px; color: #475569; margin-top: 3px; line-height: 1.5; }

.models-tip { font-size: 11.5px; color: #64748b; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 7px 10px; margin-bottom: 10px; line-height: 1.5; }
.provider-card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; margin-bottom: 10px; }
.provider-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.provider-head b { font-size: 13px; }
.provider-head code { font-size: 10.5px; color: #64748b; background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
.provider-state { font-size: 10px; padding: 1px 7px; border-radius: 10px; }
.provider-state.ok { background: #dcfce7; color: #15803d; }
.provider-state.empty { background: #f1f5f9; color: #94a3b8; }
.switch { margin-left: auto; display: flex; align-items: center; gap: 5px; font-size: 11px; color: #475569; cursor: pointer; }
.provider-fields { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.provider-fields input { padding: 6px 9px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 11.5px; }
.provider-actions { display: flex; align-items: center; gap: 8px; }
.btn-mini { padding: 5px 14px; border: 0; border-radius: 6px; background: #6366f1; color: #fff; font-size: 12px; cursor: pointer; }
.btn-mini.test { background: #fff; color: #6366f1; border: 1px solid #c7d2fe; }
.btn-mini:disabled { opacity: .5; cursor: not-allowed; }
.test-result { font-size: 11px; }
.test-result.ok { color: #15803d; }
.test-result.bad { color: #b91c1c; }

.node-config label { display: block; font-size: 11.5px; color: #475569; margin: 9px 0 4px; font-weight: 600; }
.node-config input, .node-config select, .node-config textarea {
  width: 100%; padding: 7px 9px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12.5px; font-family: inherit;
}
.cfg-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.cfg-head b { font-size: 14px; color: #1e293b; }
.btn-close { border: 0; background: none; font-size: 14px; color: #94a3b8; cursor: pointer; }
.cfg-tip { font-size: 10.5px; color: #b45309; margin-top: 5px; line-height: 1.5; }
.tool-checks { display: flex; flex-wrap: wrap; gap: 8px; }
.tool-checks label { display: flex; align-items: center; gap: 4px; font-size: 11.5px; color: #475569; margin: 0; font-weight: 400; }

.wf-node { width: 168px; padding: 9px 11px; border-radius: 10px; background: #fff; border: 2px solid #94a3b8; box-shadow: 0 2px 6px rgba(0,0,0,.06); transition: border-color .3s; cursor: pointer; position: relative; }
.wf-node.st-running { border-color: #3b82f6; box-shadow: 0 0 0 4px #3b82f622; }
.wf-node.st-verifying { border-color: #f59e0b; box-shadow: 0 0 0 4px #f59e0b22; }
.wf-node.st-looping { border-color: #f97316; box-shadow: 0 0 0 4px #f9731622; animation: pulse 1s infinite; }
.wf-node.st-done { border-color: #22c55e; }
.wf-node.st-failed { border-color: #ef4444; box-shadow: 0 0 0 4px #ef444422; }
.wf-node.st-skipped { border-color: #cbd5e1; opacity: .55; }
@keyframes pulse { 50% { box-shadow: 0 0 0 7px #f9731600; } }
.wf-node-type { font-size: 9.5px; color: #94a3b8; }
.wf-node-name { font-size: 13px; font-weight: 600; color: #1e293b; margin: 2px 0; }
.wf-node-meta { font-size: 10.5px; color: #64748b; display: flex; gap: 7px; }
.wf-node-meta .score { color: #6d28d9; }
.wf-node-meta .loops { color: #ea580c; }
.node-handle { width: 9px !important; height: 9px !important; background: #6366f1 !important; border: 2px solid #fff !important; }
</style>
