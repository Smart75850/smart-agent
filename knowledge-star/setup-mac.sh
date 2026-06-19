#!/bin/bash
# ============================================================
# Mac Claude Code 一键同步脚本
# 将 Windows Claude Code 嘅全部知识同步到 Mac
# 用法: bash setup-mac.sh
# ============================================================
set -e

echo "========================================"
echo "  Mac Claude Code 知识同步"
echo "========================================"
echo ""

# 检测目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
WORKSPACE_DIR="$HOME/workspace/smart-agent"

# 1. Clone smart-agent（如果未有）
if [ ! -d "$WORKSPACE_DIR" ]; then
    echo "[1/4] Clone smart-agent 仓库..."
    mkdir -p "$HOME/workspace"
    git clone https://github.com/Smart75850/smart-agent.git "$WORKSPACE_DIR"
else
    echo "[1/4] smart-agent 仓库已存在，git pull..."
    cd "$WORKSPACE_DIR" && git pull
fi

# 2. 复制 CLAUDE.md
echo "[2/4] 同步 CLAUDE.md..."
mkdir -p "$CLAUDE_DIR"
cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
echo "  -> $CLAUDE_DIR/CLAUDE.md"

# 3. 复制 skills（知识星图教学系统）
echo "[3/4] 同步 skills..."
rm -rf "$CLAUDE_DIR/skills/knowledge-tutor"
cp -r "$SCRIPT_DIR/skills/knowledge-tutor" "$CLAUDE_DIR/skills/knowledge-tutor"
echo "  -> $CLAUDE_DIR/skills/knowledge-tutor/"

# 4. 复制 memory（Claude 记忆）
echo "[4/4] 同步 memory..."
mkdir -p "$CLAUDE_DIR/projects/C--Users-guohu/memory"
cp "$SCRIPT_DIR/memory/"*.md "$CLAUDE_DIR/projects/C--Users-guohu/memory/" 2>/dev/null || true
echo "  -> $CLAUDE_DIR/projects/.../memory/"

echo ""
echo "========================================"
echo "  同步完成！"
echo "========================================"
echo ""
echo "下次启动 Claude Code (Mac) 时，会话会自动加载："
echo "  - 知识星图数据 (knowledge-star/galaxy-data.json)"
echo "  - 完整 CLAUDE.md 配置"
echo "  - CDP 反爬架构决策"
echo "  - 全部对话记忆"
echo ""
echo "日常更新："
echo "  cd ~/workspace/smart-agent && git pull"
echo "  bash ~/workspace/smart-agent/knowledge-star/setup-mac.sh"
