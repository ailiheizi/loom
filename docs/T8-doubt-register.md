# T8 架构疑惑登记册（写 repair.ts 前的体检）

> 来源：6 子系统映射 + 6 维度交叉审计 workflow（13 agents，42 raw doubts → 18 去重）。所有 FATAL 项已对源码二次核验。
> 校正：`client/src/repair.ts` **完全不存在**（HANDOFF 说"写了一半"有误，是干净空白）。

## A 段 — 写 repair.ts 前必须拍板（T8 阻断项）

### A1. 重物化每次清空 outDir，无通用 override 通道 — FATAL ✅已核验
- 证据：`materialize.ts:71-72` 每次 `rmSync(outDir)` + `cpSync(baseDir,outDir)`。`MaterializeInput` 仅暴露 `generatedContent: Map<seamId,string>`（:32）；pick/barrel/prisma/env 无 override 入口。`gate.ts` 无状态（每次重读 tsconfig），所以"只重跑 gate"已被支持。
- 致命点：若修复改了文件、下轮又重物化 → 除 generate 内容外所有修复被静默擦除 → 必然 thrash → `converged=false`，恰好污染 M2 要测的收敛结论。
- 处置：**混合方案**。(1) generate 走 `generatedContent` Map，在 round-0 唯一一次 materialize 注入；(2) 其余修复（pick/barrel/prisma/env）**就地改 outDir + 只重跑 gate()，绝不重物化**（HANDOFF 选项 b）。零改 materialize.ts。

### A2. Project-model 接缝无法确定性收敛 — FATAL ✅已核验（4 层叠加缺陷）
- A2a 数据被剥离：`meta.json:27` 有 `requires_prisma_model:"Project"`，但 `contracts.ts:95-103 LoomMeta` 无此字段，`loadCandidates.ts:33` 用 `RegistryItem.parse` 剥掉未知键。`materialize.ts:125` 虽用 `as Record<string,unknown>` 强读，但读的是 zod 已清洗的对象 → 永远 `undefined` → `requiresPrismaModels` **恒为 []**。代码长得像处理了 #1 修复信号，其实是死代码。
- A2b 无 append 路径：即使拿到名字，`materialize.ts:128-138` 只做 import/register，**没有对 `prisma-models` 锚点（schema.prisma:77）做 MODEL_APPEND**。`BarrelOp.MODEL_APPEND` 契约存在但未接线。
- A2c 无 model 体：候选只带裸名 `"Project"`，字段定义哪里都没有。`project.ts` 查 `ctx.db.project.*` 但无 schema 体可 append。
- A2d 无子进程重生成 client：`db.ts` 的 `ctx.db.project` 类型来自预生成的 `generated/prisma/index.d.ts`；不跑 `prisma generate` 就不存在。client/src 全树 `child_process`/`prisma generate` = **0 命中**。
- 处置：做成**确定性 pre-AI fixer**（非 AI override）：① 修剥离（给 LoomMeta + loom_contracts.py 加字段，或像 barrel_snippet 一样读原始 JSON）；② 提供 Project model 体（候选 meta 加 `prisma_model_def` 或修复内置模板，**需决策来源**）；③ 在 prisma-models 锚点 append（导出私有 `appendAtAnchor`）；④ outDir 跑 `pnpm exec prisma generate` 再重 gate。**待决策：子进程是否在 M1 范围？** 否则此接缝不可收敛，必须在收敛判据里显式排除。

### A3. generate 接缝无内容 + xlsx 依赖未满足 — FATAL ✅已核验
- 证据：plan 里 `report.custom_export action=generate`，`generated_file=src/app/_components/export-button.tsx`，但 `generatedContent` 为空（`materialize.ts:94` 报"generate 缺内容"）。`why` 计划用 `xlsx`(SheetJS)，**确认未安装**。`SelectionDecision` 无 deps 字段，generate 接缝无候选→无依赖声明通道，唯一信号是 gate `TS2307`。子缺陷：generated_file 是客户端路径，而 `loom.core.json:56-69` 指定服务端 `src/server/export/` 签名 `(rows:T[])=>Buffer|Blob`，materialize 盲写。
- 处置：实现 `generateContents(plan,…)`：每个 generate 接缝 `llm.complete`+`extractCode` 填 Map 供 round-0。**system prompt 必须约束**：禁止引入 core 没有的运行时依赖；用浏览器原生 API 实现导出（CSV `Blob` + `URL.createObjectURL`）；锁定位置与签名到接缝 spec。这样 ~1 轮收敛、无需安装。同时校验 generated_file 落在 seam.target（解决客/服端矛盾）。

