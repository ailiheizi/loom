# Loom MVP 实施计划

> 构建策略：**端到端最薄一条线先打通**（vertical-slice-first）。因为已跳过独立验证实验，最薄链路 M1/M2 本身兼做方向验证。
> 已定决策：CRUD SaaS 后台 / create-t3-app 当 core / Python 平台 + TS 目标 / 仅首次启动场景。
> 方法：5 视角并行规划 → 合成 → 对抗审校 + 定 M1 任务清单。

## 里程碑路线图

| 里程碑 | 目标 | 完成判定 | 工作量 |
|---|---|---|---|
| **M0** | 钻机：纯物化管道，无 AI | 手写 manifest → `materialize && gate` → 打印 0/N errors | ~2-3 人天 |
| **M1** ★ | 最薄端到端：1 个写死想法跑通选择→物化→闸门→有界修复 **+ 同想法从零对照臂** | 单命令产出 git 仓库，0 error + 能 `pnpm dev` 跑通核心 flow + 一行双臂对照数据 | ~3-5 人天 |
| **M2** | 铺宽 3-5 想法 + 2×2 归因 + GO/NO-GO 止损闸门 | 「想法×{组装/从零/oracle}×6指标」表 + GO/NO-GO 结论 | ~3-4 人天 |
| — | **以下重资产严格推迟到 M2=GO 之后** | | |
| M3 | 真实向量检索替代手工策展（解命门：意图摘要召回） | 仅靠检索跑通 M1 同想法 + 离线召回率达标 | ~1-2 周 |
| M4 | Python 大规模 ingestion（解命门：候选池规模） | 池扩到规模化，WRITE_OWN 退化率随池增长下降 | ~2-3 周 |
| M5 | core 治理 + 飞轮回流（最重） | 合成/上传产物回流入池被复用，健康度闭环 | ~3-4 周+ |

**关键路径**：M0 → M1（首个 demo，~一周）→ M2（唯一工程止损点）→ M3 → M4 → M5。
**M2 是唯一止损闸门**：命中任一 kill 判据则停工程、回设计，不靠"再调调 prompt"硬续。

## 审校揪出的 M1 核心矛盾（已修正进计划）

1. **M1 必须吸收"同想法从零对照臂"**——原计划把对照臂全推到 M2，但只跑组装臂在数学上无法证伪"组装比从零省"这个赌注。从零臂复用同一 gate+repair，边际成本极小，收益是真正可证伪的 GO 信号。**oracle 臂 + 3-5 想法铺宽留 M2。**
2. **"能跑"必须纳入 M1 done**——`0-error + pnpm build` 是空心判定。env.js zod throw / prisma migrate / NextAuth secret / DATABASE_URL 全在 tsserver 盲区。M1 done 加硬条件：`pnpm dev` 真启动 + 人工走通核心 flow 一次。
3. **envVars 自动注入是"能跑"的硬前置，不是选择题**——候选带 `AUTH_GOOGLE_ID` 而 env.js 的 zod schema 不同步 append，t3 启动期直接 throw。
4. **接口契合度排序在 M1/M2 未被真验证**——seam 是对单份冻结 base 手写的、检索被"L0 全量喂"mock 掉。M1/M2 只验证选择机制+修复收敛，**不能外推成"真实检索召回够用"**。
5. **跨语言契约必须是第一个任务**——AssemblyPlan/manifest/lockfile 的 Pydantic↔zod 单一事实源是 Python/TS 两侧并行的硬分叉点。

## MVP 模块划分

**Python 平台侧**（向量/AI 生态；目标项目仍是 TS）：
- `loom.ingest` ingestion（MVP 跳过，手工策展替代，M4 才真做）
- `loom.retrieve` 检索排序（MVP 跳过，L0 全量喂替代，M3 才真做）
- `loom.disclosure` 披露式展开（MVP 真做数据契约，降级为读文件夹纯函数）
- `loom.select` 选择引擎 ★MVP 核心（instructor + Anthropic tool-use 出 AssemblyPlan）
- `loom.fallback` 兜底判定（MVP 真做规则，WRITE_OWN 退化率是 kill 判据）

**TS client 侧**（Node 20+TS，ts-morph/tsserver 原生）：
- 拉取层（MVP 读本地文件夹，zod 边界校验）
- 物化引擎（ts-morph：整文件落盘 + barrel append-only + dry-run 预览）
- 闸门（ts-morph `getPreEmitDiagnostics` 同步全项目诊断，规避 LSP 推送假绿）
- 修复循环（机器自动修 + 3 轮有界 + 震荡检测 + span-only 回灌）

**通信**：无状态 REST + 内容寻址 blob（MVP 退化为本地文件夹）。JSON Schema 单一事实源（pydantic 产出 / zod 消费）。候选契约复用 shadcn registry-item.json，私货塞 `meta.loom`。

## M1 可执行任务清单（有序）

