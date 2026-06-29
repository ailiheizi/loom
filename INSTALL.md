# Loom 安装指南（给 AI 读）

> 这份文件是给 AI coding agent（Claude Code / Cursor / opencode 等）读的。
> 用户把这份文件的 URL 发给你，请你照下面步骤把 Loom 装好。全部步骤都很简单。

Loom = 一个 MCP 工具：从用户自己的代码库检索-组装新项目，越用越强（AI 编程的肌肉记忆）。
装 Loom = 装 uv（如果没有）+ 注册一个 MCP server。**不需要 clone 仓库、不需要 Python、不需要 key。**

## 步骤

### 1. 确认 uv 已安装

```bash
uv --version
```

没有就装（uv 会自己管理 Python，用户无需装 Python）：
- macOS / Linux：`curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows：`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

### 2. 注册 Loom MCP server

Claude Code：
```bash
claude mcp add loom -- uvx loom-memory-mcp
```

Cursor / 其他（手写 `.mcp.json`）：
```jsonc
{ "mcpServers": { "loom": { "command": "uvx", "args": ["loom-memory-mcp"] } } }
```

opencode（`opencode.json`）：
```jsonc
{ "mcp": { "loom": { "type": "local", "command": ["uvx", "loom-memory-mcp"], "enabled": true } } }
```

### 3. 验证

重启 agent 或重载 MCP，确认这些工具可见：
`loom_propose` / `loom_plan_from_choices` / `loom_get_files` / `loom_ingest`

首次调用会自动在 `~/.loom/` 初始化用户的个人组件库（内置 39 个种子候选）。

## 装好后怎么用（告诉用户）

直接说想法，例如「用 loom 搭一个带 Google 登录、Project 增删改查、表格和表单的后台」。流程：
1. 你调 `loom_propose` → 每个能力 seam 返回 2-3 个候选 + 架构取舍
2. 你帮用户挑（高置信直接选，不确定才问用户）→ `loom_plan_from_choices`
3. `loom_get_files` → 返回完整 create-t3-app 项目文件
4. 你写盘 → `pnpm install` → 填 `.env` → `pnpm dev`
5. 用户写完新代码后，你可以调 `loom_ingest` 收录进库，下次复用

诚实边界：产物「能编译能启动」≠ 功能完备（OAuth 占位需用户填真 key）。
