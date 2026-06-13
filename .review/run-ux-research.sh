#!/bin/bash
# 6.13 早上跑的研究命令
# 用法: bash .review/run-ux-research.sh
set -eo pipefail
cd /volume1/docker/trendrod

# Hermes background=true 启动的 subshell 可能 env 被裁剪（CLAUDE_CODE_SUBPROCESS_ENV_SCRUB 类似机制），
# 导致 cc 找不到 ~/.claude/ OAuth token，报 "Not logged in"。显式 export 兜底。
export HOME="${HOME:-/volume1/docker/hermes/data/home}"
export USER="${USER:-Bin}"
export PATH="$PATH:/home/Bin/.npm-global/bin"

PROMPT=$(cat <<'EOF'
阅读 .review/UX-RESEARCH-2026-06-12.md（这是研究任务规格），
也阅读 .review/issues.md（已有 50 个 issue）和 static/index.html（1932 行），
然后输出 UX 提升方案文档到 .review/TRENDROD-UX-PROPOSAL-2026-06-13.md

关键要求：
- 不要直接改代码
- 不要碰后端 main.py
- 重点在 IA + 视觉 + 交互 + 性能感知
- 方案要分 Phase、标风险、引用现有 issue
- 输出完成后给我一段 200 字以内的概要

参考 skill：creative/popular-web-designs（54 套设计系统作灵感），但要配合红涨绿跌（中国惯例）
EOF
)

/home/Bin/.npm-global/bin/claude -p "$PROMPT" \
  --permission-mode bypassPermissions \
  --max-turns 25 \
  2>&1 | tee /tmp/ux-research.log
