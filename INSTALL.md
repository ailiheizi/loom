# Loom 安装指南（给 AI 读：你可以照这个自己把 Loom 装好）

> 这份文件是给 AI 工具（claude code / cursor 等）读的。按下面步骤检查环境、安装缺失项、
> 配置 LLM 渠道、注册 skill。每步都给了**检查命令**和**失败时的安装命令**。
> 全程用绝对路径（Windows 下 bash cwd 不稳）。项目根记为 `$ROOT`。

## 0. 确认项目根

```bash
ROOT=/d/windows/code/project/Loom   # 改成实际路径
ls "$ROOT/loom_assemble.sh" "$ROOT/platform" "$ROOT/client"   # 三者都在 = 路径对
```

## 1. 运行时依赖（检查 → 缺则装）

| 工具 | 检查 | 缺则装 |
|---|---|---|
| Node ≥20 | `node -v` | 装 Node LTS |
| pnpm | `pnpm -v` | `npm i -g pnpm` |
| Python ≥3.12 | `python --version` | 装 Python |
| uv | `uv --version` | `pip install uv` 或 `pipx install uv` |

## 2. client 依赖（TS）

```bash
cd "$ROOT/client" && pnpm install
# 验证：node node_modules/typescript/bin/tsc --noEmit   → 应 exit 0
```
注意：client 的 tsx 跑法是 `node node_modules/tsx/dist/cli.mjs <script>`（`pnpm exec tsx` 有 esbuild 预检坑）。

## 3. platform 依赖（Python，含检索/ingest）

```bash
cd "$ROOT/platform" && uv sync
# 检索 embedding（本地，离线）：
uv run python -c "import fastembed" || uv add fastembed
# ingest（tree-sitter 解析）：
uv run python -c "import tree_sitter_typescript" || uv add tree-sitter tree-sitter-typescript
# 验证检索：uv run python eval_retrieval.py  → recall@1 应 ~100%
```
注意：platform 一律用 `uv run python`（全局 python 的 pydantic 版本冲突）。

## 4. LLM 渠道（选择层要调一次 AI；client 物化零 LLM）

Loom 只在"选择装哪些组件"这步调 AI。配一个可用渠道（二选一）：

**deepseek（推荐，OpenAI 兼容）**：
```bash
export LOOM_LLM_PROVIDER=deepseek
export LOOM_LLM_API_KEY=sk-xxxxx          # 用户的 deepseek key
export LOOM_LLM_BASE_URL=https://api.deepseek.com   # 默认值，可省
export LOOM_LLM_MODEL=deepseek-chat                 # 默认值，可省
# 验证：curl -s -m 15 -X POST "$LOOM_LLM_BASE_URL/chat/completions" \
#   -H "Authorization: Bearer $LOOM_LLM_API_KEY" -H "Content-Type: application/json" \
#   -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":5}'
#   → 返回 JSON 含 choices = 通
```

**anthropic 网关（若可用）**：设 `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`，不设 `LOOM_LLM_PROVIDER`。
（注：已知 code.ppchat.vip 网关可能不稳/无 embedding 通道，故 embedding 用本地 fastembed。）

## 5. 注册 skill（让 claude code 能一句话触发）

skill 已在 `$ROOT/.claude/skills/loom/SKILL.md`。若要全局可用，软链或拷到用户级：
```bash
# claude code 项目内自动发现 .claude/skills/；全局用拷到 ~/.claude/skills/loom/
cp -r "$ROOT/.claude/skills/loom" ~/.claude/skills/   # 可选
```

## 6. 冒烟测试（确认整条链路通）

```bash
# 纯本地、不调 AI 的验证（确认 client+检索+ingest 都就绪）：
cd "$ROOT/platform" && uv run python eval_retrieval.py && uv run python eval_writeown.py
cd "$ROOT/client" && node node_modules/typescript/bin/tsc --noEmit

# 端到端（需 LLM key，用现成想法）：
LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=$KEY \
  bash "$ROOT/loom_assemble.sh" "$ROOT/ideas/saas-admin-with-google-auth.json" "$ROOT/.work/smoke"
# → 末尾打印 "✓ 完成。starter 在: ..." + converged=true
```

## 装好后怎么用

见 `.claude/skills/loom/SKILL.md`。一句话：用户描述想法 → AI 写成 ideas/*.json →
`loom_assemble.sh` 一条命令出 starter。
