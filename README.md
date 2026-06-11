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

## 现状（诚实版）

核心链路 **M1–M5 每段都有真实现 + 离线测试**（不依赖外部服务，可复现）：

| 机制 | 验证 |
|---|---|
| 选择→物化→修复（确定性，client 零 LLM） | M1 端到端收敛 |
| 止损闸门 + 2×2 归因 | M2：3 想法 × {组装/从零/oracle} |
| 真向量检索（本地 fastembed） | M3：recall@1 = 100% |
| 自动 ingestion 扩池（tree-sitter） | M4：WRITE_OWN 退化率 25%→0% |
| 飞轮健康度闭环 | M5：复用→健康度升→排序提升 |

**端到端真测**：用 deepseek 跑通"想法 → AI 选 → client 组装 → 0-error starter"。

### Token 实测数据

同一个 4-seam 想法（saas-admin：Google 登录 + Project CRUD + 数据表格 + 导出）：

| 维度 | 组装臂 | 从零臂 | 说明 |
|---|---|---|---|
| AI output（收敛产物） | **600–1200 tok** | **7700–8800 tok** | 量级差约 **6–10×** |
| 检索 input（离线确定） | **≈348 tok** | ≈1081 tok（全量喂） | 检索召回子集 **省 ≈68%** |

- output 数据来自真实跑出的收敛产物（如 oracle-saas-admin out=672、assembly out=1218）。
- 从零臂 output（7700–8800）是真实消耗，但三臂均**未完全收敛**——所以它是"逐行生成"成本的**下界**（真跑通只会更多），故"组装更省"是**保守**估计。
- output 是大头（比 input 贵约 4×），省的全是最贵的部分；client 物化阶段零 output。
- 这是单想法量级，非统计严谨基准；精确百分比不稳定，故以**量级**表述。

**诚实边界**：
- "能跑" = 能编译 + 能启动服务，**非功能完备**（占位 OAuth 凭据需自填；页面装配可能需手工补）。
- token 数据是单想法量级，三臂未完全收敛，以量级表述而非精确百分比（见上表说明）。
- generate（无候选时凭空写）比 pick 脆弱；最有效对策是扩候选池。
- 检索/池规模是最小验证版，非规模化生产（多语言 / Qdrant / OCI 分发等推迟）。

## 怎么用

见 [`INSTALL.md`](./INSTALL.md)（AI 自助安装指南）。装好后：

```bash
# 一句话想法 → starter
LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=sk-... \
  bash loom_assemble.sh ideas/<your-idea>.json <output-dir>
```

或在 Claude Code 里用 [`.claude/skills/loom`](./.claude/skills/loom/SKILL.md) skill 一句话触发。

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
