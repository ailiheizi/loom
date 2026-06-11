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

1. **把用户想法写成 idea.json**（参考 `ideas/*.json` 格式：idea_id / title / description /
   core_ref / capability_intents[]，每个 intent 标 seam_id）。放进 `ideas/`。
2. **一条命令组装**：
   ```bash
   LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=$KEY \
     bash <项目根>/loom_assemble.sh <项目根>/ideas/<your-idea>.json <输出目录>
   ```
   它内部：① platform 检索召回候选子集 + deepseek 选 AssemblyPlan（省 input）
   → ② client 确定性物化 + 建 prisma model + 注入 env + 类型检查 + 有界修复。
3. **看结果**：输出目录是一个 t3 项目。`converged=true` 表示 0 类型错。
   装配历史（picked/adapted/generated 分层）会打印。
4. **交付**：`cd <输出目录> && pnpm install && node node_modules/next/dist/bin/next dev`。

## 诚实边界（务必告知用户）

- "能跑" = 能编译 + 能启动服务，**非功能完备**：占位 OAuth 凭据（真登录需用户填真 key）；
  页面装配（把组件接进首页）可能需手工补——Loom 保证接缝级组装正确，不保证 UI 已连好。
- 若某能力无候选 → 走 generate（AI 写），这部分可能需修复轮、偶有不收敛（generate 比 pick 脆）。
- 候选池越大越省：能 pick 的越多，generate 越少。要扩池用 `platform/ingest.py`。

## 关键文件

- `loom_assemble.sh`：端到端入口（选择→物化）
- `platform/run_select.py --retrieve`：检索召回 + AI 选择
- `client/scripts/loom_materialize.ts`：确定性物化（零 LLM）
- `INSTALL.md`：AI 自助安装指南
- `docs/HANDOFF.md`：完整实现进度与里程碑
