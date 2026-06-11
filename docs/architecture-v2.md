# Loom v2 架构（澄清版设计）

> 基于用户澄清后的真实设计：**AI 主战场是「选择」而非生成 + 披露式展开控 input + 文件/组件级拼装 + client 内 LSP 校验 + 接受高起点(80分)**。
> 方法：5 视角并行深化（入库向量化 / 披露式展开 / 选择引擎+兜底 / client+LSP / token经济）→ 合成 v2 → 对抗审校 + 最小实验。
> **结论先行：方向成立，但不要直接进全平台工程。先做末尾的双臂对照实验——几天出数，直接决定要不要投。**

## 使用场景收窄：仅用于「项目首次从零启动」

> Loom **只在项目第一次从零创建那一刻使用一次**。组装完交付一个能编译能跑的高起点 starter，之后用户用 aider/cursor 等自己维护——Loom 不参与持续演化。

这个收窄带来三个直接后果：

1. **修复循环天然有界，命门消失**：不追求修到完美，跑一遍 LSP + 自动修 + 兜底几轮，到「能编译能跑」就交付。上一轮审校最大的风险（修复 thrash 导致 `h*>1` 失控）基本不会发生，盈亏回到 h\*≈0.46 的赢面线上。
2. **砍掉一大批"持续维护"才需要的复杂度**：增量更新 / Ripple 反向重建 / rename 追踪 / content_hash 漂移 **全部删除**；"diff" 不是持续演化的 diff，就是**这一次组装**的 diff，落盘即结束。核心链路不变：ingestion → 向量匹配 → 披露式展开 → 选择 → client 物化 → LSP 跑一遍。
3. **竞品定位清晰**：不跟 aider/cursor（改已有代码）竞争，而是跟 **bolt / v0 / lovable / gpt-engineer（从零生成）** 抢"项目启动"那一下。差别一句话——**它们生成，Loom 组装**。

**「现成类似的」答案**：完整链路（匹配真实项目→组装→LSP 校验落地）**没人做**；但零件全现成（Reposeek 匹配、shadcn registry 装配契约、create-t3-app/Backstage 配方组装、Sourcegraph 检索）。形态有竞品（从零启动器），机制无人做（检索-组装而非生成）。这正是该赌的差异化。

**收窄未解决的两件事**（与"用几次"无关，与"策展了多少"有关）：① 候选池够不够大 / WRITE_OWN 退化率——不够则退化成"更慢的 bolt"；② 意图摘要召回率——"用想法找对组件"押在 LLM 摘要质量上。

**验收指标随之调整**：starter 的"80分"不是"还要改 20% 才完美"，而是"能编译+能跑+结构对"。实验的 post-pull diff 要拆成两类——**fix（为让它跑起来的修复，算扣分）** vs **extend（用户在其上建业务，正常、不扣分）**，只量 fix 部分。

## 核心结论（对抗审校）

> 你的赌注「选择比生成省」在数学上成立（r=price_out/price_in≈4~5，省 1 单位 output 可花 5 单位 input 去检索仍不亏）。**但真正的盈亏支点不是「披露式展开省钱」，而是「LSP 修复循环必须有界」——h\* 盈亏几乎完全由 ΔRepair（组装相对从零的额外修复成本）决定，命中率只是次要变量。**

## 端到端数据流（9 步）

```
0. [离线·平台持续] Ingestion：大量 repo 逐文件过 tree-sitter（铺底）+ SCIP（按需）
   → cAST 切成 符号/文件/组件 三粒度 → 每单元生成 代码向量+意图摘要向量 入 Qdrant
   → SHA-256/Merkle DAG 增量。core 平台自写/用户上传，走同管线+四道闸门，OCI+sha256 分发。
1. [想法分解] 自然语言想法 → capability intents（auth/session、payment/webhook…）
   每个 intent 对齐 core 暴露的一个 seam（接口/扩展点）。
2. [平台匹配] 组件级意图向量粗召回 → 对每个 (seam,capability) 混合排序：
   ①接口契合度（最强）②依赖可满足性 ③向量相似（显式降权，RACG 实证相似代码引噪声）④健康度。
3. [披露式展开] 4 层，广度铺底/深度只给决赛：
   L0 候选清单+能力摘要 → L1 接口签名 → L2 关键文件全文 → L3 依赖/调用链。
   core+重复前缀走 prompt caching(read=0.10x)。
4. [AI 选择/兜底] AI 只输出极小 AssemblyPlan：每 seam 一条 SelectionDecision
   {seam, action(pick|adapt|generate|skip), ref(内容寻址), confidence, why}。
   级联门控 coverage+margin 建议 action；input 触硬预算 B_in=α·r·O_gen_est 仍无 SELECT 强制收口。
5. [Client 拉取+物化] CLI 瘦客户端拉 manifest/lockfile + 内容寻址 blob。
   resolver 在 Nx Tree 虚拟 FS 确定性物化：Tier A 整文件落盘 + Tier B overlay 补丁
   （整文件 override / 具名锚点注入 / 结构化 op，放弃行号 diff）；barrel append-only 接入口。
   dry-run 出 FileChange 预览 → 确认 → 分层 git commit 可回滚。
6. [LSP Gate-1] client 内嵌 LSP（v1=tsserver），pull diagnostics 收 Error：
   未解析 import/类型错/缺依赖。能机器自动修的（add import、npm install）先自动修。
7. [修复回流] 剩余 error 按文件聚合（只回灌 error span±N 行，批量修）→ AI 出 override 补丁
   → 重新物化 → 重跑 LSP，循环至 0 error 或 iteration(≤2-3)/token 上限。
8. [飞轮回流] generate 产物过 Gate-1 后打包成 registry item 入 pending/，
   后台过同一 ingest 管线，provenance=synthesized 低初始健康度入池；被复用→健康度升→转 pick。
   用户上传走相同管线，provenance=user 给更高信任。
最终：git pull 下来一个 LSP 编译过/import齐/依赖齐的「高起点(~80分)可运行项目」。
```

