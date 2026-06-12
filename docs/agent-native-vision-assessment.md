# Agent-Native 愿景评估（2026-06-12）

> 评估对象：把 Loom 演进为可安装进 AI coding agent（Claude Code / opencode / codex）的对话式项目组装服务。
> 方法：5 视角并行评估（产品价值 / 技术架构 / 现状差距 / 风险命门 / 参照系），每条结论附仓库代码或文档证据。
> 一句话结论：**分发直觉（装进 agent）正确；但"server 侧 LLM"和"AI 自动生成架构梯度"这两个具体设计需翻转/降级，而真正的地基（候选池密度）尚未验证。**

## 待评估愿景（用户原始描述）

1. 用户把想法告诉 AI agent（client 侧，AI 是中介）
2. agent 把想法发给 Loom server
3. server 返回针对这个想法的**多个架构方案梯度**（从复杂 RBAC 到简单实现）
4. agent 能确定需求就选定继续，不确定就问用户
5. 逐功能、逐组件交互式收敛成完整项目
6. 关键设定：**LLM 始终在 server 侧，client/agent 不直接碰 LLM**

## 核心价值（成立的部分）

- **agent-native 分发是真红利**：装进用户已在的 Claude Code / codex，绕开"又一个独立 CLI/网站"的获客成本。shadcn MCP、Nx MCP 已验证此路径，值得早做。
- **"检索-组装而非生成"的范式倒置是真差异化**：v0/bolt/lovable 是一次性从零生成、架构决策不可见；Loom 从受控候选池挑现成组件拼装。这点定位成立（idea-evaluation.md、similar-projects.md）。

## 需要翻转的设计：LLM 应在 client 侧，不在 server 侧

愿景把推理放在 server 侧 deepseek，5 个维度一致判定这是反的：

- client 本身就是 Claude Code（Opus/Sonnet），比 server 侧 deepseek 强得多。
- "对话澄清、需求收敛、确定/不确定判断"正是宿主 agent 的母语。
- 把推理塞回 server 侧弱模型 = 用弱模型替强模型 + 重复造 agent 已做得更好的对话能力。

**正确分层**：
```
宿主 agent（client 侧）→ 听想法、对话澄清、判断、问用户
        │ 调 MCP 工具
        ▼
Loom server → 只做两件无状态的事：
   ① 给想法/能力返回真实候选菜单（检索现成池）
   ② 给定选择做确定性 verify + 物化
   LLM 在 server 侧只做很轻的事，甚至不做
```

"对话式渐进收敛"不需 Loom 实现——宿主 agent 天然在做。Loom 只需把候选摊给 agent。

> 注意红线冲突：现状 `client/src/repair.ts` 在 client 侧直接调 anthropic 做修复（与"LLM 只在 server 侧"矛盾）。要么搬到 server，要么（更好）交给宿主 agent。

## 最大的两个命门

### 命门 1：「架构梯度」目前是 0 引擎、纯人肉
代码里的"梯度"就是 3 个手写 json（`ideas/variants/saas-admin-{lite,std,full}.json`）。HANDOFF 自承"自动生成复杂度梯度难，是内容活非技术活"。对**任意**想法自动出梯度的引擎不存在，且是最难的部分。

### 命门 2：候选池太稀疏，「让你挑」挑不起来
现状 12 候选 / 6 seam，其中 **4 个 seam 只有 1 个候选**（导出 / markdown / 导入各 1）。只有 auth(3)、crud(4) 有真选择。"从 RBAC 到简单实现让你选"——池里**根本没有 RBAC 候选**。密度不够，"逐功能选代码"一半功能无可选，只能 generate，退化成更慢的 bolt。

> 这两个命门是 docs 早已点名的真命门（候选池规模 / 意图召回质量），愿景没解决，反而放大。

## 与现状的差距

