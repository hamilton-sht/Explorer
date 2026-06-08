#!/bin/bash
# Explorer 轨迹生成配置模板
# 复制此文件为 config.sh 并填入你的配置

# ========================================
# API 配置
# ========================================

# 选项 1: DashScope (阿里云 - Kimi)
export DASHSCOPE_API_KEY='your-dashscope-api-key-here'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'

# 选项 2: OpenAI
# export OPENAI_API_KEY='your-openai-api-key-here'
# export API_BASE_URL='https://api.openai.com/v1'
# export MODEL_NAME='gpt-4o'

# 选项 3: Claude 兼容 API
# export API_KEY='your-api-key-here'
# export API_BASE_URL='https://api-int.memtensor.cn/v1'
# export MODEL_NAME='claude-opus-4-8'

# 选项 4: 其他兼容 OpenAI API 的服务
# export DASHSCOPE_API_KEY='your-api-key-here'
# export API_BASE_URL='https://your-api-endpoint.com/v1'
# export MODEL_NAME='your-model-name'

# ========================================
# 显示配置 (通常不需要修改)
# ========================================
export DISPLAY=:99

# ========================================
# 轨迹生成参数
# ========================================
export MAX_STEPS=10              # 每条轨迹的最大步骤数
export VIEWPORT_WIDTH=1280       # 浏览器窗口宽度
export VIEWPORT_HEIGHT=720       # 浏览器窗口高度
export OUTPUT_DIR="./trajectories"  # 输出目录

# ========================================
# 起始 URL 列表
# ========================================
# 可以添加更多 URL，脚本会为每个 URL 生成一条轨迹
export URLS=(
    "https://www.amazon.com/"
    "https://www.wikipedia.org/"
    "https://www.reddit.com/"
    "https://www.github.com/"
)
