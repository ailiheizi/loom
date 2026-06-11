# 类似项目调研

> 4 个方向并行联网调研。**总体发现：Loom 的完整链路（想法空间→匹配现成项目→组装→写 diff）目前由割裂的工具分段覆盖，没有一个产品端到端做"组装式开发"。** 空白点正是把"匹配真实项目"和"在其上组装并写 diff"缝成一条闭环——这是目前没人完整做的事。

## 链路分段现状（按 Loom 工作流对位）

| Loom 环节 | 现有代表 | 它们的边界 |
|-----------|---------|-----------|
| 想法→匹配现成项目 | **Reposeek** | 止于"选哪个仓库"，不组装、不 diff |
| 从零生成（对照组） | v0 / bolt / lovable / gpt-engineer | 复用粒度停在 UI 组件或模板，不复用"整个项目" |
| 在已有 repo 写 diff | **aider / Cursor** | 前提是"你已经有这个 repo"，无"匹配并引入外部项目" |
| 配方式组装模板 | Nx / Backstage / create-t3-app / cookiecutter / Plop | 组装的是作者预写死的模板，非动态匹配的真实项目 |
| 检索原材料 | grep.app / GitHub Code Search / Sourcegraph | 止于搜索/发现，不做组装与 diff |

## 高相关项目（high）

**Reposeek.ai** — https://reposeek.ai/
输入想法，像市场调研一样从开源生态推荐可作为基础的现成项目，告诉你该 fork、研究还是避开。
- 相似：与 Loom"想法→匹配现成项目"几乎正面重叠。
- 差异：只到"发现/推荐"就停，把组装与实现完全留给人类。**Loom 的机会就是接管它的下游**——拉取、组装、产出 diff，补齐闭环。

**aider** — https://aider.chat/
终端 AI 结对编程，用 repo-map 建上下文，以多种 edit 格式对多文件生成精确改动并自动 git 提交。
- 相似：精准命中 Loom 的"写 diff"环节，diff 驱动 + git 深度绑定。
- 差异：单仓库内编辑器，不做"匹配并引入外部项目"。**可借鉴其 repo-map + 多 edit 格式 + 自动提交的工程化做法**。

**bolt.new** — https://bolt.new/ ·  **v0.dev** — https://v0.dev/
从 prompt 直接生成可运行应用 / 生产级 React 组件（复用 shadcn/ui 原语）。
- 差异：本质"从零生成"，复用单位是模板/组件，不是"匹配并复用整个现成项目"。是 Loom 的**对照范式**。

**Nx Generators** — https://nx.dev/features/generate-code
generator 是接受参数的 TS 函数，通过 Tree API 增量改文件，可相互组合（composeWith）。
- 相似：最接近 Loom 的"组装"——原子生成器拼成大特性，Tree 做增量变更（概念接近 diff）。
- 差异：组装的是作者预写模板，不从真实项目空间语义匹配。**可借鉴 Tree 式可预览/可回滚的增量写入**。

**Backstage Software Templates** — https://backstage.io/docs/features/software-templates/
YAML 定义 Template，由有序 steps（action）组成流水线产出"golden path"项目。
- 相似：把脚手架抽象成可编排的步骤/动作流水线 + 表单输入。
- 差异：面向组织内固定 golden path，模板由平台团队预维护。**Loom 可借鉴 step/action 可插拔编排，但匹配源是真实项目而非内部模板**。这也是 Loom 的杀手级场景之一（见 refined-concept）。

**create-t3-app** — https://create.t3.gg/
每个技术栈片段（tRPC/Prisma/NextAuth/Tailwind）都是可选项，按勾选"按需生成"。
- 相似：鲜明的配方式/模块化组装，接近"按想法选模块再组装"。
- 差异：可选模块是预定义有限集，无开放匹配、无 diff 增量落地。

