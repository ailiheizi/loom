# Loom 进化版设计：AI 编程的肌肉记忆

> 本文档供开发 agent 使用，按此设计实现。

## 一句话定位

**把 Loom 从"一次性组装 starter"进化成"持续学习的 AI 编程伴侣"——自动收录你写过的代码为可复用组件,下次碰到类似需求 AI 直接从你自己的组件库里挑着用,越用越强。**

核心差异化：别人的"代码记忆"是帮 AI 检索/想起代码在哪；我们的是帮 AI **直接复用你写过的代码做新项目**（记住 → 提取组件 → 复用组装 → 飞轮强化）。

---

## 架构流程

```
你写代码 → agent 调 loom_ingest(paths) → tree-sitter 提取组件 → 存入候选池(带 hash 去重)
                                                                     ↓
下次有需求 → agent 调 loom_propose → 检索候选池(embedding + 信任加权) → AI 选 → 组装
                                                                     ↓
组装成功 → flywheel.record_reuse → 该组件信任分上升(越用越靠前)
久没被用 → 信任分衰减(老组件沉底,不删除)
```

---

## 现有可复用模块(不要重写,直接改)

| 模块 | 位置 | 做什么 | 复用方式 |
|---|---|---|---|
| **ingest.py** | `platform/ingest.py` (166行) | tree-sitter 解析源码 → 提取 exports → 生成候选 JSON | 直接复用,加入自动触发入口 |
| **retrieve.py + embedding.py** | `platform/` | fastembed(BAAI/bge-small) + 余弦相似度检索 | 直接复用,检索时加信任加权 |
| **flywheel.py** | `platform/flywheel.py` (78行) | `record_reuse(seam_id, ref)` 记录复用,`harvest()` 统计 | 改成信任层:加 trust_score + 时间衰减 |
| **MCP server** | `platform/mcp_server.py` | 已有 `loom_propose`/`loom_plan`/`loom_get_files` | 新增 `loom_ingest` tool |
| **候选格式** | `candidates/*/` | JSON: name/description/files[]/seam_id/hash/meta_loom | 沿用,加 `trust_score` 和 `last_used` 字段 |

---

## 要新做的(按优先级)

### P0：新增 MCP tool `loom_ingest`（核心,第一步做这个）

**功能：** agent 写完代码后调用,把指定文件/目录自动收录成 Loom 候选组件。

**接口设计：**
```python
# MCP tool 定义
{
    "name": "loom_ingest",
    "description": "把你刚写完的代码收录进 Loom 组件库,下次碰到类似需求时可直接复用",
    "parameters": {
        "paths": ["src/auth/oauth.ts", "src/components/DataTable.tsx"],  # 要收录的文件
        "seam_hint": "auth.oauth_provider",  # 可选:建议的 seam 分类
        "description": "Google OAuth 登录 provider"  # 可选:人话描述
    }
}
```

**实现要点：**
- 调用已有的 `ingest.py` → `ingest_file()` 函数
- 如果 `seam_hint` 没给,用 AI 或规则推断 seam_id(文件路径/export 名推断)
- 生成候选 JSON 存入候选池目录
- 自动计算 embedding 并存入向量索引(调 `embedding.py`)
- content hash 去重:如果 hash 已存在,更新 `last_ingested` 时间戳而非重复添加

**实现位置：** 在 `platform/mcp_server.py` 中新增 tool handler,内部调用 `ingest.py`。

---

### P1：信任加权检索

**改动位置：** `platform/retrieve.py` + 候选 JSON 格式

**候选 JSON 新增字段：**
```json
{
  "meta_loom": {
    "seam_id": "auth.oauth_provider",
    "trust_score": 0.5,
    "times_reused": 0,
    "last_used": null,
    "ingested_at": "2026-06-28T..."
  }
}
```

**检索评分公式（参考 memory-engine 的信任层）：**
```python
effective_trust = trust_score * 0.5 ** (days_since_last_use / HALF_LIFE_DAYS)
final_score = semantic_similarity * (0.7 + 0.3 * effective_trust)
# 语义相似度仍是主要因子,信任分做加权调整(不会完全覆盖语义)
```

**参数(可调)：**
- `HALF_LIFE_DAYS = 30`（30天未使用信任减半）
- 新收录的默认 `trust_score = 0.5`
- 被复用一次 → `trust_score = trust + (1 - trust) * 0.2`（向1靠拢）
- pinned 组件不衰减（手工策展的核心组件）

