# Loom

> **组装式开发（Composition-over-Generation）**：不从零写代码，而是从受控候选库**挑**现成组件拼装新项目——一次做对、最小化新增代码、省 AI 输出 token。
>
> 一句话：**它们生成，Loom 组装。**

## 是什么

Loom 是一个**持续学习的代码组装系统**——AI 编程的"肌肉记忆"。你给一个想法（如"带 Google 登录、能管理项目、支持导出的后台"），Loom：

1. 把想法分解成能力接缝（auth / CRUD / 表格 / 导出 …）
2. 从你的**个人组件库**（`~/.loom`）检索召回每个接缝最匹配的现成组件
3. AI 只做**选择**（pick / adapt / generate），不逐行写代码 → 输出极小
4. **确定性物化**：拼装 + 接成页面 + 注入环境 + 建数据表 → 完整 t3 项目
5. 你写完的新代码 `loom_ingest` 收录回库——**下次类似需求，AI 从你自己写过的代码里挑着用，越用越强**

核心赌注：**选择比生成省**（AI 输出只用于"选哪个"）。核心差异：别人的"代码记忆"帮 AI 检索/想起代码；Loom 帮 AI **直接复用你写过的代码组装新项目**（记住 → 提取组件 → 复用组装 → 信任飞轮强化）。

> 一句话：**它们生成，Loom 组装；你写过的，Loom 记住。**

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

### 最快：让你的 AI 装（推荐）

把下面这句发给你的 AI（Claude Code / Cursor / opencode）：

```
照这份指南帮我装 Loom：https://raw.githubusercontent.com/ailiheizi/loom/master/INSTALL.md
```

AI 会读指南、装好 uv（如果没有）、注册 Loom MCP。装好后直接说「用 loom 搭一个带登录、CRUD、表格的后台」即可。

> 强烈建议让 AI 装——它会读完整指南、按你的环境（Claude Code / Cursor / opencode）选对配置，比手动少出错。下面是手动方式。

### 方式一：uvx 本地 MCP（手动配，零 Python 感知）

只需装 [uv](https://docs.astral.sh/uv/)（一行 `curl`，比装 Python 简单），不碰 Python/pip/venv。在 Claude Code / Cursor 等 MCP agent 里配：

```jsonc
// .mcp.json
{
  "mcpServers": {
    "loom": { "command": "uvx", "args": ["loom-memory-mcp"] }
  }
}
```

或命令行：`claude mcp add loom -- uvx loom-memory-mcp`（[PyPI](https://pypi.org/project/loom-memory-mcp/)）

首次运行自动在 `~/.loom/` 初始化你的**个人组件库**（内置 39 个种子候选）。之后：

1. 对 agent 说想法（「搭个带 Google 登录、Project CRUD、表格、表单的后台」）
2. `loom_propose` → 每个能力 seam 返回 2-3 个候选 + 架构取舍，agent 帮你挑（不确定才问你）
3. `loom_plan_from_choices` → 拼成 plan；`loom_get_files` → 返回完整 t3 项目文件
4. agent 写盘 → `pnpm install` → 填 `.env` → `pnpm dev`
5. **`loom_ingest`**：你写完的代码调一次，自动收录进 `~/.loom`——**下次碰到类似需求，agent 从你自己写过的代码里挑着用，越用越强**

全程本地、零网络、零 key（propose/get_files 不调 LLM，AI 的「选择」只花几十 token）。
信任飞轮：常被复用的候选浮顶（Beta-Bernoulli 信任分），久不用的沉底。

飞轮的成功信号有两条路：
- **自动（推荐）**：client 物化后跑全项目 tsc（gate），把 per-候选编译结果写到 `outcomes.jsonl`，
  platform 下次启动自动消费——真实信号，不靠 agent 自觉。设 `LOOM_OUTCOMES_PATH`（或用默认
  `<store>/outcomes.jsonl`）让两端对上即闭环。
- **手动**：agent 跑完验证主动调 `loom_record_outcome(refs, success)`（纯 MCP 路径、无 client 物化时用）。

> 诚实边界：自动信号来自 tsc 编译通过与否，不等于"功能真的对"（OAuth 占位能编译但要填真 key）。
> 编译层面的"好用"已能自动驱动飞轮；语义层面的"好用"仍需人/agent 反馈。

### 方式二：远程服务（可选，连托管实例）

不想装任何东西，连一个托管的 Loom：

```bash
claude mcp add --transport http loom https://loom.alhz.org/mcp
```

> 边界：产物「能编译能启动」≠ 功能完备。OAuth 需填真实凭据；默认轻量词袋检索（速度优先，
> 可切 fastembed 语义检索）。候选池覆盖 SaaS 后台/博客类想法（39 候选 / 10 接缝 / 2 域）。

### 提升检索质量：开 fastembed 语义检索

默认用词袋检索（StubEmbedder，零网络、零加载，装上即用），但**同义词检索弱**。
要更准的语义检索，设环境变量 `LOOM_EMBED_PROVIDER=fastembed`（首次下载 BGE 模型 ~130MB，之后离线）。

实测差异（同义异词查询「找一个支持行内编辑的表格」）：

| 检索器 | 同义异词查询命中 | 说明 |
|---|---|---|
| StubEmbedder（默认词袋） | #7 | 靠字面词重叠，不懂同义 |
| fastembed（BGE 语义） | **#1** | 真懂语义 |

> ⚠️ 默认模型 multilingual-MiniLM 支持中英跨语言(判别力 0.6+)。
> 纯英文场景可设 `LOOM_EMBED_MODEL=BAAI/bge-small-en-v1.5` 获得更高英文精度。

在 `.mcp.json` 里加 env 即可：
```jsonc
{ "mcpServers": { "loom": {
  "command": "uvx", "args": ["loom-memory-mcp"],
  "env": { "LOOM_EMBED_PROVIDER": "fastembed" }
} } }
```

### 方式三：本地全自动（开发/自备 key）

见 [`INSTALL.md`](./INSTALL.md)。装好 Node/pnpm/Python/uv 后：

```bash
LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=sk-... \
  bash loom_assemble.sh ideas/<your-idea>.json <output-dir>
```

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
