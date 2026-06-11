# Loom 最小验证实验：可执行清单

> 目标：用 2-3 人天，在**不建平台**的前提下，回答「组装 vs 从零」哪个更划算、修复循环可不可控、starter 起点够不够高。
> 场景固定为 **项目首次从零启动**（Loom 的唯一使用场景）。
> 对照：**臂1 组装**（Loom 设想机制）vs **臂2 从零**（bolt/v0/gpt-engineer 范式）。

---

## 0. 一句话方法

选 1 个现成 core + 手工策展一小撮真实组件 + 裸 tsserver，对 3-5 个想法各跑两臂，量 token 账 / 修复收敛性 / fix-diff 比 / WRITE_OWN 退化率。任一 kill 判据命中就停。

---

## 1. 固定变量（先拍死，别在实验里改）

| 项 | 选定 | 理由 |
|---|---|---|
| 生态 | Node/TS | LSP 最成熟(tsserver)，候选池最大 |
| 垂直域 | **CRUD SaaS 后台**（带 auth 的管理后台） | 接缝少、同质化高、组装赢面最大；候选好凑 |
| core | `create-t3-app`（Next.js + tRPC + Prisma + NextAuth + Tailwind 的某个固定勾选组合） | 现成、接缝清晰、本身就是配方式 |
| LSP | `typescript-language-server`（裸跑，pull diagnostics） | 第一闸门，确定性 |
| 模型 | 组装臂和从零臂用**同一个**模型（如 Sonnet 4.6） | 不混淆变量 |
| 修复硬上限 | **3 轮** | 防 thrash，到点强制收口 |

> core 用 `create-t3-app` 时先 `pnpm create t3-app@latest` 生成一份**固定配置**存下来当 base，每个想法都从这份 base 起，不重新生成。

---

## 2. 手工策展候选库（模拟平台，不建向量库）

挑 **3-4 个 seam**，每个准备 **2-3 个真实候选**（从真实开源项目里扒文件，不是自己写），共 5-10 个候选文件/组件。

| seam | 候选来源举例 | 接口契约（你手写成 L1） |
|---|---|---|
| `auth.oauth_provider` | NextAuth 各 provider 配置文件 | `(config) => Provider` |
| `payment.stripe_webhook` | 真实 repo 里的 Stripe webhook handler | `(req) => Response`，处理 `checkout.session.completed` 等 |
| `data.crud_resource` | 某 admin 模板的 resource CRUD 模块 | tRPC router：`list/get/create/update/delete` |
| `ui.data_table` | 某 shadcn-based 后台的表格组件 | `<DataTable columns rows />` |

**披露层手工模拟**（不写检索，用文件夹+清单代替）：
```
candidates/
  auth.oauth_provider/
    _L0.md          # 一句话能力摘要 + 依赖指纹 + LOC
    _L1.ts          # 只有导出签名/类型，不含函数体
    google-oauth/   # L2：完整源码（AI 要了才贴给它）
    github-oauth/
  payment.stripe_webhook/
    ...
```
- **L0** = 每候选一句话 + npm 依赖 + 行数（喂给 AI 做粗筛）
- **L1** = 导出签名 + 类型（多数情况 AI 看这层就能选）
- **L2** = 整文件源码（AI 明确要才给）

> 关键：**故意留一个 seam 没有合适候选**（如某个冷门需求），用来观测 WRITE_OWN 是否正确触发、生成质量如何。

---

## 3. AssemblyPlan 输出 schema（AI 的唯一产物）

AI 不写源码，只输出这个 JSON（这就是"选择即生成"，output 极小）：

```jsonc
{
  "seams": [
    {
      "seam": "auth.oauth_provider",       // core 暴露的接缝 id
      "action": "pick",                     // pick | adapt | generate | skip
      "ref": "google-oauth",                // 选中的候选（adapt/pick 时必填）
      "adapter": null,                      // adapt 时：需要的胶水说明（一句话）
      "confidence": 0.86,                   // AI 自评 0-1
      "why": "导出 GoogleProvider 符合 (config)=>Provider 接口"  // 一句话，可截断
    },
    {
      "seam": "report.custom_export",
      "action": "generate",                 // 无合适候选→自己写
      "ref": null,
      "generated_file": "src/server/export.ts",  // generate 时：真写的代码走单独通道
      "confidence": 0.5,
      "why": "候选均不支持 xlsx 导出，自写"
    }
  ]
}
```

