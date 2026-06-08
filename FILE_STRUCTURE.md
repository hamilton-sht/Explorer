# 📁 项目文件说明

## 核心文件结构

```
Explorer/
├── 📘 README.md                    # 原始项目文档
├── 🚀 QUICKSTART.md                # 快速开始指南 (新增)
├── 📖 DASHSCOPE_SETUP.md          # 详细配置文档 (新增)
│
├── ⚙️  config.template.sh          # 配置模板 (新增)
├── 🔧 quick_start.sh               # 一键启动脚本 (新增)
├── 🔧 run_dashscope.sh            # DashScope 运行脚本 (新增)
│
├── 📂 traj_gen/                    # 轨迹生成核心模块
│   ├── 🔴 llm_utils.py            # API 调用 (已修改)
│   ├── 🔴 browser_env.py          # 浏览器环境 (已修改)
│   ├── main.py                     # 主程序入口
│   ├── task_proposal_agent.py     # 任务生成
│   ├── task_refiner_agent.py      # 任务优化
│   ├── trajectory_verifier.py     # 轨迹验证
│   └── requirements.txt            # Python 依赖
│
├── 📂 trajectories/                # 输出目录 (自动创建)
│   ├── traj_1_YYYYMMDD_HHMMSS/
│   ├── traj_2_YYYYMMDD_HHMMSS/
│   └── ...
│
└── 📂 evals/                       # 评估模块
    ├── mind2web_live_eval/
    ├── mind2web_orig_eval/
    └── miniwob/
```

## 🔴 已修改文件详细说明

### 1. `traj_gen/llm_utils.py`

**修改内容：**
- 支持通过环境变量配置 API endpoint
- 兼容 DashScope、OpenAI 和其他 OpenAI 格式 API

**关键环境变量：**
```python
DASHSCOPE_API_KEY  # 或 OPENAI_API_KEY
API_BASE_URL       # API 基础地址
MODEL_NAME         # 模型名称
```

**修改前：**
```python
def call_gpt4v(args, messages, max_tokens=2048, temperature=0.01):
    api_key = os.getenv("OPENAI_API_KEY")
    url = "https://api.openai.com/v1/chat/completions"
    model = args.deployment
    ...
```

**修改后：**
```python
def call_gpt4v(args, messages, max_tokens=2048, temperature=0.01):
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
    url = f"{base_url}/chat/completions"
    model = os.getenv("MODEL_NAME", args.deployment)
    ...
```

### 2. `traj_gen/browser_env.py`

**修改内容：**
- 从 headless=False 改为 headless=True
- 添加对系统 Chrome 的支持 (executable_path)
- 处理 Playwright 浏览器不可用的情况

**修改前：**
```python
self.browser = self.tls.playwright.chromium.launch(
    headless=False, 
    slow_mo=0
)
```

**修改后：**
```python
try:
    self.browser = self.tls.playwright.chromium.launch(
        headless=True,
        slow_mo=0,
        executable_path='/usr/bin/google-chrome'
    )
except Exception as e:
    logging.error(f"Failed to launch: {e}")
    self.browser = self.tls.playwright.chromium.launch(
        headless=True, 
        slow_mo=0
    )
```

## 🆕 新增文件说明

### 1. `config.template.sh` - 配置模板

**用途：** 用户复制此文件为 `config.sh` 并填入自己的配置

**包含内容：**
- API 密钥配置
- API 端点配置
- 模型选择
- 轨迹生成参数
- 起始 URL 列表

### 2. `quick_start.sh` - 一键启动脚本

**功能：**
- ✅ 自动检查环境依赖
- ✅ 启动 Xvfb 虚拟显示
- ✅ 批量生成多条轨迹
- ✅ 彩色输出，进度提示
- ✅ 统计成功/失败数量

**使用方法：**
```bash
./quick_start.sh [配置文件]
# 默认使用 config.sh
```

### 3. `run_dashscope.sh` - DashScope 专用脚本

**特点：**
- 硬编码配置（适合快速测试）
- 包含完整的环境设置
- 适合不熟悉 shell 的用户

### 4. `QUICKSTART.md` - 快速开始文档

**内容：**
- 三步启动流程
- 最小化配置说明
- 常见问题快速解决

### 5. `DASHSCOPE_SETUP.md` - 详细配置文档

**内容：**
- 完整的环境准备指南
- 多种 API 提供商配置
- 输出文件格式说明
- 常见问题详细解答
- 进阶使用示例

## 📂 输出文件说明

每条轨迹会生成一个目录，包含：