**可直接复用（地基扎实，约省 4-6 人周）**
- 确定性物化 + 类型检查 + env 注入（`client/src/{materialize,gate,injectEnv}.ts`）——几乎不用改，正踩在愿景"client 侧确定性物化"的位置
- 检索排序 + 候选池 + 契约（`platform/retrieve.py`、`embedding.py`、`loom_contracts.py` ↔ `contracts.ts`）——当 server 能力底座
- 飞轮 + 质量门（`verify_candidates.py` / `flywheel.py` / `analyze_repo.py`）——候选池供给侧

**必须新建**
- MCP server 外壳（全仓零网络代码：grep 不到 fastapi/flask/express/createServer/modelcontextprotocol）
- "本地文件传递 → 网络下发 blob"的改造（耦合在 6 个文件，是硬工程，非包个 HTTP 能绕）：
  1. `loom_assemble.sh` 进程串联 + `.work/plan.json` 文件桥
  2. `run_select.py` 把 plan 写本地 `.work`
  3. `loom_materialize.ts` 读 `LOOM_PLAN/LOOM_OUT` 环境变量 + 本地 core 路径
  4. `loadCandidates.ts` 整个从本地 `candidates/` 读
  5. `materialize.ts` cpSync 本地 base + 从 `meta.dir` 本地读候选
  6. `repair.ts` + `llm.ts` client 侧直连 LLM（愿景红线）
- 「架构梯度生成引擎」（最难，未验证）

## 推荐落地路径

**第一步（先验池，不要先搭 server）**：在一个垂直域（SaaS 后台），用现成的 `analyze_repo.py` 飞轮把 2-3 个高频 seam 的候选从 1 扩到 8-12，再用数据回答 **"pick 现成"是否真比"从零 generate"净赢**。这是 refined-concept 早写明却被跳过的前置实验，是整个想法的盈亏地基。

**第二步（梯度降级为候选级）**：不要 AI 自由生成架构，而是用现有检索给每个 seam 返回 2-3 个真实候选（OAuth vs 密码登录、全 CRUD vs 只读列表），让宿主 agent 摊给用户挑。这是检索引擎免费就能给的、可 scale 的梯度，避开"AI 自动排复杂度难"的死结。

**第三步（才包 MCP server）**：装进 Claude Code，对话/收敛交给宿主 agent，Loom 只暴露 `propose_candidates` / `materialize` 两个无状态工具。会话状态推到 agent 侧，绕开 server 侧会话管理复杂度。

## 作者已拍板（2026-06-12）

1. **LLM 翻转到 client 侧** ✅：推理/对话/判断交给宿主 agent，Loom server 只做检索+物化，**deepseek 弃用**。后续须把 `client/src/repair.ts` 的 client 侧 LLM 调用移除/交给宿主 agent。
2. **梯度降级为候选级** ✅：放弃"AI 自动生成 RBAC→简单架构"，改为"每个 seam 给 2-3 个真实候选让用户/agent 挑"（现有检索引擎免费可给）。
3. **先验池** ✅：先灌密一个垂直域的候选池、用数据证明"组装比生成净赢"，再搭 server。
4. **目标用户 = 架构师** ✅：锁定关心架构决策的人（非新手）。影响呈现：候选要带架构取舍说明（依赖/复杂度/风险），让架构师据此判断，而非隐藏决策。

### 拍板后的下一步

**第一步（当前）= 验池实验**：在 SaaS 后台垂直域，用 `analyze_repo.py` 飞轮把 2-3 个高频 seam 的候选灌到 8-12 个，跑对照实验，用数据回答"pick 现成是否真比从零 generate 净赢"。这是整个愿景的盈亏地基。

## 附：被反转的既有决策（须重新论证才能推进）

`architecture-v2.md` 曾明确把场景收窄到"首次启动、用一次、单轮出一个 AssemblyPlan"，理由是只有单轮才能让修复循环有界、h\* 回到 0.46 赢面线。"对话式渐进、多轮交互收敛"重新引入了被砍掉的复杂度（增量更新 / 状态维护 / 多轮修复 thrash）。重开这个面之前，须重答 h\* 在交互式场景下是否仍有界。

---

_评估消耗：7 agent / ~62 万 token / 27 分钟。每条结论的文件证据见 workflow 原始输出。综合由主 agent 完成（workflow 综合步 agent 未正常产出）。_
