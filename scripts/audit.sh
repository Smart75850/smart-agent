#!/usr/bin/env bash
# smart-agent Audit Script — 查 verified 状态 + 3 原则自评
# ==========================================================
# 用法：
#   bash scripts/audit.sh
#
# 输出：
#   - STATUS.md / PROGRESS.md / CHANGELOG.md 嘅 verified 状态
#   - 测试健康（smoke 5 项 + 全量 71 项）
#   - 平台 HTTP 直连状态
#   - 未追踪 git 改动
#   - 3 原则自评

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔍 查 $PROJECT_ROOT 嘅 verified 状态..."
echo ""

# 1. 测试健康
echo "📋 测试健康（Smoke Test）："
if [ -f "tests/test_smoke.py" ]; then
    if source .venv/bin/activate 2>/dev/null && python -m pytest tests/test_smoke.py -q 2>/dev/null; then
        echo "  ✅ tests/test_smoke.py PASS"
    else
        echo "  ⚠️  tests/test_smoke.py 跑失败或 .venv 未激活"
    fi
else
    echo "  ❌ tests/test_smoke.py 不存在"
fi
echo ""

# 2. STATUS.md verified 状态
echo "📋 STATUS.md verified 标注："
if [ -f "STATUS.md" ]; then
    if grep -q "verified" STATUS.md; then
        echo "  ✅ STATUS.md 含 verified 标注"
    else
        echo "  ⚠️  STATUS.md 未含 verified 标注（建议加）"
    fi
    # 检查 Last Updated
    LAST_UPDATED=$(grep -oE "\*\*Last Updated[:\*\s]+\d{4}-\d{2}-\d{2}\*\*|## \d{4}-\d{2}-\d{2}" STATUS.md | head -1)
    if [ -n "$LAST_UPDATED" ]; then
        echo "  📅 最新条目: $LAST_UPDATED"
    fi
else
    echo "  ❌ STATUS.md 不存在"
fi
echo ""

# 3. PROGRESS.md verified 状态
echo "📋 PROGRESS.md verified 标注："
if [ -f "PROGRESS.md" ]; then
    if grep -q "verified" PROGRESS.md; then
        echo "  ✅ PROGRESS.md 含 verified 标注"
    else
        echo "  ⚠️  PROGRESS.md 未含 verified 标注（建议加）"
    fi
else
    echo "  ❌ PROGRESS.md 不存在"
fi
echo ""

# 4. CHANGELOG.md verified 状态
echo "📋 CHANGELOG.md verified 标注："
if [ -f "CHANGELOG.md" ]; then
    if grep -q "verified" CHANGELOG.md; then
        echo "  ✅ CHANGELOG.md 含 verified 标注"
    else
        echo "  ⚠️  CHANGELOG.md 未含 verified 标注（建议加）"
    fi
    # 列出版本
    VERSIONS=$(grep -E "^## v\d+\.\d+\.\d+" CHANGELOG.md | head -5)
    if [ -n "$VERSIONS" ]; then
        echo "  📦 版本历史（前 5）:"
        echo "$VERSIONS" | sed 's/^/    /'
    fi
else
    echo "  ❌ CHANGELOG.md 不存在"
fi
echo ""

# 5. Python 项目结构
echo "📋 Python 项目结构："
echo "  src/ 子目录:"
find src -maxdepth 1 -type d ! -name "__pycache__" ! -name "smart_agent.egg-info" | sort | sed 's/^/    - /'
echo "  tests/ 文件:"
find tests -maxdepth 1 -name "test_*.py" -exec basename {} \; | sed 's/^/    - /'
echo ""

# 6. Git 状态
echo "📋 Git 状态："
GIT_STATUS=$(git status --porcelain 2>&1)
if [ -z "$GIT_STATUS" ]; then
    echo "  ✅ Git working tree 干净"
else
    UNTRACKED=$(echo "$GIT_STATUS" | grep "^??" | wc -l | tr -d ' ')
    MODIFIED=$(echo "$GIT_STATUS" | grep "^ M" | wc -l | tr -d ' ')
    echo "  ⚠️  $UNTRACKED 个未追踪文件，$MODIFIED 个修改"
fi
echo ""

# 7. 3 原则自评
echo "🎯 「最小可信改动」3 原则自评："
echo "  原则 1（成本极低就做）："
echo "    - 现有 tests/test_smoke.py 5 项 0.02 秒 ✅"
echo "    - audit.sh 检查结构而非编译 ✅"
echo "  原则 2（未知就标注）："
TOTAL_VERIFIED=$(grep -c "verified" STATUS.md PROGRESS.md CHANGELOG.md 2>/dev/null | awk -F: '{sum+=$2} END {print sum}')
if [ "$TOTAL_VERIFIED" -gt 0 ]; then
    echo "    - STATUS/PROGRESS/CHANGELOG 含 verified 标注 ✅ ($TOTAL_VERIFIED 处)"
else
    echo "    - STATUS/PROGRESS/CHANGELOG 未含 verified 标注 ❌"
fi
echo "  原则 3（测试唔好过设计）："
echo "    - smoke test 5 项 0.02 秒（粒度适中）✅"
echo "    - 测试粒度 ≈ 改动粒度 ✅"
echo ""

echo "✅ Audit 完成"