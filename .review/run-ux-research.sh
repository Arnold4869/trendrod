#!/bin/bash
# 6.13 早上跑的研究命令
# 用法: bash .review/run-ux-research.sh
set -e
cd /volume1/docker/trendrod

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

claude -p "$PROMPT" --permission-mode bypassPermissions
