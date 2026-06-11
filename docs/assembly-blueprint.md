# Loom 自组装蓝图（Assembly Blueprint）

> 用 Loom 自己的愿景作用于 Loom：把 `similar-projects.md` 里的 11 个项目当作"现成材料"，深挖它们的真实机制，给 Loom 写一份"哪层借哪个项目的什么机制"的组装配方。
> 方法：11 个项目各 1 agent 用 MCP/web 深挖真实机制 → 对位 Loom 四层 → 合成蓝图 → 对抗审校。
> **重要：审校发现蓝图把最硬的几个难点留成了空层。先读末尾"审校：致命缺口"再决定落地。**

## 一句话结论

可借的零件几乎都现成（aider 的 repo-map、Reposeek 的混合检索、Nx 的 Tree overlay、Backstage 的 action 注册表、SPL-FOP 的 SAT+FST、Bit 的依赖图、Unison 的内容哈希、Hoogle+ 的可达性求解）——**但 Loom 真正的护城河（从无边界的现成项目反向推断接缝）没有任何项目解决，必须自建。借来的件全都假设"接缝已存在"。**

## 四层组装配方

### L1 想法空间（想法 → 能力清单）
- **借 Cody** agentic loop + reflection：把"想法→能力"做成迭代细化，但**终止判据必须从 LLM 主观信心换成客观闸门**（可组合性校验通过 / 接缝测试 / token 上限）。
- **借 Cody** `contextFilters` 的 RE2 include/exclude：声明式 pattern 框定受控生态边界。
- **借 Reposeek** 查询塑形：产出"想 build on 的能力（品类+栈+约束）"而非让模型写代码。
- **要建**：把自然语言想法分解为 `能力清单 + 分面标签 + 接口签名草案 + 生态边界`，作为 L2 检索种子。

### L2 索引 Capsule（匹配现成项目）—— 多机制拼一层
- **借 aider**：tree-sitter `tags.scm` 多语言符号提取 + 符号引用图（networkx MultiDiGraph）+ PageRank + personalization + token 预算二分裁剪。**直接作为相关性排序与上下文压缩内核**，种子改成"用户想法关键词"。
- **借 Bit**：静态解析 import/require 自动生成依赖图 + 三分类（外部包 / 生态内模块 / 内部文件）——三分类直接对应"需 adapter 的边界 / 可组合单元 / 内聚实现"。
- **借 Reposeek**：摄取期 LLM 意图蒸馏 + 1536 维向量 + 混合检索（语义+词法 exact-match）+ 硬过滤与软排序解耦 + 证据优先输出契约。粒度须从整仓库下沉到"每个接缝的能力意图"。
- **借 Cody**：embeddings 语义为主 + keyword fallback，补齐精确符号/接缝名召回。
- **借 Unison**（仅思想）：规范化 AST 内容哈希作稳定身份与跨项目去重。⚠️ 见冲突。
- **借 Hoogle+**（仅思想）：Petri 网类型可达性 + TYGAR/CEGAR 抽象精化，把"可组合性校验"升级为"能否、按什么顺序接得上"的主动判定。⚠️ 见冲突。
- **检索流程**：标签硬过滤（license/生态准入/接缝兼容）→ 向量+符号图+依赖图三信号软排序 → 可组合性校验（依赖图缺口检测 + 可达性判定）。

### L3 配方与 IR（声明式组装）
- **借 Backstage Scaffolder**：YAML 三段式（parameters/steps/output）+ 字符串 id 引用的 action 注册表（`createTemplateAction` + zod input/output 契约）+ `ActionContext` 统一接缝契约（workspacePath+output()+checkpoint+dryRun+signal）。
- **借 create-t3-app**：`PkgInstallerMap` 的 `{inUse, installer}` 声明/执行解耦 + `dependencyVersionMap` 版本钉死 + `selectXxxFile` 汇聚文件集中选定。
- **借 SPL-FOP/FeatureIDE**：特性模型 → CNF → SAT 的 correct-by-construction 校验（拒绝非法组合、配置自动补全、void/dead/false-optional 检测）。
- **借 Hoogle+**：可达性 firing sequence 自动初始化 grafts/bindings 接线草案。
- **借 Unison**：name→hash 分离——接缝声明做成 `接口名→内容哈希` 映射，组装即编辑映射而非改代码本体。
- **要建**：manifest → 确定性 resolver 编译成 IR + 文件树，前置 SAT correct-by-construction 编译期门。