物化规则（脚本做，不靠 AI）：
- `pick`：把候选 L2 整文件落到 core 的 target 目录，在 seam barrel 里 append 一行 `export`。
- `adapt`：落候选文件 + 让 AI 额外生成一个 adapter 小文件。
- `generate`：用 AI 写的 `generated_file`。
- `skip`：core 自带的占位保留。

---

## 4. 两臂跑法

### 臂1 组装
```
for 每个想法:
  1. 把想法 + 3-4 个 seam 的 L0 清单喂 AI
  2. AI 请求 L1（按需）→ 必要时请求 L2 → 输出 AssemblyPlan
  3. 脚本按 plan 物化（落文件 + barrel append + npm 装依赖）
  4. tsserver 收 pull diagnostics
  5. 有 error → 聚合成修复 prompt（只回灌 error span±10 行）→ AI 出 override → 重新物化 → 重跑 LSP
  6. 重复步骤 5，硬上限 3 轮；到 0 error 或触顶即停
  记录：每步 input/output token、每轮 error 数
```

### 臂2 从零
```
for 同一个想法:
  1. 直接让 AI 从零生成整个项目（同模型）
  2. tsserver 收 diagnostics
  3. 同样的修复循环，硬上限 3 轮
  记录：input/output token、每轮 error 数
```

---

## 5. 指标与埋点

| 指标 | 怎么量 | 数据源 |
|---|---|---|
| **总等效成本** | `output_tok + input_tok / 4`（r=4） | API response 的 usage 字段 |
| **ΔRepair（盈亏支点）** | 组装臂第0轮物化后→0-error 的累积 input token | 累加修复循环各轮 input |
| **修复收敛性** | 3 轮内是否到 0；error 数序列是降还是震荡 | 每轮 LSP error count |
| **compile_pass@pull** | 第0轮物化后的 error 数（越低越好） | tsserver diagnostics |
| **fix-diff 比（80分核心）** | 见下方拆分 | git diff --stat |
| **WRITE_OWN 退化率** | `action=generate 的 seam 数 / 总 seam 数` | AssemblyPlan 统计 |

### fix-diff 的关键拆分（区分"修"和"扩"）
到 0 error 后，人工把项目改到"能跑通核心 flow"，把改动**逐 commit 打标签**：
- `fix:` — 为了让它跑起来/接对（**算扣分**，这是起点不够 80 分的部分）
- `extend:` — 在它之上建业务功能（**不算扣分**，正常开发）

```
80分得分 = 1 - (fix 行数 / 总交付行数)
```
两臂都这么量，比的是 **fix 行数**——谁交付的起点更少需要返修。

---

## 6. Kill 判据（命中即停或转向）

| 判据 | 含义 | 动作 |
|---|---|---|
| 组装臂总成本 ≥ 从零 **且** fix-diff ≥ 从零 | 核心赌注证伪 | **kill 整个 v2** |
| 实测 h\* > 1（ΔRepair 等效成本 > 命中省下的 output） | 修复不可控 | 解决回灌最小化前不进工程 |
| WRITE_OWN 退化率 > ~40% | 候选池不足，退化成 codegen | 先解决"源项目池规模"再谈 |
| 0-error 后 fix-diff ≈ 从零 | "80分"是编译维度假分 | Gate-2 行为测试来源必须先解决 |
| 修复 3 轮不收敛（error 震荡） | thrash 坐实 | 硬 cap+定向回灌未解前不进工程 |

---

## 7. 产出物

一张表：3-5 个想法 × 两臂 × 6 指标。外加一段判断：**组装臂是否在 CRUD SaaS 后台这个最有利的垂直域里赢了从零？** 赢 → 下一步验证意图摘要召回 + 真实向量检索；没赢 → 这个最有利场景都赢不了，v2 不该进工程。

---

## 8. 不在本实验范围（故意不做）

- 不建向量库 / 不做真实检索（用手工 L0 清单代替）
- 不建 ingestion 管线 / 不解析大量 repo
- 不做 core 治理 / 上传更新 / 飞轮回流
- 不做多语言（只 TS）
- 不做 Gate-2 行为测试（只到 LSP 绿 + 人工 fix-diff 评估）
- 不做披露式展开的自动预算控制（人工按需给层即可）

> 这些都是"实验证明组装净赢之后"才值得建的重资产。先用最便宜的方式验最致命的假设。
