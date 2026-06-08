#!/bin/bash

# 激活 conda 环境
source /home/ubuntu/miniconda3/etc/profile.d/conda.sh
conda activate explorer

# 设置显示环境（用于 headless 浏览器）
export DISPLAY=:99

# 请在这里设置你的 Moonshot API Key
# export MOONSHOT_API_KEY="your-moonshot-api-key-here"

# 如果没有设置 MOONSHOT_API_KEY，脚本会报错
if [ -z "$MOONSHOT_API_KEY" ]; then
    echo "错误：请先设置 MOONSHOT_API_KEY 环境变量"
    echo "使用方法："
    echo "  export MOONSHOT_API_KEY='your-api-key'"
    echo "  bash run_2_trajectories.sh"
    exit 1
fi

# 启动虚拟显示服务器（如果还没运行）
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "启动 Xvfb 虚拟显示服务器..."
    Xvfb :99 -screen 0 1920x1280x16 &
    sleep 2
fi

# 创建输出目录
OUTPUT_DIR="/home/ubuntu/Explorer/trajectories"
mkdir -p $OUTPUT_DIR

# 定义两个不同的初始 URL 来生成不同的轨迹
URLS=(
    "https://www.amazon.com/"
    "https://www.wikipedia.org/"
)

# 运行2条轨迹
for i in {0..1}; do
    echo "=========================================="
    echo "生成第 $((i+1)) 条轨迹..."
    echo "初始 URL: ${URLS[$i]}"
    echo "=========================================="

    TRAJ_DIR="${OUTPUT_DIR}/traj_$((i+1))_$(date +%Y%m%d_%H%M%S)"
    mkdir -p $TRAJ_DIR

    python -m traj_gen.main \
        --model-dir $TRAJ_DIR \
        --init-url "${URLS[$i]}" \
        --max-steps 10 \
        --deployment gpt-4o \
        --viewport-width 1280 \
        --viewport-height 720 \
        2>&1 | tee "${TRAJ_DIR}/run.log"

    echo "轨迹 $((i+1)) 完成，保存在: $TRAJ_DIR"
    echo ""
    sleep 5
done

echo "=========================================="
echo "全部完成！生成了 2 条轨迹"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="
