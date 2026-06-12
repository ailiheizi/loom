# 验池实验结果（Pool-Density Validation）

> 日期：2026-06-12
> 目的：验证 agent-native 愿景的盈亏地基——"候选池够密时，pick 现成组件是否真比从零 generate 净赢"。
> 结论：**GO（强信号）**。灌密后组装臂以 ~1/17 成本干净收敛，从零臂烧 4 轮修复仍不收敛。

## 实验设计

- **垂直域**：SaaS 后台。
- **灌密对象**：2 个高频 seam。`ui.data_table` 2→8、`report.custom_export` 1→6（新增 11 个零依赖真实候选）。
- **方法**：① 离线指标（零 LLM）测灌密前后"pick 可选度"；② 双臂对照（真调 deepseek）测 assembly(pick) vs from_zero(generate) 的 h\*。
- **LLM**：client/src/llm.ts 改造支持 OpenAI 兼容（deepseek），复用现有 key。详见"附：本次顺带修的真 bug"。

## 结果 1：离线 pick 可选度（零 LLM，可复现）

| seam | 灌密前可选度 | 灌密后可选度 |
|---|---|---|
| ui.data_table | 2 | 8（top5 召回 5） |
| report.custom_export | 1 | 6（top5 召回 5） |
| auth.oauth_provider | 3 | 3（未动） |
| data.crud_resource | 4 | 4（未动） |
| **可挑 seam（可选度≥2）** | **3/6** | **4/6** |
| **平均可选度** | **2.00** | **3.17** |

`report.custom_export` 从"单候选无可挑"变成"6 候选可挑"——这是"让架构师挑"从挑不起来到挑得起来的直接量化。

## 结果 2：质量门（verify_candidates，t3 严格 gate）

- 22/23 候选过门。**我灌密的 11 个零依赖候选 100% 通过** t3 严格 tsconfig（noUncheckedIndexedAccess 等）。
- 唯一失败 = 原有 `tanstack-data-table`（缺 `@tanstack/react-table` 外部依赖 TS2307，与灌密无关，verify 不装外部包）。

## 结果 3：双臂 h\*（真调 deepseek，灌密后池）

想法：saas-admin-with-google-auth（4 seam）

| 指标 | assembly（pick 现成） | from_zero（从零生成） |
|---|---|---|
| input_tok | 1756 | 7641 |
| **output_tok** | **340** | **7553** |
| equiv_cost | 779 | 9463 |
| 修复轮数 | 0 | 4（仍未收敛） |
| **converged** | **✅ true（0 error）** | **❌ false（3 error 残留）** |

**h\* = 0.0581**（组装成本约为从零的 1/17）。

错误收敛轨迹（from_zero）：round0=17 → round1=7 → round2=4 → round3=3，3 轮修复烧掉 retry_input=6305、retry_output≈3800，仍剩 3 个类型错没修掉（含黑名单文件 root.ts，AI 不许碰）。

## 一个意外但有力的旁证

灌密**前**，`report.custom_export` 池里只有 csv-export-fn，AI 对"导出 xlsx"的需求只能 **adapt（0.80）**。灌密**后**多了 excel-csv-export-fn，AI 直接 **pick（1.00）**。池密度让 AI 从"勉强适配"升级为"满分直选"——验池命题的活体证据。

## GO/NO-GO 判断：GO

- **离线**：灌密后目标 seam 可选度达标（pick 可选度 ≥3、可挑 seam 增加），质量门 100% 过。✅
- **双臂**：灌密后 assembly 干净收敛、from_zero 不收敛 + 成本高 17 倍。这不是"省一点 token"，而是**从零路径在该池密度下做不出能编译的项目，组装路径能**。✅

**对 agent-native 愿景的意义**：池密度是真命门，且可以靠灌密（零 LLM 的 ingest）解决。"每功能给 2-3 个真实候选让架构师挑 + pick 组装"这条路有数据支撑，值得继续投入到第二/第三步（候选级梯度呈现 → MCP server）。

## 诚实边界

- **h\*<1 不单独证真**（`run_compare.py` 自承：from_zero 的 synthetic 候选库构造可能单向压低组装臂成本）。本实验的强信号来自**收敛性差异**（assembly 收敛 vs from_zero 不收敛）+ **数量级差异**（17 倍），而非 h\* 绝对值。
- **样本小**：单想法、单垂直域、2 个 seam 灌密。结论不外推到其他域。
- **from_zero 用 deepseek-chat 生成**：换更强模型，from_zero 收敛率可能改善，h\* 差距可能缩小。但"组装零生成成本"的结构性优势不依赖模型强弱。
- **灌密候选来源**：11 个候选由 Claude 按各库真实 API 写出（非从开源直接摘取），均过 t3 严格质量门，但"作者是 AI"这点在可信度上需标注。

## 产物清单

- 新候选源：`.work/pool-density-src/{ui.data_table,report.custom_export}/`（11 个）
- 入池脚本：`platform/seed_pool.py`（零 LLM，幂等）
- 可选度指标：`platform/eval_pool_density.py`
- 双臂 metrics：`.work/metrics-{assembly,from_zero}-saas-admin-with-google-auth.json`
- h\* 报告：`.work/compare-saas-admin-with-google-auth.json`
- llm.ts 双 provider 改造：`client/src/llm.ts`、`platform/run_select.py`（anthropic 惰性导入）

## 附：本次顺带修的真 bug

1. `platform/run_select.py`：顶部无条件 `import anthropic`，导致 deepseek 模式也强依赖 anthropic 包（且会走错 Python 环境崩溃）。改为惰性导入，只在 anthropic provider 分支内 import。
2. `client/src/llm.ts`：原仅支持 Anthropic SDK。新增 OpenAI 兼容分支（`LOOM_LLM_PROVIDER=deepseek|openai` → fetch /v1/chat/completions），零新依赖，`complete()` 签名不变，三处调用方无需改动。这一步把"client 侧 LLM 可换 provider"落地了，也为后续"LLM 翻转/可插拔"铺路。