### A4. TS 侧从不产出 RepairRound/AssemblyMetrics；round-0 边界未定义 — FATAL(对M2)，阻断T8 ✅已核验
- 证据：`delta_repair_input = sum(r.input_tok for r in rounds[1:])`（`loom_contracts.py:340-344`），但 `rounds[]` 只由不存在的修复循环填 → **恒为 0**。`run_select.py:131` 建了 AssemblyMetrics 但 `__main__` 只写 assembly-plan.json，选择 token 只活在 `plan.budget`（input=129/output=515）。`contracts.ts:245-269` 有 zod 镜像但无代码构造。Python(选择) 与 TS(修复) 指标从不合并。
- 致命点：architecture-v2 说盈亏"几乎完全由 ΔRepair 决定"，而这个主导项结构上恒读 0 → 机械地报 h*≪1（假 GO）。
- 处置：每轮产出 `RepairRound{round_index, input_tok=resp.usage.input_tokens(含重计前缀), error_count, error_fingerprints}`。**钉死约定：round_index=0 = 初始 materialize+gate（0 修复 token）；修复轮 1..N**，使 `rounds[1:]` 干净隔离修复消耗。总量从 plan.budget 初始化，写 `.work/metrics-<arm>.json`。选择期 input 单列 `disclosure_input` 桶（T9 合并）。

### A5. 以 gate 指纹收敛 → 放过"类型对但行为退化"的修复 — HIGH，阻断T8 ✅已核验
- 证据：`gate.ts:28` 只收 `category===1` 的 TS 诊断（编译维度），指纹 `file:code`（:56），收敛目标 `errorCount:0` 自指。
- 致命点：AI override 可用 `as any`/`@ts-ignore`/删调用/改签名消掉 `TS2339`，gate 变绿、指纹收窄、循环宣告成功，却把行为债转移到 T11 盲区——这正是"80分假分"的生成机制，且是 repair.ts 写法的属性。
- 处置：override system prompt 禁止 `as any`/`@ts-ignore`/删逻辑灭错；每轮记 diff 行数入 RepairRound；repair.ts 输出注明 `errorCount:0` 仅编译维度信号，"done"须 T11 兜底。

### A6. 震荡/收敛判据须 指纹+计数 联合 — MEDIUM，T8 设计 ✅已核验
- 证据：`gate.ts:56` 指纹去重到 `file:code`，丢了行号/消息——同文件同 code 的 3 个错误塌缩成 1 个指纹。RepairRound 同时带 error_count 与 error_fingerprints。
- 处置：**指纹集严格收窄 OR error_count 严格下降**则继续；两者都不改善才判 thrash。两字段都已存在，填满即可。

### A7. loom.core.json 多半只编码接口形状、非行为 — HIGH(存疑)，T8 须先读 ⚠️证据缺口
- 提出此点的 analyst **没能读到该文件**，是唯一未直接核验的项。
- 处置：依赖 contract-fit 前**先读 loom.core.json**，枚举每个接缝实际约束了什么。若只有签名，把 contract-fit 当预筛、repair.ts 范围限于机械契合，不宣称行为正确。

## B 段 — 带入 T9–T12 / M2 判据的风险

### B1. M2 在 h*<1 上的 GO 结构上不可证；只有 Kill 有效 — HIGH
- 每个 mock 都把 h* **向下**偏：摊销缺席、L0 全量喂使 disclosure_input 虚低（真实 input=129、L2 从未展开）、6 个手挑候选对单冻结 base、无 prompt 缓存、ΔRepair 来自策展非检索。偏置单向 → 实测 h*<1 不能证真实系统 h*<1（拇指全压向 GO），但实测 h*>1 是稳健 Kill。
- 处置：重定义 M2 闸门：**h*>1 → 硬 Kill（有效）；h*<1 → 必要非充分**，GO 还需 WRITE_OWN<40% + 3 轮收敛 + fix-diff<从零 + 明注"成本优势在 M3 真检索前未证"。

### B2. h* 不可计算：G 未定义、摊销无字段 — HIGH
- 代码里无 `h_star` 函数（只在文档散文）。AssemblyMetrics 无 amortized、无 G。G=从零 total_output_tok 来自未建的 T10。`r=4` 硬编码。
- 处置：T9 harness 加显式 `h_star(assembly, from_zero)`，各项各有来源字段，**任一项未填则大声失败**而非默认 0。`G≡from_zero.total_output_tok`；同 idea_id 从零指标缺失则拒绝产出 h*。amortized 默认 None 标"M4 排除摊销"。