### L4 物化与补丁（最薄 AST 语义 diff 落地）
- **借 Nx devkit**：`Tree` 虚拟 FS overlay + `FileChange{path,type,content}` 统一变更清单 + dry-run（算清单不 flush）+ 同树复用（后装模块读前装产物=接缝对齐基底）+ `GeneratorCallback`/`runTasksInSerial` 延迟副作用。
- **借 SPL-FOP/FeatureHouse**：FST（名字+类型的语言无关语义树）+ superimposition（同名同类型递归叠加）+ `original()` 覆盖/包裹语义 + FSTGenerator（一份文法生成语言适配器）。**这是差异化 AST 补丁内核的蓝本。**
- **借 Plop/Hygen**：声明式接缝注入 + `skip_if` 幂等护栏 + core 预埋具名锚点（`// <loom-anchor:routes>`）+ add(新建) vs inject(增量) 前置存在性校验。
- **借 aider**：SEARCH/REPLACE 失败→模糊回退→反思重试三段式容错 + 逐步自动提交可回滚（用 AST 匹配替换其文本匹配）。
- **借 Bit**：capsule 隔离构建（复制文件+独立装依赖）做接缝测试沙箱 + snap 内容 hash 不可变锚点 + Ripple 沿依赖图反向重建。
- **要建**：在 Nx 式 overlay 之上自建 AST 层，把 UPDATE 类 FileChange 升级为 AST 节点级语义补丁。

### 横切（lock-provenance / 成本 / 测试闸门 / 增量）
- **Bit** snap/tag 内容 hash 做 lock-provenance + Ripple 反向传播增量重建。
- **Cody/aider** 便宜模型（Gemini Flash/Haiku）做 reflection/review、贵模型做核心决策 + token 预算硬上限。
- **SPL-FOP/Bit** golden 集成测试 + capsule 接缝测试作为所有迭代循环的统一客观终止判据。
- **Reposeek** request_id 关联 + "score 仅单响应内可比"的诚实约束，全链路可追溯（但保留排序信号透明，不照搬黑盒重排）。

## 示例：把 Loom 自身当作被组装的项目

体现你的核心设想——core 选定一个骨架、代码模块选几个、最终在程序上配置 diff、最小化写代码：

```yaml
# loom.manifest.yaml
apiVersion: loom/v1
kind: Assembly
name: loom-itself          # 被组装的目标 = Loom 这个工具本身

base:                       # core：选定一个骨架（中枢编排引擎）
  graft: backstage-scaffolder      # L3 骨架：YAML 三段式 + action 注册表 + ActionContext
  pin: "1.x"

grafts:                     # 代码模块：选几个现成项目，按层接到 base 上
  - id: cody-agentic-loop    from: sourcegraph-cody  seam: idea.refine
  - id: aider-repomap        from: aider             seam: index.ranking       # 符号图+PageRank+token二分
  - id: bit-depgraph         from: bit               seam: index.depgraph      # import静态解析+三分类
  - id: reposeek-ingest      from: reposeek          seam: index.ingest        # 意图蒸馏+混合检索+硬/软解耦
  - id: unison-hash          from: unison            seam: index.identity      # 规范化AST哈希做稳定身份
  - id: hooglep-solver       from: hoogle-plus        seam: index.composability # Petri网可达性=可组合性校验
  - id: featureide-sat       from: spl-fop           seam: resolve.correctness # SAT correct-by-construction
  - id: nx-tree              from: nx-devkit         seam: materialize.overlay # 虚拟FS overlay+dry-run
  - id: fst-superimposition  from: spl-fop           seam: materialize.astpatch # FST叠加=AST语义补丁内核
  - id: hygen-inject         from: hygen             seam: materialize.seam     # 幂等锚点注入护栏
  - id: aider-selfheal       from: aider             seam: materialize.faulttolerance
  - id: bit-capsule          from: bit               seam: materialize.seamtest # 隔离沙箱跑接缝测试

bindings:                   # 把各 graft 的异构接口适配到统一接缝（最小化手写胶水）
  - bind: aider-repomap.seed         to: cody-agentic-loop.capabilityTags  # 种子源：对话文件→L1能力标签
  - bind: bit-depgraph.edges         to: index.depgraph.in
  - bind: unison-hash.id             to: nx-tree.fileChange.anchor         # 内容hash→overlay不可变锚点
  - bind: hooglep-solver.firingSequence to: resolve.grafts.draft           # 可达性接线草案→manifest初始化

overrides:                  # 核心：在"程序上配置 diff"，把现成机制改造成 Loom 所需，而非重写代码
  - target: nx-tree.fileChange.UPDATE
    diff: "text-overlay → ast-semantic-patch(via fst-superimposition)"
  - target: hygen-inject.anchor
    diff: "regex-line-match → named-ast-anchor(// <loom-anchor:*>)"
  - target: cody-agentic-loop.terminate
    diff: "llm-subjective-confidence → objective-gate(seamtest-pass | token-cap)"
  - target: reposeek-ingest.granularity
    diff: "whole-repo-intent → per-seam-capability-intent"
  - target: featureide-sat.input
    diff: "L2 composability-signals → feature-model-constraints"

crosscutting:
  lock:        { provenance: unison-hash, incremental: bit-ripple }
  costControl: { reflect-model: gemini-flash, core-model: claude, token-cap: 32k }
  gate:        { seam-tests: bit-capsule, golden: integration }

# 结果：用户只写这份声明（选骨架+勾模块+几条 override diff），
# resolver 经 SAT 校验编译成 IR，L4 以最薄 AST 语义补丁物化落地，几乎不手写实现代码。
```

