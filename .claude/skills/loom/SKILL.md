---
name: loom
description: >
  用 Loom 把一个开发想法组装成能编译能跑的高起点 starter 项目（检索-组装而非从零生成，
  AI 输出省 59~85%）。Use when: (1) 用户想从零启动一个新项目/想要一个 starter，
  (2) 用户说"用 loom 搭/组装/生成一个 X"、"帮我起一个带 Y 的项目"，
  (3) 用户描述一个 Web 应用想法（带登录/CRUD/表格/导出等能力）并想要可运行骨架。
  Loom 从候选库挑现成组件拼装（pick/adapt），只在无候选时才生成，产出 create-t3-app
  技术栈（Next.js+tRPC+Prisma+NextAuth）的可运行项目 + 装配历史。
  TRIGGER on: "loom", "组装项目", "搭一个", "起个项目", "starter", "从零启动", "assemble".
  client 物化是确定性的（零 LLM）；只有"选择装哪些组件"那步调一次 AI。
---

# Loom 项目组装 Skill

把"一句话想法"变成"能 `pnpm dev` 跑起来的高起点项目"。机制：**它们生成，Loom 组装**——
从受控候选库挑实战检验过的组件拼装，而非逐行生成，所以 AI 输出 token 省 59~85%。

## 何时用

用户想从零起一个 Web 项目，且能力落在 Loom 支持的接缝内（OAuth 登录 / CRUD 资源 /
数据表格 / 导出 / markdown 渲染 / CSV 导入）。技术栈固定为 create-t3-app。

## 前置（首次用，AI 自己检查并按需安装）

**先读 `INSTALL.md`**（项目根），它给 AI 列出依赖检查与安装步骤。关键：
- Node + pnpm（client）、Python + uv（platform）
- 一个 LLM 渠道（选择层调）：`LOOM_LLM_PROVIDER=deepseek` + `LOOM_LLM_API_KEY=sk-...`
  （deepseek OpenAI 兼容；原 anthropic 网关如可用也行）
- fastembed（本地 embedding，检索用，`uv add fastembed` 已装则跳过）

## 怎么执行（编排步骤）

### 方式 A：对话式（MCP，推荐 —— 面向架构师，逐功能挑候选）

装好 MCP server 后（见「安装 MCP」），宿主 agent（你）驱动三个无状态工具，LLM 全在你这侧：

1. **把想法写成 idea.json 文本**（idea_id / title / description / core_ref /
   capability_intents[]，每个 intent 标 seam_id）。
2. **`loom_propose(idea_json)`** → 每个 seam 返回 2-3 个真实候选 + 架构取舍（deps/复杂度/适用场景）
   + recommended 标记。**你把候选梯度摊给用户挑**；需求明确就替他选推荐项，不明确就问。
3. **`loom_plan_from_choices(idea_json, choices_json)`** → 把选择组装成 AssemblyPlan（零 LLM）。
   choices 每 seam 一条：`{"seam_id":"ui.data_table","ref":"sortable-data-table"}`。
4. **`loom_materialize(plan_json)`** → 确定性物化成 t3 starter，返回 `{out_dir, converged, next}`。
   `converged=true` = 0 类型错。

这条路把"选哪个组件"的决策权交给架构师，server 无状态、不调 LLM（对齐 agent-native 设计）。

### 方式 B：一条命令全自动（shell，server 侧 deepseek 选）

```bash
LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=$KEY \
  bash <项目根>/loom_assemble.sh <项目根>/ideas/<your-idea>.json <输出目录>
```
内部：platform 检索召回 + deepseek 选 AssemblyPlan → client 确定性物化。适合不需要人工挑的场景。

### 安装 MCP

- **Claude Code**：项目根 `.mcp.json` 已配好 loom server，用 `${CLAUDE_PROJECT_DIR}/platform` 绝对定位（cwd 无关，健壮）。项目级 `.mcp.json` 会被自动发现；首次需批准。验证：`loom_propose` 等三工具可见。
- **opencode**：项目根 `opencode.json` 配好 loom（相对 `platform`）。`opencode mcp list` 应显示 `✓ loom connected`。**注意**：opencode 读项目级配置依赖在项目根启动（cwd 漂到子目录会报 MCP server not found）。
- 两个配置文件独立，各自客户端读各自的，互不影响。

## 诚实边界（务必告知用户）

- "能跑" = 能编译 + 能启动服务，**非功能完备**：占位 OAuth 凭据（真登录需用户填真 key）；
  页面装配（把组件接进首页）可能需手工补——Loom 保证接缝级组装正确，不保证 UI 已连好。
- 若某能力无候选 → `needs_generate=true`，走 generate（AI 写），这部分可能需修复轮、偶有不收敛。
- 候选池越大越省：能 pick 的越多，generate 越少。要扩池用 `platform/ingest.py` / `seed_pool.py`。

## 关键文件

- **MCP（对话式）**：`platform/mcp_server.py`（propose/plan_from_choices/materialize 三工具）、`.mcp.json`
- `platform/propose.py`：候选梯度提案（每 seam 2-3 候选 + tradeoffs，零 LLM）
- `platform/plan_from_choices.py`：选择 → AssemblyPlan（零 LLM）
- `loom_assemble.sh`：全自动端到端入口（选择→物化）
- `platform/run_select.py --retrieve`：检索召回 + AI 选择
- `client/scripts/loom_materialize.ts`：确定性物化（零 LLM）
- `INSTALL.md`：AI 自助安装指南
- `docs/HANDOFF.md`：完整实现进度与里程碑
