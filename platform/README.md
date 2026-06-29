# loom-mcp

**AI 编程的肌肉记忆** —— 一个持续学习的代码组装 MCP server。

把你写过的代码自动收录为可复用组件，下次碰到类似需求，AI 直接从你自己的组件库里挑着用，越用越强。

## 安装

需要 [uv](https://docs.astral.sh/uv/)。在 Claude Code / Cursor 等 MCP agent 里配：

```jsonc
// .mcp.json
{ "mcpServers": { "loom": { "command": "uvx", "args": ["loom-memory-mcp"] } } }
```

或：`claude mcp add loom -- uvx loom-memory-mcp`

首次运行自动在 `~/.loom/` 初始化个人组件库（内置种子候选）。

## 工具

- `loom_propose(idea_json)` — 对想法返回每个能力 seam 的 2-3 个候选 + 架构取舍
- `loom_plan_from_choices(idea_json, choices_json)` — 选择 → 装配计划
- `loom_get_files(plan_json)` — 物化成完整 create-t3-app 项目文件
- `loom_ingest(paths, seam_hint?, description?)` — 收录你写的代码进组件库
- `loom_record_outcome(refs, success)` — 跑完 tsc/build 后回报结果，驱动信任飞轮

## 工作流

说想法 → propose 给候选梯度（agent 帮你挑，不确定才问）→ get_files 返回完整项目
→ 写盘 + `pnpm install` + 填 `.env` + `pnpm dev`。写完新代码 `loom_ingest` 收录，越用越强。

全程本地、零网络、零 key（检索/物化不调 LLM）。信任飞轮：常用的候选浮顶，久不用的沉底。

详见 [项目主页](https://github.com/ailiheizi/loom)。

## 许可

MIT