## MVP 推荐构建顺序

1. **L4 物化骨架**（可独立验证）：移植 Nx Tree overlay + FileChange 清单 + dry-run，先用整文件级跑通"声明→预览→flush→git回滚"，暂不接 AST。
2. **L4 AST 层**：引入 tree-sitter/ts-morph，落地 FST superimposition 把 UPDATE 升级为 AST 节点级语义补丁——这是最高风险机制，最早验证。
3. **L3 最小 resolver**：照搬 t3 的声明/执行解耦 + 版本钉死 + Backstage action 注册表，先不接 SAT。
4. **L3 SAT 门**：接 FeatureIDE 式特性模型，做非法组合拒绝/配置补全/死模块检测。
5. **L2 索引**：aider repo-map + Bit 依赖图三分类做骨架，叠 Reposeek 意图蒸馏+混合检索与 Unison 哈希，最后接 Hoogle+ 可达性。
6. **L1 + 横切收尾**：Cody loop（客观闸门）+ contextFilters；接通 lock-provenance、Ripple 增量、双模型成本控制、测试闸门。

---

## 审校：致命缺口（落地前必须先解决）

对抗审校的整体判断：**机制盘点扎实、风险自陈诚实，但系统性地把五大核心难点中最硬的几个留成空层或用前提不成立的借用件占位，当前不足以直接落地。**

### 6 大缺口
1. **接缝推断层完全缺位（致命）**：所有借来的项目（Bit/SPL-FOP/Nx/t3/Backstage）都假设接缝已存在；从"无边界的现成项目反向推断候选接缝"——这恰是护城河——没有任何层为它写实现。L2→L4 之间缺这层即整条链断裂。
2. **依赖地狱与 license 传染只标记不求解**：钉版本只是记录冲突不是消解冲突（graft A 需 lodash@3、B 需 @5）；缺真正的版本 SAT 求解器与 license 兼容格（lattice）推理。
3. **golden/接缝测试被当客观闸门，但测试来源未指定**：被组装的产物此前不存在，哪来 golden 测试？为尚未生成的产品生成行为测试本身是未解难题。
4. **graft 争抢同一接缝时缺仲裁语义**：FST superimposition 只处理同名同类型叠加，两个 graft 都想拥有路由/入口接缝时没有合并或裁决机制。
5. **省 token（难点 #3）零覆盖**：横切只声明双模型+32k 上限，无基线对比、无度量计划——前期评估明确警告"省 token 可能被实测推翻"。
6. **多源 Frankenstein 自相矛盾（难点 #4）**：评估说"多源拼装是最差模式"，而示例 manifest 恰恰把 Loom 自身从 11 个 graft 拼装，未论证为何不产生阻抗失配/不内聚。

### 关键机制冲突
- **Unison 内容哈希**：成立是因为 Unison 整门语言内容寻址、AST 无名字、支持 alpha 归一。套到任意 TS/Python/Go 上至多得"语法哈希"，遇宏/反射/重命名/副作用即破裂，语义等价本不可判定——与 aider 按名连边的符号图直接打架。
- **Hoogle+ 类型可达性**：工作在纯函数+强类型+策展小世界仍是指数级；TS 结构化/Python 动态类型不具备让"类型可达=可组合"成立的表达力，会产生大量"类型对但语义错"伪解。
- **SPL-FOP SAT**：特性模型是领域专家手写工件。从检索信号自动派生健全特性模型本身无解；约束错则 correct-by-construction 只是相对错误约束自洽（循环论证）。
- **最承重的 SPL-FOP（L3 SAT + L4 FST 双层承重）调研置信度空白**——最被依赖的机制族证据最弱。

### 最该先补的 6 项
1. 补建（或至少立项+界定范围）**接缝推断层**——护城河与断点所在。
2. 把**行为验证升为主闸门**并定义测试来源（非兜底）。
3. 引入真正的**依赖版本 SAT 求解 + license 兼容格推理**。
4. 核实 SPL-FOP 置信度，MVP 锁单语言（TS），**用真实任意仓库原型**验证 AST 合并（修正 build order 的风险倒置——别用已切好特性的合成输入自欺）。
5. 尽早搭 **token/成本基线对照实验**，再决定是否把双模型+32k 写进架构。
6. 正面处理**多源 Frankenstein 反模式**：为接缝适配器设连贯性预算与冲突上界，或显著削减 graft 数量。
```
