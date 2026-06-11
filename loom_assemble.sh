#!/usr/bin/env bash
# Loom 端到端组装：一句话想法 → 能编译的高起点 starter。
# 串起 platform 选择（deepseek 真 AI + 检索召回）→ client 确定性物化+gate+修复。
#
# 用法：
#   bash loom_assemble.sh <idea.json> [output_dir]
# 环境变量（LLM 渠道，必需）：
#   LOOM_LLM_PROVIDER=deepseek
#   LOOM_LLM_API_KEY=sk-...           deepseek key
#   LOOM_LLM_BASE_URL=https://api.deepseek.com   （默认）
#   LOOM_LLM_MODEL=deepseek-chat                 （默认）
#
# client 本身零 LLM（纯确定性物化+类型检查），只有 platform 选择层调 AI。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IDEA="${1:?用法: loom_assemble.sh <idea.json> [output_dir]}"
OUT="${2:-$ROOT/.work/loom-output}"

# 绝对路径化（避开 Windows cwd 不稳）
case "$IDEA" in /*|?:*) ;; *) IDEA="$(cd "$(dirname "$IDEA")" && pwd)/$(basename "$IDEA")";; esac

echo "[loom] 想法: $IDEA"
echo "[loom] 输出: $OUT"

# 选择阶段（platform，deepseek 真 AI + 检索召回子集，省 input）
echo "[loom] (1/2) AI 选择装配方案（检索召回 + deepseek 决策）…"
SEL_OUT="$( cd "$ROOT/platform" && uv run python run_select.py "$IDEA" --retrieve 2>&1 )" || {
  echo "$SEL_OUT" | tail -3; echo "[loom] ✗ 选择阶段失败。检查 LOOM_LLM_API_KEY。"; exit 1; }
echo "$SEL_OUT" | grep -E "pick|adapt|generate|WRITE_OWN" | sed 's/^/    /'

# 从选择输出里抓 plan 路径（run_select 打印 "plan 写入 .../assembly-plan-<id>.json"）
PLAN="$(echo "$SEL_OUT" | grep -oE '[A-Za-z]:[\\/].*assembly-plan-[^ ]*\.json' | tr '\\' '/' | tail -1)"
# 兜底：用 idea 文件名主干（idea_id 约定等于文件名）
[ -z "$PLAN" ] && PLAN="$ROOT/.work/assembly-plan-$(basename "$IDEA" .json).json"
[ -f "$PLAN" ] || { echo "[loom] ✗ 未生成 plan: $PLAN"; exit 1; }
echo "[loom]   plan: $PLAN"
echo "[loom]   plan: $PLAN"

# ── 2. 物化阶段（client，确定性：物化+建表+注入env+gate+有界修复）
echo "[loom] (2/2) client 确定性组装（物化 → 类型检查 → 修复）…"
( cd "$ROOT/client" && LOOM_OUT="$OUT" LOOM_PLAN="$PLAN" \
  node node_modules/tsx/dist/cli.mjs scripts/loom_materialize.ts ) || {
  echo "[loom] ✗ 物化阶段失败。"; exit 1; }

echo ""
echo "[loom] ✓ 完成。starter 在: $OUT"
echo "[loom]   下一步: cd $OUT && pnpm install && node node_modules/next/dist/bin/next dev"
