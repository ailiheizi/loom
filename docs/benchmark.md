# Loom Benchmark：组装 vs 从零生成

> 日期：2026-06-16 ｜ 模型：deepseek-chat（单模型）｜ 候选池：39 候选 / 10 接缝 / SaaS后台+博客域

## 测什么

对同一个想法，对比两条路各自做出项目的代价与结果：

- **assembly（组装臂）**：Loom 检索候选 → AI 选择（pick）→ 确定性物化现成组件
- **from_zero（从零臂）**：不给候选，让同一个 AI（deepseek）从零写每个接缝的代码

两臂走**完全相同**的下游：物化 → 类型检查（tsc / ts-morph）→ 有界修复循环。唯一变量是"代码的作者"（策展的现成候选 vs AI 临场写）。

## 怎么测（公平性）

- **修复轮上限 maxRounds=8**（不是之前的 3）：让从零臂充分修复，修到**真收敛**或 **thrash 止损**（连续轮次错误数不降且指纹不收窄 → 判定改不动，提前停），而非被人为的"第 3 轮"截断。
- **收敛判定** = tsc 0 error（`gate.ts` 用 ts-morph，等价 `tsc --noEmit`）。
- token 只计 AI 的真实消耗：选择/生成的 output + 修复轮的 output。

> 复现：`bash .work/_honest_bench.sh && cd platform && PYTHONIOENCODING=utf-8 uv run python honest_report.py`

## 结果

| 想法 | 组装：轮/结果/out | 从零：轮/结果/out |
|---|---|---|
| saas-admin（Google登录+CRUD+表格+导出） | 0 修复轮 / ✅ 0 error / **329** | 2 轮 / ❌ thrash，剩 10 error / 3427 |
| task-tracker（GitHub登录+CRUD+表格） | 0 修复轮 / ✅ 0 error / **350** | 5 轮 / ❌ thrash，剩 2 error / 10525 |
| contact-book（Google登录+CRUD+表格） | 0 修复轮 / ✅ 0 error / **351** | 2 轮 / ❌ thrash，剩 4 error / 2646 |
| blog-platform（GitHub登录+CRUD+表格+markdown） | 0 修复轮 / ✅ 0 error / **371** | 2 轮 / ❌ thrash，剩 13 error / 8679 |
| **合计** | **4/4 收敛，1401 tok** | **0/4 收敛，25277 tok** |

## 核心结论

**主结论（定性，最重要）**：
> 单靠 deepseek 从零生成，**4 个想法 0 个修到能编译**（全部 thrash 止损，越修越乱卡在 2-13 个 error）。
> Loom 组装 **4/4 全部 0-error 收敛**，且 0 个修复轮（pick 的现成候选本就过过质量门）。
> **这不是"省多少 token"，是"从零做不出能编译的项目，组装做得出"。**

**附：output token（次要）**：
> 组装合计 1401 tok vs 从零 25277 tok = **组装是从零的 1/18（省 94.5%）**。
> 但这个百分比**低估**了真实差距——从零那 25277 token 买到的是 4 个编译不过的半成品（价值≈0），组装的 1401 token 买到的是 4 个能跑的项目。

## 诚实边界

- **单模型 deepseek-chat**。换更强模型（claude/gpt）从零臂收敛率很可能改善——0/4 是 deepseek 的能力上限，不全是"从零"范式本身的锅。换言之：模型越强，Loom 的相对优势越小。
- **"收敛" = tsc 0 error，非 next build / 真运行**。运行期错误（RSC 边界、路由）这层未自动验证。
- **thrash 止损 ≠ 修到尽头**。理论上无限轮 + 人工介入可能修好从零的产物，但那不是现实工作流。
- **样本小**：4 想法、单域、各 1 次（deepseek 有随机性，单次有波动）。这是量级参考，非统计严谨基准。
- 之前 README 的"省 91%"是旧的单样本 + 从零未充分修复的口径，已被本文档取代。

## 这个 benchmark 真正说明的

Loom 的价值不在"省百分之几的 token"（那随模型强弱浮动），而在：**把"能不能做出一个能编译的项目"从一件 AI 做不稳的事，变成一件确定的事**——因为组装的是过过质量门的现成代码，不是每次现写现赌。