> 起手顺序纠正：**不要先写选择引擎**。先并行做两件互不依赖的奠基：T1 契约 + T2 M0 基线。

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| T1 | 冻结跨语言契约：Pydantic v2 写 AssemblyPlan/SelectionDecision/manifest/lockfile，预留 sha256/envVars/provenance 字段；导出 JSON Schema，TS 侧 zod 镜像；附 fixture 对拍 | `loom_contracts.py` + `contracts.ts` + `schema/*.json` + `fixtures/` | none |
| T2 | 完成 M0 基线：冻结 t3 base 副本（App Router+tRPC+Prisma+NextAuth v5+Tailwind），注入 `// <loom-anchor:*>` 锚点；手写 `loom.core.json` 定义 4 seam（含 1 个故意留空的 report.custom_export） | base/ + 注入锚点的 base + loom.core.json | T1 |
| T3 | 手工策展候选池：3-4 seam 各 2-3 真实开源文件，按 `candidates/<seam>/{_L0.md,_L1.ts,<候选>/L2全文}` 组织 + deps/envVars/LOC 元数据 | candidates/ 目录树 | T1 |
| T4 | 写死想法 + capability intents→seam 映射（带 Google OAuth 的 CRUD SaaS 后台 + 1 resource，硬编码） | idea.json | T1 |
| T5 | Python 选择回合：喂全部 L0+L1 → AI tool-use 按需请求 L2 → instructor 强约束出 AssemblyPlan。重试设硬上限，重试 token 单独计量不计入 ΔRepair | select.py + AssemblyPlan.json + 分桶 token 日志 | T1,T2,T3,T4 |
| T6 | 物化引擎对接 AssemblyPlan（走 M0 ts-morph）：pick=落盘+barrel append；adapt=候选+独立 adapter 文件；generate=单独 codegen 通道；dry-run 预览 | materialize 集成层 | T1,T2 |
| T7 | envVars 自动注入：append 进 env.js zod schema + 写 .env.example | env-sync 步骤 | T6 |
| T8 | 有界修复循环：install→诊断→确定性自动修→残余 error span±10 行回灌→AI override→重物化重跑。3 轮上限 + 震荡提前止损 | repair runner + 每轮 error/token 数组 | T6,T2 |
| T9 | 埋点 harness（arm 参数化）：error 序列、in/out token、WRITE_OWN 占比、ΔRepair。同一 runner 能驱动组装臂+从零臂 | harness + metrics.json | T5,T8 |
| T10 | 单想法从零对照臂（M1 必做，复用同一 gate+repair）：同模型从零生成同想法，跑同一闸门+3 轮修复，记录可单想法测的指标子集 | from-zero 产物 + 单想法双臂对照行 | T9 |
| T11 | "能跑"验收（M1 done 硬条件）：pnpm build + prisma generate + tsc/next build 二次确认 + pnpm dev 真启动 + 人工走通核心 flow；修复逐 commit 打 fix:/extend: 标签量 fix-diff | 启动日志 + flow 记录 + fix-diff 计数 | T7,T10 |
| T12 | 分层 git commit + 单命令端到端驱动：commit 分 picked/adapters/generated/各修复轮；一条命令串起全链路，组装臂+从零臂各一次 | 单命令 CLI + git 仓库 + 完整 metrics | T5,T7,T9,T11 |

## M2 GO 条件 / Kill 判据

**GO**：组装臂总成本 < 从零 **且** fix-diff < 从零 **且** h\* < 1 **且** WRITE_OWN 退化率 < 40% **且** 修复 3 轮收敛。

**失败归因（2×2 隔离，别靠直觉）**：
- 从零臂同 harness 也跑不通 → **harness/实现 bug**，先修 harness。
- 从零臂干净跑通、组装臂震荡 → **组装机制问题**。
- oracle 组装能跑、AI 组装不能 → **选择/披露层问题**。
- 连 oracle 组装都不通 → **core-fit/物化问题**（可能 create-t3-app 不适合当 core）。
- 确定性 import 路径/barrel 格式错 → **实现 bug**（修脚本后 error 整批消失）。

> 铁律：指责"赌注错了"之前，先证明 harness 能让从零臂和 oracle 组装跑通——这两个对照变量是唯一干净的归因锚点。

## 第一个技术风险（诚实排序）

1. **[第1天就爆]** create-t3-app 没有机器可读 seam 契约——它是一次性 scaffolder，无 manifest/无扩展点/无锚点。第一步就得人工在产物上手写 seam map + 插锚点。意味着"接口契合度排序"M1 没被真验证。
2. **[起项目时爆]** LSP 绿 ≠ 能跑——env/prisma/secret 全在盲区。
3. **[修复轮次爆]** 修复 thrash / ΔRepair——adapt/generate 与跨文件类型失配会震荡，h\*>1 即不可能赢。
4. **[选想法时爆]** WRITE_OWN 退化——手工小池下退化率很可能高，别挑"刚好被池覆盖的想法"自欺。
5. **[延后命门]** 意图摘要召回——M1 手工 mock 不爆，M3 真检索才暴露，标"已延后未验证"。