**Plop / Hygen** — https://plopjs.com/
微生成器，用 add/modify/append/inject 往现有项目增量写入或修改文件。
- 相似：强调对"已存在代码库"做增量改动，比 cookiecutter 更贴近"写 diff"姿态。
- 差异：仍依赖人工写好的模板片段 + 正则锚点。**可借鉴 append/inject 式增量改写作为 diff 落地实现**。

**Sourcegraph / Cody / Deep Search** — https://sourcegraph.com/
跨多仓库语义代码搜索与代码智能；Deep Search 用迭代搜索+依赖追踪回答自然语言问题。
- 相似：用代码库上下文/语义检索辅助写改代码，与想法空间匹配理念相通。
- 差异：聚焦企业内部代码库的理解/搜索，不做"跨开源项目组装+生成 diff"。

**Hoogle+ (TYGAR)** — https://github.com/TyGuS/hoogle_plus
给类型签名/IO 示例作规约，从现有库函数检索并自动组合出满足规约的程序（synthesis by composition）。
- 相似：核心机制与 Loom 一致——现成单元按需检索+组合，"规约→候选→组装"对位"想法→匹配→组装"。
- 差异：组装单元是单个函数（粒度远小于项目），靠类型/IO 精确规约而非自然语言。**可借鉴"类型/接口引导的候选剪枝"约束组装搜索空间**。

**软件产品线 / 特性导向编程 (SPL / FOP, 含 Foundry)** — https://ar5iv.labs.arxiv.org/html/2307.10896
按"特性"拆核心资产，用特性模型描述变体公共点/差异点，按选定特性组合生成产品变体。
- 相似："选一组特性→自动组合成产品"与 Loom"选匹配项目→组装"高度同构；特性模型本质就是一种"想法/能力空间"分类。
- 差异：面向单一受控库的预设变体，需预先建模，前期成本高。**可借鉴其"特性依赖/约束求解"保证 correct-by-construction**。

**Bit (bit.dev)** — https://bit.dev
组件市场+组合式开发平台：代码拆成独立版本化、可独立构建测试的组件，跨项目检索复用并 compose。
- 相似：最接近 Loom 的"市场+组装"产品形态，强调 composition over rewriting。
- 差异：组装单元是团队预封装的标准化组件，匹配靠人工浏览/关键词。**可借鉴其组件版本化/依赖图工程化经验**。

## 中/低相关（借鉴技术基础）

- **grep.app** — https://grep.app ·  **GitHub Code Search** — https://github.com/features/code-search：海量公开代码检索的"原材料层"，可作 Loom 上游。
- **gpt-engineer / Lovable** — https://github.com/gpt-engineer-org/gpt-engineer：纯"从零生成"范式，与 Loom 路线相反。
- **Cursor** — https://cursor.com/：全库语义索引 + 多文件 diff 编辑，但只面向"你自己的工作区"。
- **Yeoman / cookiecutter**：第一代脚手架基线（composeWith / Jinja 插值），Loom 应明显超越的低配方参照。
- **语义代码搜索 / 语义克隆检测**（学术，BigCloneBench/GPTCloneBench）— https://arxiv.org/html/2305.05959v2：按功能而非文本匹配，是"想法空间匹配"的核心技术基础。
- **IDEA: LLM + MCTS 设计空间探索** — https://arxiv.org/abs/2506.10587：把设计空间形式化为可搜索空间，可把 Loom 匹配阶段从启发式升级为评分引导的空间搜索。
- **Unison 类型导向检索** — https://www.unison-lang.org/blog/type-based-search/：内容寻址 + 接口检索，可给被组装片段稳定标识，降低版本漂移。
- **semble (MinishLab)** — https://github.com/MinishLab/semble：面向 agent 的省 token 代码检索组件。

## 一句话结论

可借鉴的拼图都已存在（Reposeek 的匹配、aider 的 diff、Nx/Backstage 的可编排组装、Hoogle+/SPL 的组合合成、Bit 的组件市场），**但没人把它们缝成"匹配真实项目→组装→diff"的闭环，且没人建"可组装性层 + 组装成功率反馈"这个真正的护城河**。