**实现：** 改 `retrieve.py` 的排序逻辑,把 `_cosine()` 结果乘以 effective_trust。

---

### P2：复用反馈(飞轮强化)

**改动位置：** `platform/flywheel.py`

**现有 `record_reuse(seam_id, ref)` 已做了复用记录。** 要加的：
- 调 `record_reuse` 时同步更新该候选的 `trust_score`（向1靠拢）和 `last_used` 时间戳
- 这样下次检索时,常用组件自然排前面

---

### P3：去重

**触发：** `loom_ingest` 时,对每个文件计算 content hash（已有 `_sha256()` 函数在 ingest.py 里）。

**逻辑：**
- hash 已存在 → 更新 `ingested_at` 时间戳,不重复创建候选
- hash 变了(代码改了) → 创建新版本 or 更新已有候选的文件内容

---

### P4：跨项目候选池

**现状：** 候选存在 `项目目录/candidates/` 下,只对当前项目有效。

**改成：** 支持全局池 `~/.loom/candidates/`（用户级,跨项目共享）+ 项目局部池（`./candidates/`）。检索时两个池都搜,全局的是"你所有项目的经验"。

**配置（环境变量或 config）：**
```
LOOM_GLOBAL_POOL=~/.loom/candidates
LOOM_LOCAL_POOL=./candidates  # 项目内
```

---

### P5（可选,第二阶段）：memory-engine 集成

**想法：** 用 memory-engine 的信任层替代 P1 里手写的信任逻辑(memory-engine 已有成熟的 trust+衰减+强化)。

**可行性：** 两个项目都是 Python,memory-engine 可作为依赖 import。但 MVP 阶段先在 Loom 内简单实现(P1的公式够用),别引入外部依赖增加复杂度。等 MVP 跑通了再考虑统一。

---

## 实现顺序（1-2周 MVP）

**第1周（核心链路跑通）：**
1. P0：`loom_ingest` MCP tool — 能收录文件成候选 ✅ 验证：调一次能在候选池里看到新组件
2. P1：信任加权检索 — 有 trust_score 的组件排序靠前 ✅ 验证：收录的组件能被检索命中
3. P2：复用反馈 — 组装成功后 trust 提升 ✅ 验证：record_reuse 后该组件下次排名上升

**第2周（完善）：**
4. P3：去重（hash 判定）
5. P4：跨项目池（~/.loom/candidates/）
6. README 更新（新定位 + 演示 gif）

---

## 验证标准（做完怎么知道成了）

- [ ] `loom_ingest` 被调用后,候选池里出现新组件
- [ ] 该组件下次被 `loom_propose` 检索命中(语义相关时)
- [ ] 被复用后 trust 上升,下次排名更靠前
- [ ] 相同代码重复 ingest 不会创建重复候选
- [ ] 跨项目:项目A收录的组件,在项目B也能被检索到

---

## 文件改动清单

| 文件 | 改动 |
|---|---|
| `platform/mcp_server.py` | 新增 `loom_ingest` tool handler |
| `platform/ingest.py` | 加入被 MCP tool 调用的入口函数(可能已有,确认) |
| `platform/retrieve.py` | 检索评分加 trust 加权 |
| `platform/flywheel.py` | `record_reuse` 时更新 trust_score + last_used |
| `candidates/` 下的 JSON | meta_loom 新增 trust_score/last_used/ingested_at |
| `platform/embedding.py` | 可能无改动(收录时自动算 embedding 已有逻辑) |
| `.loom/` 或 config | 新增全局池路径配置 |
| `README.md` | 更新定位 + 新功能说明 |

---

## 相关工作与借鉴（竞品分析）

> 以下项目和论文与我们方向相关,做的时候可参考它们的实现思路、避免重复造轮子,同时明确我们的差异化在哪。

### 代码记忆类（检索/索引方向——它们做的是"帮AI想起来",我们做的是"帮AI复用"）

