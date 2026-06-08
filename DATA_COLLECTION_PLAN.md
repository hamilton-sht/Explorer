# Explorer 合成轨迹采集计划

## 当前目标

使用 Claude API 采集约 10,000 条浏览器操作轨迹。任务应尽量来自公开网页，避免登录、付款、订阅、试用、注册账号等流程。

当前代码使用 OpenAI-compatible 接口调用 Claude：

- `API_BASE_URL=https://api-int.memtensor.cn/v1`
- `MODEL_NAME=claude-opus-4-7`
- `API_KEY` 只通过环境变量传入
- 当前 key 标识：开头为 `sk-VNdN8...`，结尾为 `...45t30QM0N`

不要把完整 API key 写入仓库文件。

## 建议爬取网站分布

建议 10k 轨迹按下面比例采集：

| 类别 | 网站 | 占比 | 数量 | 原因 |
|---|---|---:|---:|---|
| 开发者仓库 | GitHub | 35% | 3,500 | 公开导航丰富，适合仓库搜索、Trending、README、issues、releases 等长轨迹。 |
| 模型/数据集平台 | Hugging Face | 25% | 2,500 | 支持公开模型/数据集搜索、筛选、模型卡、评测信息浏览。 |
| 文档站 | Python docs、MDN、PyTorch、TensorFlow、npm docs | 15% | 1,500 | 页面稳定，适合多步搜索、目录跳转、文档浏览。 |
| 百科/参考类 | Wikipedia | 10% | 1,000 | 公开信息检索和页面跳转丰富，但部分页面可能较慢或动态加载不稳定。 |
| 包/项目索引 | PyPI、npmjs、crates.io | 10% | 1,000 | 适合包搜索、筛选、详情页浏览，多数内容公开。 |
| 新闻/论文/社区 | Hacker News、arXiv、Papers with Code | 5% | 500 | 公开浏览和搜索可用，但任务完成度验证可能更难。 |

如果短期需要 GitHub 数据，可以临时提高 GitHub 比例；但完整 10k 不建议全部放在 GitHub，否则站点结构重复度会偏高。

## 已加入的 Prompt 约束

当前任务生成和任务 refinement prompt 已做过以下约束：

- reasoning 必须是 general、面向用户的推理。
- reasoning 中不要提 element ID、SOM label、accessibility-tree node ID、bbox、坐标、`[数字]` 这种编号。
- element ID 只允许出现在最终 JSON 的 `grounded_action` 字段中。
- 避免 sign-up、sign-in、注册、订阅 checkout、pricing-plan comparison、trial、try、get started、产品激活等容易进入登录或短轨迹的任务。
- 优先选择公开仓库搜索、仓库发现、Trending/Explore、文档浏览、release/issue/README 浏览等更容易形成长轨迹的任务。

不使用硬编码 sanitizer；只靠 prompt 约束模型输出。

## 样本运行统计

我已在 `traj_gen/llm_utils.py` 加入 usage 记录：只要 API 返回 `usage` 字段，就会追加写入当前轨迹目录下的 `llm_usage.jsonl`。

已完成的样本：

| 网站 | 运行目录 | Max steps | 实际 actions | 耗时 | 有 usage 的 API 调用数 | 输入 tokens | 输出 tokens | 缓存读取 tokens | Verifier |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| GitHub | `trajectories/cost_samples_20260606/github_sample_094110` | 10 | 10 | 206s | 13 | 1,534 | 11,056 | 0 | success |
| Hugging Face | `trajectories/cost_samples_20260606/huggingface_sample_094557` | 10 | 10 | 268s | 13 | 6,196 | 11,472 | 0 | failure |

额外参考的长轨迹：

| 网站 | 运行目录 | Max steps | 实际 actions | 耗时 | Verifier |
|---|---|---:|---:|---:|---|
| GitHub | `trajectories/github_50steps_20260606/github_50_1_no_pricing_090610` | 50 | 50 | 1,017s | success |

Wikipedia 10-step 样本曾启动，但卡在 step 5 附近，已停止，不纳入主估算。

## Token 与价格假设

用户给定价格：

- 输入：`$5.0000 / 1M tokens`
- 输出：`$25.0000 / 1M tokens`
- 缓存读取：`$0.5000 / 1M tokens`

计算公式：

```text
cost = input_tokens / 1e6 * 5 + output_tokens / 1e6 * 25 + cache_read_tokens / 1e6 * 0.5
```

根据两个 10-step 样本的 API reported usage，得到下面均值：

