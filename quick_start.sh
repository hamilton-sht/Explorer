#!/bin/bash
# Explorer 快速启动脚本 - 轨迹生成
# 使用方法: ./quick_start.sh [配置文件]

set -e  # 遇到错误立即退出

# ========================================
# 颜色输出
# ========================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# ========================================
# 加载配置
# ========================================
CONFIG_FILE="${1:-config.sh}"

if [ ! -f "$CONFIG_FILE" ]; then
    print_error "配置文件不存在: $CONFIG_FILE"
    print_info "请先复制配置模板："
    echo "  cp config.template.sh config.sh"
    echo "  nano config.sh  # 编辑配置"
    exit 1
fi

print_info "加载配置文件: $CONFIG_FILE"
source "$CONFIG_FILE"

# ========================================
# 检查必需的环境变量
# ========================================
print_info "检查配置..."

if [ -z "$DASHSCOPE_API_KEY" ] && [ -z "$OPENAI_API_KEY" ] && [ -z "$API_KEY" ]; then
    print_error "未设置 API Key"
    print_info "请在配置文件中设置 DASHSCOPE_API_KEY、OPENAI_API_KEY 或 API_KEY"
    exit 1
fi

if [ -z "$API_BASE_URL" ]; then
    print_error "未设置 API_BASE_URL"
    exit 1
fi

if [ -z "$MODEL_NAME" ]; then
    print_error "未设置 MODEL_NAME"
    exit 1
fi

print_success "配置检查通过"
echo "  API Base URL: $API_BASE_URL"
echo "  Model: $MODEL_NAME"
echo "  Max Steps: ${MAX_STEPS:-10}"
echo "  Viewport: ${VIEWPORT_WIDTH:-1280}x${VIEWPORT_HEIGHT:-720}"

# ========================================
# 检查 Conda 环境
# ========================================
print_info "检查 Conda 环境..."

if ! command -v conda &> /dev/null; then
    print_error "Conda 未安装"
    exit 1
fi

# 激活环境
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
fi

if conda env list | grep -q "^explorer "; then
    conda activate explorer
    print_success "Conda 环境 'explorer' 已激活"
else
    print_error "Conda 环境 'explorer' 不存在"
    print_info "请先创建环境："
    echo "  conda create --name explorer python=3.12.5"
    echo "  conda activate explorer"
    echo "  pip install -r traj_gen/requirements.txt"
    exit 1
fi

# ========================================
# 检查 Chrome 浏览器
# ========================================
print_info "检查 Chrome 浏览器..."

if command -v google-chrome &> /dev/null; then
    CHROME_VERSION=$(google-chrome --version)
    print_success "Chrome 已安装: $CHROME_VERSION"
elif command -v chromium-browser &> /dev/null; then
    CHROME_VERSION=$(chromium-browser --version)
    print_success "Chromium 已安装: $CHROME_VERSION"
else
    print_error "未找到 Chrome/Chromium 浏览器"
    print_info "Ubuntu 安装命令："
    echo "  wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
    echo "  sudo dpkg -i google-chrome-stable_current_amd64.deb"
    exit 1
fi

# ========================================
# 启动 Xvfb (虚拟显示服务器)
# ========================================
print_info "检查 Xvfb..."

if ! command -v Xvfb &> /dev/null; then
    print_error "Xvfb 未安装"
    print_info "Ubuntu 安装命令："
    echo "  sudo apt-get install xvfb"
    exit 1
fi

if pgrep -x "Xvfb" > /dev/null; then
    print_success "Xvfb 已在运行"
else
    print_info "启动 Xvfb..."
    Xvfb :99 -screen 0 1920x1280x16 > /dev/null 2>&1 &
    sleep 3
    print_success "Xvfb 已启动"
fi

export DISPLAY=:99

# ========================================
# 创建输出目录
# ========================================
OUTPUT_DIR="${OUTPUT_DIR:-./trajectories}"
mkdir -p "$OUTPUT_DIR"
print_success "输出目录: $OUTPUT_DIR"

# ========================================
# 生成轨迹
# ========================================
echo ""
echo "========================================"
echo "  开始生成轨迹"
echo "========================================"
echo ""

# 默认 URL 列表
if [ ${#URLS[@]} -eq 0 ]; then
    URLS=(
        "https://www.amazon.com/"
        "https://www.wikipedia.org/"
    )
    print_warning "未指定 URL，使用默认列表"
fi

TOTAL_URLS=${#URLS[@]}
SUCCESSFUL=0
FAILED=0

for i in "${!URLS[@]}"; do
    URL="${URLS[$i]}"
    TRAJ_NUM=$((i+1))

    echo ""
    echo "========================================"
    echo "  轨迹 $TRAJ_NUM/$TOTAL_URLS"
    echo "========================================"
    echo "  URL: $URL"
    echo "========================================"
    echo ""

    TRAJ_DIR="${OUTPUT_DIR}/traj_${TRAJ_NUM}_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$TRAJ_DIR"

    print_info "输出目录: $TRAJ_DIR"
    print_info "开始生成..."

    # 运行轨迹生成
    if python -m traj_gen.main \
        --model-dir "$TRAJ_DIR" \
        --init-url "$URL" \
        --max-steps "${MAX_STEPS:-10}" \
        --deployment "${MODEL_NAME}" \
        --viewport-width "${VIEWPORT_WIDTH:-1280}" \
        --viewport-height "${VIEWPORT_HEIGHT:-720}" \
        2>&1 | tee "${TRAJ_DIR}/run.log"; then

        print_success "轨迹 $TRAJ_NUM 生成完成"
        SUCCESSFUL=$((SUCCESSFUL+1))

        # 检查输出文件
        if [ -f "${TRAJ_DIR}/task_trajectory_data.json" ]; then
            FILE_SIZE=$(du -h "${TRAJ_DIR}/task_trajectory_data.json" | cut -f1)
            print_success "轨迹文件已生成 (${FILE_SIZE})"

            # 统计步骤数
            STEP_COUNT=$(ls "${TRAJ_DIR}"/screenshot_*.png 2>/dev/null | wc -l)
            echo "  步骤数: $STEP_COUNT"
        else
            print_warning "未找到轨迹数据文件"
        fi
    else
        print_error "轨迹 $TRAJ_NUM 生成失败"
        FAILED=$((FAILED+1))
    fi

    # 短暂延迟
    if [ $TRAJ_NUM -lt $TOTAL_URLS ]; then
        sleep 3
    fi
done

# ========================================
# 统计结果
# ========================================
echo ""
echo "========================================"
echo "  生成完成"
echo "========================================"
echo "  总数: $TOTAL_URLS"
echo "  成功: $SUCCESSFUL"
echo "  失败: $FAILED"
echo "========================================"
echo "  输出目录: $OUTPUT_DIR"
echo "========================================"
echo ""

if [ $SUCCESSFUL -eq $TOTAL_URLS ]; then
    print_success "全部轨迹生成成功！"
    exit 0
elif [ $SUCCESSFUL -gt 0 ]; then
    print_warning "部分轨迹生成成功"
    exit 0
else
    print_error "所有轨迹生成失败"
    exit 1
fi
