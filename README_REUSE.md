# 🎁 复用包使用说明

这是一个即插即用的 Web 轨迹生成系统，已配置好支持 DashScope (Kimi API) 和其他兼容 OpenAI 的 API 服务。

## 📦 包含内容

```
Explorer/
├── 📘 QUICKSTART.md              # ← 从这里开始！
├── 📖 DASHSCOPE_SETUP.md        # 详细文档
├── 📁 FILE_STRUCTURE.md         # 文件结构说明
│
├── ⚙️  config.template.sh        # 配置模板
├── 🚀 quick_start.sh            # 一键启动脚本
│
├── 🔧 traj_gen/
│   ├── llm_utils.py             # 已修改：支持多 API
│   ├── browser_env.py           # 已修改：headless 模式
│   └── ...
│
└── 📂 trajectories/             # 输出目录（自动生成）
```

## 🚀 30 秒快速启动

### 前提条件

确保你已经：
- ✅ 安装了 Conda/Miniconda
- ✅ 有一个 DashScope API Key (或 OpenAI API Key)

### 启动步骤

```bash
# 1. 进入项目目录
cd Explorer

# 2. 创建并激活环境（首次使用）
conda create --name explorer python=3.12.5
conda activate explorer
pip install -r traj_gen/requirements.txt

# 3. 复制并编辑配置
cp config.template.sh config.sh
nano config.sh  # 填入你的 API key

# 4. 运行！
./quick_start.sh
```

就这么简单！🎉

## 📝 配置说明

编辑 `config.sh`，只需修改 3 个关键参数：

```bash
# 1. API Key
export DASHSCOPE_API_KEY='sk-你的密钥'

# 2. API 地址
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'

# 3. 模型名称
export MODEL_NAME='kimi-k2-5'
```

其他参数使用默认值即可。

## 📊 输出结果

运行完成后，查看 `trajectories/` 目录：

```
trajectories/
├── traj_1_20260604_123456/
│   ├── task_trajectory_data.json    # ← 主要数据文件
│   ├── screenshot_*.png              # 每步截图
│   ├── html_*.html                   # HTML 快照
│   └── run.log                       # 运行日志
└── traj_2_20260604_123500/
    └── ...
```

## 🎯 支持的 API 提供商

### 1. DashScope (阿里云 - Kimi)

```bash
export DASHSCOPE_API_KEY='sk-xxxxx'
export API_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL_NAME='kimi-k2-5'
```

### 2. OpenAI

```bash
export OPENAI_API_KEY='sk-xxxxx'
export API_BASE_URL='https://api.openai.com/v1'
export MODEL_NAME='gpt-4o'
```

### 3. 其他兼容服务

任何支持 OpenAI Chat Completions API 格式的服务都可以使用：

```bash
export DASHSCOPE_API_KEY='your-api-key'
export API_BASE_URL='https://your-endpoint.com/v1'
export MODEL_NAME='your-model-name'
```

## 🔧 自定义配置

### 修改起始 URL

编辑 `config.sh` 中的 `URLS` 数组：

```bash
export URLS=(
    "https://www.amazon.com/"
    "https://www.wikipedia.org/"
    "https://www.github.com/"
    "https://www.reddit.com/"
    # 添加更多 URL...
)
```

### 调整生成参数

```bash
export MAX_STEPS=15              # 每条轨迹的最大步骤数
export VIEWPORT_WIDTH=1920       # 浏览器窗口宽度
export VIEWPORT_HEIGHT=1080      # 浏览器窗口高度
```

## 📚 文档索引

- **快速开始**: [QUICKSTART.md](QUICKSTART.md) - 3 步启动指南
- **详细配置**: [DASHSCOPE_SETUP.md](DASHSCOPE_SETUP.md) - 完整配置和故障排除
- **文件结构**: [FILE_STRUCTURE.md](FILE_STRUCTURE.md) - 代码结构和工作流程

## 🐛 遇到问题？

### 常见问题快速解决

1. **API 调用失败**
   ```bash
   # 测试 API 是否可用
   curl -X POST "$API_BASE_URL/chat/completions" \
     -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"'$MODEL_NAME'","messages":[{"role":"user","content":"test"}]}'
   ```

2. **Chrome 未找到**
   ```bash
   # Ubuntu 安装
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   sudo dpkg -i google-chrome-stable_current_amd64.deb
   ```

3. **Xvfb 错误**
   ```bash
   # 安装 Xvfb
   sudo apt-get install xvfb
   
   # 重启
   pkill Xvfb
   Xvfb :99 -screen 0 1920x1280x16 &
   ```

更多问题请查看 [DASHSCOPE_SETUP.md](DASHSCOPE_SETUP.md#常见问题) 的常见问题部分。

## 💡 使用技巧

### 1. 测试 API 连接

在大规模生成前，先测试单条轨迹：

```bash
source config.sh
python -m traj_gen.main \
    --model-dir ./test_output \
    --init-url "https://www.wikipedia.org/" \
    --max-steps 3
```

### 2. 批量处理

把多个 URL 放到文本文件：

```bash
# urls.txt
https://www.amazon.com/
https://www.wikipedia.org/
https://www.github.com/
```

然后用脚本读取：

```bash
while IFS= read -r url; do
    python -m traj_gen.main \
        --model-dir "./trajectories/$(date +%s)" \
        --init-url "$url" \
        --max-steps 10
done < urls.txt
```

### 3. 后台运行

对于长时间任务，使用 nohup：

```bash
nohup ./quick_start.sh > output.log 2>&1 &
```

查看进度：

```bash
tail -f output.log
```

## 🎓 代码修改说明

如果你想了解我们做了哪些修改来支持 DashScope API：

### 修改 1: `traj_gen/llm_utils.py`

**改动**: 支持自定义 API endpoint 和多种 API key

```python
# 修改前
api_key = os.getenv("OPENAI_API_KEY")
url = "https://api.openai.com/v1/chat/completions"

# 修改后
api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
url = f"{base_url}/chat/completions"
model = os.getenv("MODEL_NAME", args.deployment)
```

### 修改 2: `traj_gen/browser_env.py`

**改动**: 
- 从 `headless=False` 改为 `headless=True`
- 添加系统 Chrome 支持

```python
# 修改前
self.browser = self.tls.playwright.chromium.launch(headless=False)

# 修改后
self.browser = self.tls.playwright.chromium.launch(
    headless=True,
    executable_path='/usr/bin/google-chrome'
)
```

所有修改都保持向后兼容，不影响原有的 OpenAI API 使用方式。

## 📊 性能预期

- **单条轨迹时间**: 5-15 分钟（取决于步骤数和 API 速度）
- **并发建议**: 建议串行执行，避免浏览器资源竞争
- **存储需求**: 每条轨迹约 5-20 MB（包含截图和 HTML）

## 🔐 安全提醒

1. **不要提交 API Key**: `config.sh` 已加入 `.gitignore`
2. **保护输出数据**: 截图可能包含敏感信息
3. **网络安全**: 确保在安全的网络环境下运行

## 🤝 贡献

如果你改进了这套系统，欢迎分享！

## 📞 获取帮助

- **详细文档**: [DASHSCOPE_SETUP.md](DASHSCOPE_SETUP.md)
- **原项目**: https://github.com/OSU-NLP-Group/Explorer
- **论文**: https://aclanthology.org/2025.findings-acl.326.pdf

---

**祝你使用愉快！** 🎉

如有问题，请查看详细文档或提出 Issue。
