#!/bin/bash

# 激活 conda 环境
source /home/ubuntu/miniconda3/etc/profile.d/conda.sh
conda activate explorer

# 设置 DashScope API 配置（根据用户提供的信息）
export DASHSCOPE_API_KEY='sk-5988aed89e204b3385f7b4057f23e658'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
export DISPLAY=:99

# 启动 Xvfb（如果还没运行）
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "启动 Xvfb..."
    Xvfb :99 -screen 0 1920x1280x16 > /dev/null 2>&1 &
    sleep 3
fi

# 创建输出目录
OUTPUT_DIR="/home/ubuntu/Explorer/trajectories"
mkdir -p $OUTPUT_DIR

# 定义两个不同的初始 URL
URLS=(
    "https://www.amazon.com/"
    "https://www.wikipedia.org/"
)

echo "=========================================="
echo "开始生成轨迹 - 使用 API"
echo "API Base URL: $API_BASE_URL"
echo "Model: $MODEL_NAME"
echo "=========================================="

# 切换到项目目录
cd /home/ubuntu/Explorer

# 运行2条轨迹
for i in {0..1}; do
    echo ""
    echo "=========================================="
    echo "生成第 $((i+1)) 条轨迹..."
    echo "初始 URL: ${URLS[$i]}"
    echo "=========================================="

    TRAJ_DIR="${OUTPUT_DIR}/traj_dashscope_$((i+1))_$(date +%Y%m%d_%H%M%S)"
    mkdir -p $TRAJ_DIR

    python -m traj_gen.main \
        --model-dir $TRAJ_DIR \
        --init-url "${URLS[$i]}" \
        --max-steps 10 \
        --deployment gpt-4o \
        --viewport-width 1280 \
        --viewport-height 720 \
        2>&1 | tee "${TRAJ_DIR}/run.log"

    echo ""
    echo "轨迹 $((i+1)) 完成"
    echo "保存位置: $TRAJ_DIR"
    echo ""

    # 检查是否生成了轨迹文件
    if [ -f "${TRAJ_DIR}/trajectory.json" ]; then
        echo "✓ 轨迹文件已生成"
    else
        echo "⚠ 警告：未找到轨迹文件"
    fi

    sleep 5
done

echo ""
echo "=========================================="
echo "✅ 全部完成！"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="
