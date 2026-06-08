# 🚀 快速复用指南

这是一个三步启动的轨迹生成系统，支持 DashScope (Kimi) 和其他兼容 OpenAI API 的服务。

## ⚡ 三步启动

### 1️⃣ 复制配置模板

```bash
cd /path/to/Explorer
cp config.template.sh config.sh
```

### 2️⃣ 编辑配置文件

```bash
nano config.sh
```

**修改以下内容：**

```bash
# 填入你的 API Key
export DASHSCOPE_API_KEY='sk-你的密钥'

# 确认 API 地址和模型
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'

# (可选) 修改起始 URL
export URLS=(
    "https://www.amazon.com/"
    "https://www.wikipedia.org/"
    "https://www.github.com/"
)
```

### 3️⃣ 运行

```bash
./quick_start.sh
```

就这么简单！脚本会自动：
- ✅ 检查环境配置
- ✅ 启动虚拟显示服务器
- ✅ 生成所有轨迹
- ✅ 保存结果到 `trajectories/` 目录

## 📂 输出结构

```
trajectories/
├── traj_1_20260604_123456/
│   ├── task_trajectory_data.json    # 主数据文件
│   ├── screenshot_*.png              # 截图
│   ├── html_*.html                   # HTML 快照
│   └── run.log                       # 运行日志
├── traj_2_20260604_123500/
│   └── ...
└── ...
```

## 🔧 环境要求

首次使用前需要安装环境：

```bash
# 1. 创建 conda 环境
conda create --name explorer python=3.12.5
conda activate explorer

# 2. 安装依赖
cd Explorer
pip install -r traj_gen/requirements.txt

# 3. 安装系统依赖 (Ubuntu)
sudo apt-get install xvfb google-chrome-stable
```

## 📖 详细文档

查看 **[DASHSCOPE_SETUP.md](DASHSCOPE_SETUP.md)** 获取：
- 完整配置说明
- API 提供商支持
- 常见问题解决
- 进阶使用方法

## 🎯 使用不同的 API

### DashScope (阿里云 - Kimi)
```bash
export DASHSCOPE_API_KEY='sk-xxxxx'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
```

### OpenAI
```bash
export OPENAI_API_KEY='sk-xxxxx'
export API_BASE_URL='https://api.openai.com/v1'
export MODEL_NAME='gpt-4o'
```

### 其他兼容服务
```bash
export DASHSCOPE_API_KEY='your-key'
export API_BASE_URL='https://your-endpoint.com/v1'
export MODEL_NAME='your-model'
```

## ⚙️ 高级选项

### 单独运行一条轨迹

```bash
source config.sh  # 加载配置

python -m traj_gen.main \
    --model-dir ./trajectories/my_custom_traj \
    --init-url "https://example.com/" \
    --max-steps 15 \
    --viewport-width 1920 \
    --viewport-height 1080
```

### 自定义任务数量

编辑 `config.sh`，修改 `URLS` 数组：

```bash
export URLS=(
    "https://site1.com/"
    "https://site2.com/"
    "https://site3.com/"
    # 添加更多...
)
```

### 调整生成参数

在 `config.sh` 中修改：

```bash
export MAX_STEPS=15              # 增加步骤数
export VIEWPORT_WIDTH=1920       # 更高分辨率
export VIEWPORT_HEIGHT=1080
```

## 🐛 常见问题

### 1. API 调用失败

```bash
# 测试 API 连接
curl -X POST "$API_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"'$MODEL_NAME'","messages":[{"role":"user","content":"test"}]}'
```

### 2. Xvfb 错误

```bash
# 重启 Xvfb
pkill Xvfb
Xvfb :99 -screen 0 1920x1280x16 &
export DISPLAY=:99
```

### 3. Chrome 未找到

```bash
# Ubuntu 安装 Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f
```

## 📞 获取帮助

- 详细文档：[DASHSCOPE_SETUP.md](DASHSCOPE_SETUP.md)
- 原项目：https://github.com/OSU-NLP-Group/Explorer
- 论文：https://aclanthology.org/2025.findings-acl.326.pdf

## 🎓 代码改动说明

为了支持 DashScope API，我们修改了：

1. **`traj_gen/llm_utils.py`**：支持自定义 API endpoint
2. **`traj_gen/browser_env.py`**：使用系统 Chrome，支持 headless 模式
3. 新增脚本：
   - `config.template.sh`：配置模板
   - `quick_start.sh`：一键启动脚本
   - `DASHSCOPE_SETUP.md`：详细文档

所有改动都向后兼容，仍然支持原始的 OpenAI API。
