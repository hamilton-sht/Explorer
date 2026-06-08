# Explorer 轨迹生成系统 - DashScope/Kimi API 复用指南

本指南详细说明如何使用 DashScope API (阿里云) 或其他兼容 OpenAI API 的服务来生成 Web 轨迹数据。

## 📋 目录

- [系统概述](#系统概述)
- [环境准备](#环境准备)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [使用方法](#使用方法)
- [输出说明](#输出说明)
- [常见问题](#常见问题)

---

## 🎯 系统概述

Explorer 是一个用于生成 Web 交互轨迹的系统，原本设计用于 OpenAI GPT-4V。本修改版支持：

- ✅ **DashScope API** (阿里云 - Kimi 等模型)
- ✅ **其他 OpenAI 兼容 API** (只需提供 base_url)
- ✅ **无头浏览器模式** (headless Chrome)
- ✅ **自动截图和 HTML 快照**
- ✅ **Set-of-Mark (SOM) 标注**

### 已修改的核心文件

1. **`traj_gen/llm_utils.py`** - 支持自定义 API endpoint
2. **`traj_gen/browser_env.py`** - 使用系统 Chrome，支持 headless 模式
3. **`run_dashscope.sh`** - 一键运行脚本

---

## 🔧 环境准备

### 1. 系统要求

- **操作系统**: Linux (Ubuntu 推荐)
- **Python**: 3.12.5
- **Chrome**: 已安装 Google Chrome 浏览器
- **显示**: Xvfb (虚拟显示服务器)

### 2. 安装依赖

```bash
# 克隆项目
git clone https://github.com/OSU-NLP-Group/Explorer.git
cd Explorer

# 创建 conda 环境
conda create --name explorer python=3.12.5
conda activate explorer

# 安装依赖
pip install -r traj_gen/requirements.txt

# 安装 Playwright 浏览器 (可选，我们使用系统 Chrome)
playwright install chromium

# 安装 Google Chrome (Ubuntu)
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f

# 安装 Xvfb
sudo apt-get install xvfb
```

---

## 🚀 快速开始

### 方法 1: 使用一键脚本 (推荐)

```bash
# 1. 编辑配置
nano run_dashscope.sh

# 2. 修改以下参数:
export DASHSCOPE_API_KEY='your-api-key-here'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'

# 3. 运行
chmod +x run_dashscope.sh
./run_dashscope.sh
```

### 方法 2: 手动运行

```bash
# 1. 设置环境变量
export DASHSCOPE_API_KEY='sk-xxxxx'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
export DISPLAY=:99

# 2. 启动虚拟显示服务器
Xvfb :99 -screen 0 1920x1280x16 &
sleep 3

# 3. 运行轨迹生成
python -m traj_gen.main \
    --model-dir ./trajectories/my_traj_1 \
    --init-url "https://www.amazon.com/" \
    --max-steps 10 \
    --deployment gpt-4o \
    --viewport-width 1280 \
    --viewport-height 720
```

---

## ⚙️ 配置说明

### 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DASHSCOPE_API_KEY` | API 密钥 | `sk-xxxxx` |
| `API_BASE_URL` | API 基础 URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `MODEL_NAME` | 模型名称 | `kimi-k2-5` |
| `DISPLAY` | X11 显示编号 | `:99` |

### 支持的 API 提供商

#### 1. DashScope (阿里云)

```bash
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
export DASHSCOPE_API_KEY='sk-xxxxx'
```

#### 2. OpenAI

```bash
export API_BASE_URL='https://api.openai.com/v1'
export MODEL_NAME='gpt-4o'
export OPENAI_API_KEY='sk-xxxxx'
```

#### 3. 其他兼容服务

只要支持 OpenAI Chat Completions API 格式即可：

```bash
export API_BASE_URL='https://your-api-endpoint.com/v1'
export MODEL_NAME='your-model-name'
export DASHSCOPE_API_KEY='your-api-key'  # 或 OPENAI_API_KEY
```

### 命令行参数

```bash
python -m traj_gen.main \
    --model-dir OUTPUT_DIR \          # 输出目录
    --init-url INITIAL_URL \          # 起始网页
    --max-steps MAX_STEPS \           # 最大步骤数 (默认 10)
    --deployment MODEL_NAME \         # 模型名称 (被 MODEL_NAME 环境变量覆盖)
    --viewport-width WIDTH \          # 浏览器宽度 (默认 1280)
    --viewport-height HEIGHT          # 浏览器高度 (默认 720)
```

---

## 📊 使用方法

### 生成单条轨迹

```bash
export DASHSCOPE_API_KEY='sk-xxxxx'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
export DISPLAY=:99

python -m traj_gen.main \
    --model-dir ./trajectories/amazon_search \
    --init-url "https://www.amazon.com/" \
    --max-steps 10
```

### 批量生成多条轨迹

使用提供的脚本 `run_dashscope.sh` 可以自动生成多条轨迹：

```bash
#!/bin/bash

# 配置
export DASHSCOPE_API_KEY='sk-xxxxx'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
export DISPLAY=:99

# 启动 Xvfb
Xvfb :99 -screen 0 1920x1280x16 &
sleep 3

# 定义多个起始 URL
URLS=(
    "https://www.amazon.com/"
    "https://www.wikipedia.org/"
    "https://www.reddit.com/"
    "https://www.github.com/"
)

# 循环生成
for i in "${!URLS[@]}"; do
    python -m traj_gen.main \
        --model-dir "./trajectories/traj_$((i+1))" \
        --init-url "${URLS[$i]}" \
        --max-steps 10
    sleep 5
done
```

---

## 📦 输出说明

每条轨迹会在指定的 `--model-dir` 目录下生成以下文件：

### 文件结构

```
trajectories/traj_1/
├── task_trajectory_data.json    # 主轨迹数据文件
├── html_0.html                   # 每步的 HTML 快照
├── html_1.html
├── ...
├── screenshot_0.png              # 每步的截图
├── screenshot_1.png
├── ...
├── screenshot_som_0.png          # Set-of-Mark 标注截图
├── screenshot_som_1.png
├── ...
├── screenshot_final.png          # 最终页面截图
├── step_simulator_flow.log       # 执行日志
└── run.log                       # 完整运行日志
```

### 主要数据文件格式

**`task_trajectory_data.json`**

```json
{
  "task_description": "搜索无线蓝牙耳机...",
  "init_url": "https://www.amazon.com/",
  "trajectory": [
    {
      "step": 0,
      "observation": "当前页面是 Amazon 首页...",
      "action": "在搜索框中输入 'wireless bluetooth headphones'",
      "action_type": "type",
      "element_id": 123,
      "value": "wireless bluetooth headphones",
      "screenshot": "screenshot_0.png",
      "html": "html_0.html"
    },
    ...
  ],
  "success": true,
  "total_steps": 8
}
```

---

## 🔍 常见问题

### 1. Xvfb 相关

**问题**: `Cannot connect to X server`

```bash
# 检查 Xvfb 是否运行
ps aux | grep Xvfb

# 重启 Xvfb
pkill Xvfb
Xvfb :99 -screen 0 1920x1280x16 &
export DISPLAY=:99
```

### 2. Chrome 驱动问题

**问题**: `Chrome binary not found`

```bash
# 验证 Chrome 安装
which google-chrome
google-chrome --version

# 修改 browser_env.py 中的路径
executable_path='/usr/bin/google-chrome'
```

### 3. API 调用失败

**问题**: `API key invalid` 或 `Connection error`

```bash
# 检查环境变量
echo $DASHSCOPE_API_KEY
echo $API_BASE_URL
echo $MODEL_NAME

# 测试 API 连接
curl -X POST "$API_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'$MODEL_NAME'",
    "messages": [{"role": "user", "content": "test"}]
  }'
```

### 4. 内存不足

**问题**: 浏览器崩溃或内存错误

```bash
# 减少并发数或降低分辨率
--viewport-width 1024 \
--viewport-height 768
```

### 5. 轨迹生成卡住

**问题**: 长时间无响应

- 检查网站是否可访问
- 查看 `run.log` 日志
- 减少 `--max-steps` 参数
- 检查 API 调用是否正常

---

## 📝 自定义任务

### 修改任务提示词

编辑 `traj_gen/task_proposal_agent.py` 中的任务生成逻辑：

```python
# 自定义任务类型
TASK_TEMPLATES = [
    "Search for {product} under ${price}",
    "Find information about {topic}",
    "Compare prices for {item}",
    # 添加你的任务模板
]
```

### 指定特定任务

不使用自动任务生成，而是手动指定：

```bash
# 修改 main.py，添加 --task 参数
python -m traj_gen.main \
    --model-dir ./trajectories/custom_task \
    --init-url "https://www.amazon.com/" \
    --task "Search for wireless headphones under $30" \
    --max-steps 10
```

---

## 🎓 进阶使用

### 1. 集成到数据流水线

```python
import subprocess
import json

def generate_trajectory(url, output_dir, max_steps=10):
    """生成单条轨迹"""
    cmd = [
        "python", "-m", "traj_gen.main",
        "--model-dir", output_dir,
        "--init-url", url,
        "--max-steps", str(max_steps)
    ]
    subprocess.run(cmd, env={
        "DASHSCOPE_API_KEY": "sk-xxxxx",
        "API_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "MODEL_NAME": "kimi-k2-5",
        "DISPLAY": ":99"
    })
    
    # 读取结果
    with open(f"{output_dir}/task_trajectory_data.json") as f:
        return json.load(f)
```

### 2. 数据清洗和过滤

```python
import json
import os

def filter_valid_trajectories(traj_dir):
    """筛选有效轨迹"""
    valid_trajs = []
    for traj_name in os.listdir(traj_dir):
        traj_path = os.path.join(traj_dir, traj_name, "task_trajectory_data.json")
        if os.path.exists(traj_path):
            with open(traj_path) as f:
                data = json.load(f)
                if data.get("success") and len(data["trajectory"]) >= 5:
                    valid_trajs.append(data)
    return valid_trajs
```

---

## 📞 技术支持

### 相关资源

- **原始项目**: https://github.com/OSU-NLP-Group/Explorer
- **论文**: https://aclanthology.org/2025.findings-acl.326.pdf
- **DashScope 文档**: https://help.aliyun.com/zh/dashscope/

### 贡献

欢迎提交 Issue 和 PR 来改进本指南。

---

## 📄 许可证

本项目遵循 MIT 许可证。详见 [LICENSE](LICENSE) 文件。