| 指标 | GitHub | Hugging Face | 平均 |
|---|---:|---:|---:|
| 输入 tokens / action | 153.4 | 619.6 | 386.5 |
| 输出 tokens / action | 1,105.6 | 1,147.2 | 1,126.4 |
| 缓存读取 tokens / action | 0 | 0 | 0 |
| 成本 / action | `$0.0284` | `$0.0318` | `$0.0301` |
| 耗时 / action | 20.6s | 26.8s | 23.7s |

注意：这些是 API 返回的 `usage` 数字，看起来对多模态请求偏低。因此它更适合作为 lower-bound estimate。除非 provider 明确确认图像 token 和 cache read 都被完整计入，否则真实成本可能更高。本次样本里接口没有返回 cache-read tokens。

## 10k 轨迹成本与时间估算

按平均 `$0.0301/action` 和 `23.7s/action` 估算：

| 平均 actions / trajectory | 总 actions | 估计 API 成本 | 串行耗时 | 10 workers 耗时 | 50 workers 耗时 |
|---:|---:|---:|---:|---:|---:|
| 10 | 100,000 | `$3,009` | 27.4 天 | 65.8 小时 | 13.2 小时 |
| 15 | 150,000 | `$4,514` | 41.1 天 | 98.8 小时 | 19.8 小时 |
| 30 | 300,000 | `$9,028` | 82.3 天 | 197.5 小时 | 39.5 小时 |
| 50 | 500,000 | `$15,046` | 137.2 天 | 329.2 小时 | 65.8 小时 |

已完成的 GitHub 50-step 长轨迹耗时 1,017s，即 20.3s/action，与短样本估算接近。

## 保守预算区间

由于图像 token 可能被低估，建议按倍率预留预算：

| 场景 | API reported cost 倍率 | 10k x 50-step 估计 |
|---|---:|---:|
| API 返回 usage 的下界 | 1x | `$15.0k` |
| 中等 buffer | 2x | `$30.1k` |
| 多模态保守 buffer | 3x | `$45.1k` |
| 非常保守 | 5x | `$75.2k` |

实际启动 10k 前，建议至少按 2x API reported estimate 预留预算，直到 provider billing dashboard 能确认真实成本。

## 运行方案

1. API key 只用环境变量：

```bash
export API_BASE_URL='https://api-int.memtensor.cn/v1'
export MODEL_NAME='claude-opus-4-7'
export API_KEY='<provided key>'
export CLAUDE_COMPAT_MAX_TEXT_CHARS=20000
```

2. 按网站分 batch 输出，例如 GitHub：

```bash
python -m traj_gen.main   --model-dir trajectories/batch_github/<run_id>   --init-url 'https://github.com/'   --max-steps 50   --seed <seed>   --deployment "$MODEL_NAME"   --viewport-width 1280   --viewport-height 720   --no-use-all-screenshots-verifier
```

3. 每条轨迹建议保留这些文件：

- `task_trajectory_data.json`
- `step_simulator_flow.log`
- `llm_usage.jsonl`
- `runtime_seconds.txt`，如果由 wrapper 启动
- 原始截图和 `screenshot_action_som_*.png`

4. 以下轨迹建议剔除或单独标记：

- `task_summary` 是 `regex fail`
- 如果 batch 要求固定长度，但实际 actions 太少
- 很早遇到 login/payment stop，且没有有效进展
- verifier failure，除非数据集明确需要失败轨迹
- reasoning 在 `grounded_action` 之外提到 element ID 或 SOM label

## 当前风险

- `--max-steps` 只是上限，模型仍可能提前输出 `stop`。
- GitHub 首页容易把模型带到 pricing、sign-up、Copilot 等短流程；prompt 已经降低这种概率，但不能完全保证。
- 部分网站会在页面处理或浏览器状态上卡住，例如 Wikipedia 样本。
- verifier 对 information-seeking 任务比较严格；如果最终页面 markdown 是 None，或者 agent 没有显式返回信息，可能判 failure。
- OpenAI-compatible Claude endpoint 的 usage 可能没有完整包含图像 token 或 cache-read 明细。

## 建议

正式跑 10k 前，先做至少 100 条 calibration batch，覆盖上面的站点分布，然后重新计算：

- 平均 actions / trajectory
- early stop 比例
- verifier success 比例
- `llm_usage.jsonl` 中的实际 usage
- provider billing dashboard 的真实费用
- 每个 worker 的真实吞吐

校准后，再固定各网站 seed 范围，根据机器浏览器容量和 API rate limit，使用 10-50 个并发 worker 跑完整 10k。
