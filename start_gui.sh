#!/bin/zsh
# 启动 MinerU 图形界面
# 用法: 双击本文件，或在终端执行 ./start_gui.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 初始化 conda
if [ -f /opt/anaconda3/etc/profile.d/conda.sh ]; then
  source /opt/anaconda3/etc/profile.d/conda.sh
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
else
  echo "未找到 conda，请确认 Anaconda/Miniconda 已安装。"
  exit 1
fi

conda activate mineru

# 国内默认走 ModelScope 下载模型
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-modelscope}"
# 提高稳定性（Mac 本地单任务）
export MINERU_API_MAX_CONCURRENT_REQUESTS="${MINERU_API_MAX_CONCURRENT_REQUESTS:-1}"
export MINERU_TASK_RESULT_TIMEOUT_SECONDS="${MINERU_TASK_RESULT_TIMEOUT_SECONDS:-7200}"
export MINERU_LOCAL_API_STARTUP_TIMEOUT_SECONDS="${MINERU_LOCAL_API_STARTUP_TIMEOUT_SECONDS:-600}"
export PYTHONUNBUFFERED=1

mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/output"

echo "启动 MinerU GUI..."
echo "Python: $(which python)"
echo "MinerU: $(which mineru)"
echo "模型源: $MINERU_MODEL_SOURCE"
python "$SCRIPT_DIR/mineru_gui.py"
