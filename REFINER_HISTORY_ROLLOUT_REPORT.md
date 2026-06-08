# Refiner 最近 5 步图片历史 Rollout 报告

## 改动说明

### 1. 当前图片输入大小如何确定

当前有两层尺寸控制：

1. 浏览器截图尺寸由命令行 viewport 决定：

```bash
--viewport-width 1280
--viewport-height 720
```

因此原始截图和 SOM 截图通常是 `1280x720`。

2. 发给 Claude-compatible API 前，会在 `traj_gen/llm_utils.py` 中压缩：

- 旧逻辑：最长边固定压到 `1024`，JPEG quality `75`
- 新逻辑：改成环境变量可调

```bash
export CLAUDE_COMPAT_IMAGE_MAX_EDGE=1280
export CLAUDE_COMPAT_IMAGE_QUALITY=80
```

本次 rollout 使用的是：

- `CLAUDE_COMPAT_IMAGE_MAX_EDGE=1280`
- `CLAUDE_COMPAT_IMAGE_QUALITY=80`

也就是说，可以调大；但调大后每步请求更重，耗时明显增加。

### 2. Refiner 加最近 5 步图片历史

`TaskRefinerAgent` 现在会接收最近 5 张历史 `screenshot_som_N.png`，再加当前截图：

- 历史图：用于理解最近浏览上下文
- 当前图：用于决定下一步 action

实现位置：

- `traj_gen/task_refiner_agent.py`
- `traj_gen/main.py`

## Rollout 配置

- 批次目录：`/home/ubuntu/Explorer/trajectories/refiner_history_rollout_20260607/batch_062632`
- 网站：GitHub
- 任务数：5
- 每条：`--max-steps 50`
- 模型：`claude-opus-4-7`
- 图片压缩：max edge 1280，quality 80
- Refiner history：最近 5 步 SOM 图片

## 逐条结果

| Run | Actions | Verifier | Summary | Regex fail | Reasoning 泄漏 | API calls | Input tokens | Output tokens | 成本 | Runtime |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| `github_50_1` | 42 | failure | regex fail | yes | 0 | 52 | 5,427 | 57,932 | `$1.4754` | 2,753s |
| `github_50_2` | 40 | failure | regex fail | yes | 7 | 52 | 6,247 | 52,532 | `$1.3445` | 2,619s |
| `github_50_3` | 44 | failure | regex fail | yes | 0 | 52 | 16,176 | 64,285 | `$1.6880` | 3,689s |
| `github_50_4` | 12 | success | Find and star a trending Python repository focused on machine learning with over 1000 stars on GitHub | no | 1 | 16 | 2,549 | 13,878 | `$0.3597` | 756s |
| `github_50_5` | 37 | failure | regex fail | yes | 0 | 40 | 6,489 | 40,360 | `$1.0414` | 2,693s |

## 汇总

| 指标 | 数值 |
|---|---:|
| 完成落盘 | 5 / 5 |
| 满 50 actions | 0 / 5 |
| Early stop / 未满 50 | 5 / 5 |
| 总 actions | 175 |
| Verifier success | 1 / 5 |
| Verifier failure | 4 / 5 |
| regex fail | 4 / 5 |
| reasoning 泄漏轨迹 | 2 / 5 |
| reasoning 泄漏 step 总数 | 8 |
| API reported 总成本 | `$5.9091` |
| 平均成本 / action | `$0.0338` |
| 平均 runtime / trajectory | 2,502s |

## 与上一批不带历史图的对比

上一批 5 条 GitHub 50-step 并行结果：

- 总 actions：154
- Verifier success：2 / 5
- regex fail：3 / 5
- reasoning 泄漏轨迹：3 / 5
- 平均 runtime / trajectory：906.6s
- 平均成本 / action：`$0.0343`

本批加最近 5 步图片历史后：

- 总 actions：175，略有增加
- Verifier success：1 / 5，下降
- regex fail：4 / 5，变差
- reasoning 泄漏轨迹：2 / 5，略有改善
- 平均 runtime / trajectory：2,502s，显著变慢
- 平均成本 / action：`$0.0338`，API reported cost/action 接近，但耗时变长很多

## 结论

加最近 5 步图片历史没有明显改善任务成功率，反而让耗时大幅增加。主要问题仍然是：

1. `TaskSummarizationAgent` 经常 `regex fail`。
2. 任务会 drift，后续 task refinement 可能把任务改得不可验证。
3. `--max-steps 50` 只是上限，模型仍提前结束或产生无效 action。
4. 仅靠 prompt 约束，仍不能完全避免 reasoning 泄漏 element/SOM 信息。

## 建议

1. 暂时不要默认给 refiner 加 5 张历史图；可以改成可选开关。
2. 优先修 summary 输出格式，降低 `regex fail`。
3. 冻结 step 0 的 original task，后续 refiner 不再新增约束，只生成下一步 action。
4. 如果要保留图片历史，建议从最近 2 步开始，而不是 5 步，减少耗时和上下文噪声。
