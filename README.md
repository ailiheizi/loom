# Loom

> **组装式开发（Composition-over-Generation）**：不从零写代码，而是从受控候选库**挑**现成组件拼装新项目——一次做对、最小化新增代码、省 AI 输出 token。
>
> 一句话：**它们生成，Loom 组装。**

## 是什么

Loom 是一个"项目首次从零启动"的代码组装系统。你给一个想法（如"带 Google 登录、能管理项目、支持导出的后台"），Loom：

1. 把想法分解成能力接缝（auth / CRUD / 表格 / 导出 …）
2. 从候选库**检索**召回每个接缝最匹配的现成组件
3. AI 只做**选择**（pick / adapt / generate），不逐行写代码 → 输出极小
4. **确定性物化**：拼装 + 注入环境 + 建数据表 + 类型检查 + 有界修复
5. 产出一个能编译能跑的高起点 starter（create-t3-app 技术栈）

核心赌注：**选择比生成省**。AI 输出（最贵的部分）只用于"选哪个"，而非"逐行写"。

实测（4 想法，deepseek-chat，两臂都修到收敛或止损，详见 [`docs/benchmark.md`](./docs/benchmark.md)）：
**从零生成 0/4 修到能编译（全部越修越乱止损），Loom 组装 4/4 干净收敛**，且 output token 只用 1/18。
核心不是"省百分之几"，而是"从零做不出能编译的项目，组装做得出"。

## 现状（诚实版）

核心链路 **M1–M5 每段都有真实现 + 离线测试**（不依赖外部服务，可复现）：

| 机制 | 验证 |
|---|---|
| 选择→物化→修复（确定性，client 零 LLM） | M1 端到端收敛 |
| 止损闸门 + 2×2 归因 | M2：3 想法 × {组装/从零/oracle} |
| 真向量检索（本地 fastembed） | M3：recall@1 = 100% |
| 自动 ingestion 扩池（tree-sitter） | M4：WRITE_OWN 退化率 25%→0% |
| 飞轮健康度闭环 | M5：复用→健康度升→排序提升 |
| **候选池密度验证（双臂对照）** | **2 seam 灌密后 h\*=0.058：组装收敛 vs 从零不收敛** |

**端到端真测**：用 deepseek 跑通"想法 → AI 选 → client 组装 → 0-error starter"。

### 实测数据（诚实版）

完整方法与数据见 [`docs/benchmark.md`](./docs/benchmark.md)。摘要（4 想法，deepseek-chat，两臂都跑到 maxRounds=8 修到收敛或 thrash 止损）：

| | 组装（pick 现成） | 从零（AI 生成） |
|---|---|---|
| 收敛（修到 0-error） | **4/4** | **0/4**（全部止损，剩 2-13 error） |
| 修复轮 | 0 | 2-5 轮后改不动 |
| output token 合计 | **1401** | 25277（白烧，没做成） |

- **核心结论不是"省 X%"**：单靠 deepseek 从零，4 个想法 0 个修到能编译（越修越乱止损）；Loom 组装 4/4 干净收敛。**从零做不出能编译的项目，组装做得出。**
- output token：组装是从零的 **1/18**——但这低估差距，因为从零那 25277 token 买到的是 4 个编译不过的半成品。

**诚实边界**：
- **单模型 deepseek-chat**。换更强模型（claude/gpt）从零臂收敛率会改善——0/4 是 deepseek 的上限，不全是"从零"范式的锅。模型越强，Loom 相对优势越小。
- **"收敛" = tsc 0-error，非 next build / 真运行**；OAuth 占位需自填，非功能完备。
- 样本小（4 想法/单域/各 1 次），量级参考非严谨基准。
- 旧 README 的"省 91%"是 maxRounds=3、从零未充分修复的口径，已被 benchmark.md 取代。

## 怎么用

### 方式一：零安装，连远程服务（推荐）

不装任何东西。在 Claude Code / Cursor 等支持 MCP 的 agent 里，加一个远程 MCP server：

```jsonc
// .mcp.json（Claude Code）或对应配置
{
  "mcpServers": {
    "loom": { "type": "http", "url": "https://loom.alhz.org/mcp" }
  }
}
```

或用命令行注册（更省事，不易写错）：

```bash
claude mcp add --transport http loom https://loom.alhz.org/mcp
```

然后直接对 agent 说想法，例如「用 loom 搭一个带 Google 登录、能增删改查项目、有表格和表单的后台」。agent 会：

1. 调 `loom_propose` → 每个能力 seam 返回 2-3 个候选 + 架构取舍
2. 你（或 agent）逐个挑 → `loom_plan_from_choices` 拼成 plan
3. `loom_get_files` → 返回完整项目文件清单（含 `app/dashboard/page.tsx` 把组件接好）
4. agent 把文件写到本地 → `pnpm install` → 填 `.env` 真实 key → `pnpm dev`

server 只做检索 + 拼装（零 LLM、零 key、不跑你的代码），AI 的「选择」只花几十 token，
代码由 server 返回现成的——这就是省 token 的来源。

> 边界：产物「能编译能启动」≠ 功能完备。OAuth 需填真实凭据；server 用轻量词袋检索（速度优先），
> 候选池覆盖 SaaS 后台/博客类想法（39 候选/10 接缝/2 域）。

### 方式二：本地全自动（需自备环境 + key）

见 [`INSTALL.md`](./INSTALL.md)。装好 Node/pnpm/Python/uv 后：

```bash
LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=sk-... \
  bash loom_assemble.sh ideas/<your-idea>.json <output-dir>
```

或在 Claude Code 里用 [`.claude/skills/loom`](./.claude/skills/loom/SKILL.md) skill 触发。

## 结构

- `platform/` — Python 侧：选择引擎（`run_select.py`）、检索（`retrieve.py` + `embedding.py`）、ingestion（`ingest.py`）、飞轮（`flywheel.py`）、契约（`loom_contracts.py`）、评测（`eval_*.py` / `verify_candidates.py`）
- `client/` — TS 侧：确定性物化（`materialize.ts`）、闸门（`gate.ts`）、有界修复（`repair.ts`）、环境注入（`injectEnv.ts`）
- `core/` — 冻结的 create-t3-app 基线 + `loom.core.json` 接缝定义
- `candidates/` — 候选库（手工策展 + ingest 自动入池）
- `ideas/` — 想法定义 + oracle 最优 plan
- `docs/` — 架构、实施计划、完整进度（`HANDOFF.md`）

## 验证（不依赖网关，可复现）

```bash
cd platform
uv run python eval_retrieval.py     # 检索召回率
uv run python eval_writeown.py      # 池增长 → WRITE_OWN 下降
uv run python eval_flywheel.py      # 飞轮健康度闭环
uv run python verify_candidates.py  # 候选 t3 gate 质量门
```

## 许可

MIT
