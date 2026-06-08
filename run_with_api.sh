#!/bin/bash

# 激活 conda 环境
source /home/ubuntu/miniconda3/etc/profile.d/conda.sh
conda activate explorer

# 设置 API Key 和显示环境
export MOONSHOT_API_KEY='sk-5988aed89e204b3385f7b4057f23e658'
export DISPLAY=:99

# 启动 Xvfb（如果还没运行）
if ! pgrep -x "Xvfb" > /dev/null; then
    echo "启动 Xvfb..."
    Xvfb :99 -screen 0 1920x1280x16 > /dev/null 2>&1 &
    sleep 3
fi

# 切换到项目目录
cd /home/ubuntu/Explorer

# 运行脚本
python quick_run.py