| 项目 | 地址 | 做什么 | 可借鉴 | 和我们的区别 |
|---|---|---|---|---|
| **codebase-memory-mcp** | github.com/DeusData/codebase-memory-mcp | 把代码库索引成知识图谱,AI查询时能"记住"项目结构 | 索引方式、MCP tool 设计 | 只做检索/记忆,不做"提取组件+组装" |
| **cipher (Byterover)** | github.com/campfirein/cipher | 给coding agent做memory layer,跨会话记住上下文。兼容Cursor/Claude Code等 | MCP接口设计、跨客户端兼容 | 记的是对话上下文,不是"代码变组件" |
| **mcp-memory-keeper** | github.com/mkreyman/mcp-memory-keeper | 持久化上下文管理(key-value) | 简洁的MCP记忆接口 | 通用记忆,不针对代码复用 |
| **CodeGraph** | 47k stars | 代码知识图谱,预索引后agent查询精准度大增 | 知识图谱构建思路、tree-sitter用法 | "查找"不是"复用组装" |
| **Mem0 + Codex** | mem0.ai/blog | 让Codex记住代码库 | RAG for code 的实践 | RAG检索,不是组件提取+组装 |

### 代码复用/自我进化类（最接近我们方向的学术工作）

| 论文/项目 | 来源 | 做什么 | 可借鉴 |
|---|---|---|---|
| **"Learning Self-Evolving Skills for Coding Agents"** | arxiv 2605.25430 (2026) | agent从经验中学习可复用skill,自动提取+下次调用 | **最接近我们的想法**——skill提取的触发方式、怎么从代码轨迹中抽象出可复用单元 |
| **"From Trajectories to Reusable Expertise"** | arxiv 2601.22758 (2026) | 把agent执行轨迹变成可复用技能库 | 轨迹→技能的抽象方法,和我们"代码→组件"类似 |
| **self_improving_coding_agent** | github.com/MaximeRobeyns/self_improving_coding_agent | 在自己代码库上工作的自我改进agent | 自我改进循环的实现 |
| **Ponytail** | github.com/DietrichGebert/ponytail | 教AI"先看有没有现成的再写"的prompt规则集 | "选择优先于生成"的理念（和Loom一致）,但它只是规则没有组件库 |

### 记忆/信任层（信任加权检索的参考实现）

| 项目 | 做什么 | 可借鉴 |
|---|---|---|
| **memory-engine (我们自己的)** | RAG + 信任加权 + 时间衰减 + LoRA性格 | **直接搬信任层逻辑**:`trust * 0.5^(未使用天数/半衰期)`,强化/衰减公式 |
| **Hermes (论文)** | 对话记忆的信任加权重排 | 信任分设计的学术依据 |
| **agent-memory-mcp-server** (PyPI) | agent长期记忆MCP | MCP接口设计参考 |

### MCP生态工具（MCP server怎么做的参考）

| 项目 | 可借鉴 |
|---|---|
| **mcpm.sh** (pathintegral-institute) | CLI MCP包管理器的命令设计 |
| **Berth** (Rust) | Rust实现的MCP管理工具,含安全功能 |
| **mcp-audit** (Rust) | MCP安全扫描的实现 |

### Token压缩（组装式编程的另一个佐证——复用=省token）

| 项目 | 说明 |
|---|---|
| **llmtrim** (Rust) | LLM代理压缩(AST级),证明了"少生成=省钱"的市场需求 |
| **claw-compactor** | 6层确定性压缩,97% token节省 |
| **rtk/Headroom** | token可视化+节省工具,证明"省token"的传播力 |

---

### 我们的差异化（对照上面所有竞品,我们独有的）

1. **从"记住"到"复用"的完整闭环**：竞品停在"索引/检索/记忆",我们走完"收录→提取组件→复用组装→飞轮强化"的全链路
2. **确定性组装**：复用不是RAG检索后丢给AI让它自己写,而是**确定性物化**(拼装+类型检查+修复),这是Loom已有的核心能力
3. **信任层(飞轮)**：越用越好的组件排名机制——组件"活着"会成长,而不是死的静态库
4. **你自己的代码优先**：不是从公共库/网上抄,是**你写过的、验证过的代码**成为第一优先候选
5. **MCP原生**：不是IDE插件(绑死一个编辑器),是MCP server(任何支持MCP的agent都能用)

---

## 新定位（README 用）

**旧：** "组装式开发：不从零写代码,从候选库挑现成组件拼装"

**新：** "AI 编程的肌肉记忆：自动学习你写过的代码,下次直接复用。越用越强。"

英文：`"Muscle memory for AI coding — auto-learns from your code, reuses it next time. Gets better the more you use it."`