```
traj_1_20260604_123456/
├── 📄 task_trajectory_data.json    # 主数据 (JSON)
│   └── 包含：任务描述、步骤列表、成功状态等
│
├── 📄 html_0.html                   # 每一步的 HTML 快照
├── 📄 html_1.html
├── ...
│
├── 🖼️ screenshot_0.png              # 每一步的普通截图
├── 🖼️ screenshot_1.png
├── ...
│
├── 🖼️ screenshot_som_0.png          # Set-of-Mark 标注截图
├── 🖼️ screenshot_som_1.png          # (带有元素 ID 标记)
├── ...
│
├── 🖼️ screenshot_final.png          # 最终页面截图
│
├── 📋 step_simulator_flow.log       # 详细执行日志
└── 📋 run.log                       # 完整运行输出
```

### 主数据文件格式 (`task_trajectory_data.json`)

```json
{
  "init_url": "https://www.amazon.com/",
  "viewport-width": 1280,
  "viewport-height": 720,
  "actions": [
    {
      "step": 0,
      "action_type": "CLICK",
      "element_id": "123",
      "screenshot": "screenshot_0.png",
      "html": "html_0.html",
      ...
    },
    ...
  ],
  "task_summary": "搜索无线蓝牙耳机并加入购物车",
  "verifier_agent_response": "success/failure",
  "total_steps": 8
}
```

## 🔄 工作流程

```
1. 用户配置
   └─> config.sh

2. 启动脚本
   └─> quick_start.sh
       ├─> 检查环境
       ├─> 启动 Xvfb
       └─> 循环处理每个 URL

3. 对于每个 URL:
   └─> python -m traj_gen.main
       ├─> 初始化浏览器 (browser_env.py)
       ├─> 生成初始任务 (task_proposal_agent.py)
       ├─> 执行步骤循环:
       │   ├─> 获取页面状态
       │   ├─> 调用 LLM (llm_utils.py)
       │   ├─> 执行动作
       │   ├─> 保存截图和 HTML
       │   └─> 优化任务 (task_refiner_agent.py)
       ├─> 验证结果 (trajectory_verifier.py)
       └─> 保存数据 (task_trajectory_data.json)

4. 输出结果
   └─> trajectories/traj_N_TIMESTAMP/
```

## 🎯 使用场景

### 场景 1: 快速测试

```bash
cp config.template.sh config.sh
nano config.sh  # 填入 API key
./quick_start.sh
```

### 场景 2: 批量生成

```bash
# 编辑 config.sh，添加 100 个 URL
export URLS=(
    "https://site1.com/"
    "https://site2.com/"
    ...
    "https://site100.com/"
)

./quick_start.sh
```

### 场景 3: 自定义任务

```bash
source config.sh
python -m traj_gen.main \
    --model-dir ./my_custom_traj \
    --init-url "https://example.com/" \
    --max-steps 20
```

### 场景 4: 集成到 Python 程序

```python
import subprocess
import os

# 设置环境变量
env = os.environ.copy()
env.update({
    'DASHSCOPE_API_KEY': 'sk-xxxxx',
    'API_BASE_URL': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'MODEL_NAME': 'kimi-k2-5',
    'DISPLAY': ':99'
})

# 运行生成
subprocess.run([
    'python', '-m', 'traj_gen.main',
    '--model-dir', './output',
    '--init-url', 'https://example.com/',
    '--max-steps', '10'
], env=env)
```

## 📊 性能参考

**单条轨迹生成时间：**
- 简单任务 (5 步)：约 3-5 分钟
- 中等任务 (10 步)：约 6-10 分钟
- 复杂任务 (15 步)：约 10-15 分钟

**影响因素：**
- API 响应速度
- 网页加载时间
- 步骤数量
- 浏览器分辨率

## 🔒 安全注意事项

1. **API 密钥保护**
   - 不要提交 `config.sh` 到 git
   - 已添加到 `.gitignore`

2. **网络安全**
   - 轨迹生成会访问真实网站
   - 确保网络环境安全

3. **数据隐私**
   - 截图可能包含敏感信息
   - 注意存储和分享

## 🆘 故障排查

### 问题定位流程

```
1. 检查日志文件
   ├─> trajectories/traj_N/run.log
   └─> trajectories/traj_N/step_simulator_flow.log

2. 常见错误类型
   ├─> API 调用失败 → 检查 API key 和网络
   ├─> 浏览器启动失败 → 检查 Chrome 和 Xvfb
   ├─> 元素定位失败 → 页面加载或 SOM 标注问题
   └─> 超时错误 → 增加 max_steps 或检查网络

3. 调试技巧
   ├─> 查看截图了解当前页面状态
   ├─> 检查 HTML 快照验证元素存在
   └─> 启用详细日志 (修改 logging level)
```

## 📚 延伸阅读

- **原始论文**: [Explorer: Scaling Exploration-driven Web Trajectory Synthesis](https://aclanthology.org/2025.findings-acl.326.pdf)
- **GitHub 仓库**: https://github.com/OSU-NLP-Group/Explorer
- **DashScope 文档**: https://help.aliyun.com/zh/dashscope/
- **Playwright 文档**: https://playwright.dev/python/
