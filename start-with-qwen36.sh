#!/bin/bash
# Smart Agent 启动 wrapper —— 用 env vars override .env，指向 qwen-openai-proxy
# 用法：./start-with-qwen36.sh [args...]

set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查 proxy 喺唔喺度
if ! curl -s --max-time 3 http://127.0.0.1:11435/health > /dev/null 2>&1; then
    echo "❌ qwen-openai-proxy 未运行（http://127.0.0.1:11435）"
    echo "请先启动："
    echo "   cd ~/workspace/qwen-openai-proxy && ./start.sh"
    exit 1
fi

# 用环境变量 override .env（dotenv 唔会覆盖已有 env vars）
export DEEPSEEK_API_KEY=dummy
export DEEPSEEK_API_URL=http://127.0.0.1:11435/v1
export DEEPSEEK_MODEL=qwen3.6

export LLM_API_KEY=dummy
export LLM_API_URL=http://127.0.0.1:11435/v1
export LLM_MODEL=qwen3.6

export QWEN_API_KEY=dummy
export QWEN_API_URL=http://127.0.0.1:11435/v1
export QWEN_MODEL=qwen3.6

echo "=========================================="
echo "🚀 Smart Agent (Qwen3.6 via Proxy)"
echo "=========================================="
echo "  LLM 后端: http://127.0.0.1:11435/v1 (qwen-openai-proxy)"
echo "  模型:      qwen3.6 → qwen3.6:35b-mlx (74 t/s)"
echo "  Vision:    qwen3.6 → 自动 routing → qwen3.6:35b (GGUF)"
echo "=========================================="
echo ""

# 如果有 .venv 就 activate，唔系用 system python
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 跑 Smart Agent（默认 main.py，或接受参数）
if [ $# -eq 0 ]; then
    python main.py
else
    python "$@"
fi