### B3. WRITE_OWN=0.25 是存在性证明非比率；池与检索未测 — HIGH
- 0.25=1.5/6，手策池+手挑想法 95%CI≈0.04–0.64；report 被故意清空逼出一个 generate。检索是 L0 全量喂（召回/精度/排序未测）。接缝对单冻结 base 手写→排序是拟合目标。WRITE_OWN<40% 是 GO 判据但其两个真实决定因素（池大小=M4、召回=M3）被推迟——延期件在为判据承重。
- 处置：GO/Kill 表里标 WRITE_OWN 与召回为"仅机制、M3/M4 前无外部效度"，描述性报告非闸门。M2 GO 范围缩到"选择+物化+修复在固定策展集上收敛且组装<从零"。

### B4. 全链路无行为正确性信号；80分是编译维度 — HIGH
- client/src 与 platform 无 test/assert/spawn。`injectEnv.ts` 写 `loom-dev-placeholder` 非空密钥让 env zod 过、Next 能起，但真实 OAuth/DB 调用必失败（auth flow 不可测）。T11 是一次性手动冒烟。T11 能暴露：启动抛错/prisma generate 失败/build SSR 错/404 白屏；不能暴露：CRUD 真写库/真 auth 回调/并发/边界。
- 处置：承认 80分=编译维度；把拉取后 diff 比作为 M2 必填数字，不用 gate errorCount 替代；T11 手动 flow 编码成可重跑脚本 + ≥1 个 tRPC 集成断言。

### B5. r=4 硬编码；prompt 缓存未埋点 — MEDIUM
- `equiv_cost` 写死 `input/4`（loom_contracts.py:337），源码无 cache_control/cache_read。
- 处置：单独抓 `cache_read_input_tokens`/`cache_creation_input_tokens`，用真实分层价算 equiv_cost，并先证网关（code.ppchat.vip）真按缓存分层计费再谈 r>4。

### B6. retry_input_tok 声明但从不写；reprompt 漏进 disclosure — LOW
- `loom_contracts.py:323-325` 声明 retry_input_tok"不计入 ΔRepair"，但 run_select.py 从不赋值，无 tool 的 reprompt 折进 total_input_tok。
- 处置：把 reprompt/非生产轮归到 retry_input_tok。

### B7. 范围相册：client+diff+LSP 过度宣称；死契约；依赖解析丢失；无 dry-run — MEDIUM/LOW
- 无客/服分离、无 CLI、无 diff 代码（仅未用的 fix_diff_lines 计数器）。gate=批量 getPreEmitDiagnostics 非实时 LSP。materialize 总是写（无 dry-run）虽文档说有。Manifest/Lockfile/BarrelMutation 是死代码。依赖解析 `lastIndexOf("@")` 对 `lodash`(=-1) 与 `@scope/pkg`(=0) 静默丢失（`materialize.ts:120-123`，注意条件是 `at>0`）。
- 处置：M2 叙事如实改标：gate="批量类型检查(tsc 等价)非 LSP"、diff=未开始、client 形态推迟。materialize 加 dryRun。T12 产 Lockfile、对齐 FileChange.kind 与 BarrelOp、`at<=0` 依赖按 name-only latest + 警告。

## T8 GO 决定

**repair.ts 现在可以写——但只能作为显式限定范围的"编译收敛循环"，不是承载判据的产物——且三个决策须先拍板：**

1. **循环架构（A1）**：确认 round-0 后只 gate 模型（就地改 outDir、重跑 gate()、绝不重物化；generate 走 generatedContent Map）。
2. **Project-model 范围（A2）**：定 `pnpm exec prisma generate` 子进程是否在 M1 范围，以及 Project model **体**来源（候选 meta vs 修复内置模板）。若子进程出范围，提前接受 data.crud_resource 不可收敛并从收敛判据排除。
3. **generate 接缝依赖策略（A3）**：确认"无新运行时依赖—浏览器原生导出"约束 vs 加安装路径。M1 推荐：无依赖重写。

**然后在这些显式假设下写：** 修 requires_prisma_model 剥离(A2a) + prisma-models MODEL_APPEND 作为 **pre-AI** 步骤；每轮产 RepairRound（round_index=0=初始 gate，修复轮 1..N）写 .work/metrics-<arm>.json；override prompt 禁 as any/@ts-ignore/删逻辑并记 diff 行；收敛=指纹收窄 OR 计数下降；contract-fit 仅当契合、**先读 loom.core.json**。

**repair.ts 不得宣称：** errorCount:0 = 行为正确(B4)，或任何 h* 授权 GO(B1/B2)。M2 闸门须先重定义为 **Kill-on-h*>1，永不 GO-on-h*<1-alone**。
