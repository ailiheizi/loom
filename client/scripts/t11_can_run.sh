#!/usr/bin/env bash
# T11 "能跑"验收脚本（可重跑）。
# 用户已定边界：只验"能启动"——next build 过 + pnpm dev 真起来，
# 诚实标注核心 flow 走不通（缺页面装配接缝 + 占位 OAuth 凭据）。
#
# 用法：bash scripts/t11_can_run.sh [assembly_dir]
# 默认 assembly_dir = .work/t9-assembly
set -uo pipefail

ROOT="/d/windows/code/project/Loom"
ASM="${1:-$ROOT/.work/t9-assembly}"
LOG="$ROOT/.work/t11-run.log"
: > "$LOG"

say() { echo "[t11] $*" | tee -a "$LOG"; }

say "验收对象: $ASM"
[ -d "$ASM" ] || { say "✗ assembly 目录不存在"; exit 1; }
cd "$ASM" || exit 1

# ── 前置 1：补齐 env 空串（Discord 是 base 自带 provider，Loom 没注入其 env）
say "前置1: 填 Discord 占位 env（否则 emptyStringAsUndefined→zod throw）"
if grep -q 'AUTH_DISCORD_ID=""' .env; then
  # 用占位值替换空串（仅为过 zod 启动校验，不接真 Discord）
  sed -i 's/AUTH_DISCORD_ID=""/AUTH_DISCORD_ID="loom-dev-placeholder"/' .env
  sed -i 's/AUTH_DISCORD_SECRET=""/AUTH_DISCORD_SECRET="loom-dev-placeholder"/' .env
  say "  已填 AUTH_DISCORD_ID/SECRET 占位"
else
  say "  Discord env 已非空，跳过"
fi

# ── 前置 2：prisma db push 建 sqlite 表（无迁移历史，适合 M1）
say "前置2: prisma db push 建库"
PRISMA="node_modules/.bin/prisma"
if [ -f "${PRISMA}.CMD" ] || [ -f "$PRISMA" ]; then
  ( "${PRISMA}" db push --skip-generate 2>&1 || "${PRISMA}.CMD" db push --skip-generate 2>&1 ) | tee -a "$LOG"
  [ -f prisma/db.sqlite ] && say "  ✓ db.sqlite 已建" || say "  ⚠ db.sqlite 未见（看上方输出）"
else
  say "  ✗ 找不到 prisma 二进制"
fi

# ── 验收 1：next build（全量静态：编译+类型+SSR 预渲染）
# 直调 next 二进制，绕过 pnpm 包装的 deps 检查（cpSync 物化的 node_modules 虚拟 store
# 位置与 base 不一致，pnpm install/build 会想 purge node_modules 并在非 TTY 下中止）。
NEXT_BIN="node_modules/next/dist/bin/next"
say "验收1: next build（全量静态构建，直调 next 二进制）"
BUILD_OK=0
if node "$NEXT_BIN" build > "$ROOT/.work/t11-build.log" 2>&1; then
  say "  ✓ next build 通过"
  BUILD_OK=1
else
  say "  ✗ next build 失败（详见 .work/t11-build.log，尾部）"
  tail -25 "$ROOT/.work/t11-build.log" | tee -a "$LOG"
fi

# ── 验收 2：next dev 真启动探活（起来→抓 Ready→关掉）
say "验收2: next dev 真启动探活"
DEV_OK=0
DEVLOG="$ROOT/.work/t11-dev.log"
: > "$DEVLOG"
# 后台起 dev server（直调 next 二进制）
node "$NEXT_BIN" dev > "$DEVLOG" 2>&1 &
DEV_PID=$!
# 最多等 60s 出现 Ready / 错误
for i in $(seq 1 60); do
  if grep -qiE "Ready in|started server|Local:.*http" "$DEVLOG"; then
    DEV_OK=1; break
  fi
  if grep -qiE "Invalid environment variables|Error:|throw|EADDRINUSE" "$DEVLOG"; then
    break
  fi
  kill -0 "$DEV_PID" 2>/dev/null || break
  sleep 1
done
if [ "$DEV_OK" = 1 ]; then
  say "  ✓ pnpm dev 启动成功（server Ready）"
else
  say "  ✗ pnpm dev 未就绪（启动日志尾部）"
  tail -20 "$DEVLOG" | tee -a "$LOG"
fi
# 关掉 dev server（含子进程）
kill "$DEV_PID" 2>/dev/null
pkill -P "$DEV_PID" 2>/dev/null
sleep 1

# ── 结论
say "──────── T11 结论 ────────"
say "next build: $([ "$BUILD_OK" = 1 ] && echo 通过 || echo 失败)"
say "pnpm dev 启动: $([ "$DEV_OK" = 1 ] && echo 成功 || echo 失败)"
say "诚实边界：核心 flow（Google 登录→CRUD→导出）当前不可走通——"
say "  ① page.tsx 仍是默认落地页，DataTable/ExportButton 未被任何页面 import（缺页面装配接缝）"
say "  ② Google OAuth 是占位凭据，点登录会失败"
say "  本验收只证明'产物能编译+能启动服务'，不证明'功能可用'。"

[ "$BUILD_OK" = 1 ] && [ "$DEV_OK" = 1 ] && exit 0 || exit 1