## 主要组件及借鉴来源

| 组件 | 职责 | 借鉴 |
|---|---|---|
| 想法分解器 | 想法→capability intents→对齐 seam | Cody loop（客观闸门）+ Reposeek 查询塑形 |
| Ingestion 管线 | 逐文件解析→多粒度→双视图向量 | tree-sitter + SCIP + cAST + voyage-code-3 + Merkle 增量 |
| Core 注册治理 | core 强 schema + 四闸门 + OCI 分发 | t3 版本钉死 + OCI sha256 寻址 |
| 检索排序 | 接缝级检索，接口契合度首要、相似度降权 | Qdrant payload 硬过滤 + RACG 实证 + 级联门控 |
| 披露式展开 | 预算硬约束 4 层逐层取证 | Self-RAG control token + Stop-RAG 值函数 + MCP code-stub + caching |
| 选择+兜底 | 极小 AssemblyPlan，选不到才生成，回流飞轮 | shadcn registry 契约 + coverage/margin + adapter as item |
| Client 物化 | CLI resolver + Tier A/B + 分层 commit | aider git-native + Nx Tree overlay + Hygen 锚点 + Unison 寻址 |
| LSP Gate-1 | 第一闸门收诊断+自动修+回流 | tsserver + LSP 3.17 pull diagnostics + mcp-language-server |
| 经济治理 | h\* 模型设预算+监控膨胀+埋点 KPI | Claude/DeepSeek 真实价格 + caching + 便宜模型解析 |

## 平台侧数据模型（四类）

1. **Core**：`core_id` + semver + content_hash 双轨；manifest 声明 seam{接口签名/target目录/barrel入口/compat_range}；OCI+sha256 分发；四闸门 + provenance。
2. **候选 registry item**（复用 shadcn 契约）：`{path, type, target, dependencies(pinned), registryDependencies, cssVars, envVars}`；每文件 SHA-256 内容寻址；provenance(platform|user|synthesized)+健康度。
3. **向量+元数据**（Qdrant，多粒度×双视图）：组件/文件/符号级 × 代码向量+意图向量；payload={scip_symbol, 接口签名, import依赖, 外部包+版本+license, 能力摘要, 装配元数据}；缓存键含 embedding_model_version + chunker_version。
4. **AssemblyPlan**：`seams[]`（每条 SelectionDecision 极小）+ `synthesized[]`；展开动作也是结构化 tool call：`EXPAND/SELECT/WRITE_OWN/DROP`；client 拉取物 = manifest/lockfile（每文件→source@hash）+ blob 集。

## 披露式展开的 input 预算数学保证

设 `r = price_out/price_in ≈ 4~5`。从零生成成本 ≈ `price_out·O_gen`；选择成本 ≈ `price_in·I_disc + price_out·O_sel`（O_sel 极小）。
**选择更划算 ⟺ `I_disc < r·O_gen`**——披露 input 可达被省代码量的 ~5 倍仍不亏。
硬预算 `B_in = α·r·O_gen_est`（α≈0.5），累计 input 触顶仍无 SELECT 则强制收口。
两个放宽 margin 的杠杆：分层压缩（L0/L1 摘要/签名对单次决策有界）+ prompt caching（重披露 cached input≈0.1x，等效放大 r）。

**盈亏平衡：净赢 ⟺ 命中率 h > h\* = (入库摊销 + 披露input + ΔRepair) / (G·r)**
- 修复受控（ΔR≈1000）：h\*≈0.46 → 命中率 >46% 即赢（仓库级检索 EM 实测 60~66%，可达标）
- 修复失控（ΔR≈6900）：h\*=1.2 > 1 → **数学上不可能赢**。这就是为什么 ΔRepair 是命门。

## v2 相比 v1 消解了什么 / 新增了什么

**消解的 v1 致命缺口：**
1. **接缝推断（v1 致命断链）→ 彻底消解**。不再从无边界项目反推接缝；core 作为强 schema 实体**自己声明** seam。护城河从「接缝推断算法」转移到「core 治理 + 组装兼容性反馈数据」。
2. **AST 行级合并 + 三大脆弱机制（Unison哈希/Hoogle+可达/SPL-FOP FST）→ 整体消解**。锁定文件/组件级拼装 + barrel append-only，连带消解 graft 争抢接缝的仲裁难题（变成 append 幂等）。
3. **测试无来源被当闸门 → 部分消解**。第一闸门换成 LSP 诊断（确定性、便宜、无需预先存在测试）；行为测试降级为 Gate-2 兜底。
4. **省 token 零覆盖 → 消解**。给出 h\* 闭式模型 + caching 头寸 + 可埋点 KPI。
5. **多源 Frankenstein → 大幅缓解**。选择而非生成 + 接口契合度排序限制多源拼内核。

**v2 新增/转移的风险：**
1. **修复循环 thrash 成为真正的成本杠杆**（v1 没有的风险面）——盈亏几乎完全由 ΔRepair 决定。
2. **LSP 绿 ≠ 行为对**——只证编译/类型/import/依赖；Gate-2 测试来源仍是遗留缺口，只是被推后。「编译过但行为错」是隐性 bug，可能让 ΔRepair 不降反升。
3. **意图摘要质量成新命门**——「用想法召回项目」完全押在 LLM 生成的能力摘要上，最贵且随模型漂移。
4. **core seam 必须有稳定机器可读接口契约**——否则接口契合度退化为相似度，门控失准、胶水暴涨。
5. **兜底生成回流自我投毒 + 双付费陷阱**——高估命中率时深披露后仍 generate = 同时付披露 input + 全量 output，比从零更贵。

## 开工前必答（12 条精选 5 条盈亏决定变量）

1. **修复循环硬上限几轮 + 回灌策略**（定向 EXPAND vs 回退重选）——防 thrash，**盈亏决定变量**。
2. **Gate-2 行为测试从哪来**——组装时拉模块自带测试 vs AI 生成 smoke/契约测试。
3. **意图摘要召回率怎么离线评测**——整条管线召回命门。
4. **core seam 接口契约强制程度**——是否强制类型化扩展点 schema。
5. **可策展的接口干净源项目池有多大**（v1 遗留）——不够则频繁 WRITE_OWN 退化成 codegen。

---

## 最小实验（几天出数，不建平台）

> 审校判断：**不值得直接进全平台工程。最该先打的一枪不是搭 ingestion/向量库（最重最贵最晚才需要），而是双臂对照实验。** 若组装臂在单垂直域都赢不了从零，整个 v2 不该进工程。

**验证 3 个决定性假设：**
1. 单一垂直域，组装(选择) vs 从零生成，总等效 token 是否真省？
2. LSP 修复循环是否有界（实测 h\* 是否 >1）？
3. 「LSP 绿」到「行为对」的 gap 有多大（80分水分）+ 候选池够不够（WRITE_OWN 退化率）？

**Setup（2-3 人天）：**
- 不建平台、不建 Qdrant、不建治理。选 1 个现成 core（create-t3-app 或 react-spa starter）。
- 手工策展 5-10 个候选文件/组件，覆盖 3-4 个 seam（auth/OAuth、payment/Stripe webhook、session）。
- 接口签名手写成 L1 清单文件**模拟披露层**（L0=一句话摘要，L2=文件全文按需贴），省掉向量检索。
- 选 3-5 个想法（如「带 Stripe 的 SaaS 启动器」「带 OAuth 的待办」）。
- **臂1 组装**：手工逐层喂 L0→L1→按需 L2 → AI 输出 AssemblyPlan → 脚本物化 → tsserver 收 pull diagnostics → error 回灌 AI 修，硬 cap 3 轮。
- **臂2 从零**：直接让 AI 从零生成同一想法，跑同一 tsserver。
- 现成工具：tsserver、git（物化+diff）、API 返回的 token 计数。

**指标：**
| 指标 | 怎么量 |
|---|---|
| 总等效成本 | `output_tok + input_tok/4`，两臂逐想法对比 |
| **ΔRepair（盈亏支点）** | 组装臂从第0轮到 0-error 的累积 input token |
| 修复收敛性 | 3 轮内是否到 0 error；error 数单调下降还是震荡(thrash) |
| compile_pass@pull | 物化后第0轮 LSP error 数，两臂对比 |
| **post-pull diff 比（80分水分）** | 到 0 error 后人工改到「能跑通核心 flow」的改动行数/总行数 |
| WRITE_OWN 退化率 | AssemblyPlan 里 action=generate 的 seam 占比 |

**Kill 判据（出现即停/转向）：**
- 组装臂总成本 ≥ 从零臂 **且** post-pull diff 比 ≥ 从零臂 → 核心赌注证伪，**kill 整个 v2**。
- 实测 h\* > 1 → 修复循环不可控，解决回灌最小化前不进工程。
- WRITE_OWN 退化率 > ~40% → 候选池不足坐实，退化成 codegen。
- LSP 0 error 后 post-pull diff 比 ≈ 从零臂 → 「80分」是编译维度假分，Gate-2 测试来源必须先解决。
- 修复循环 3 轮不收敛（error 震荡） → thrash 坐实，硬 cap+定向回灌未解前不进工程。

**只有这个实验显示「组装净赢 + 修复收敛」，下一步才轮到验证意图摘要召回率与披露式展开的 input 控制。**
```
