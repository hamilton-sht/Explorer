# Kimi K2.5 与 Claude Opus 4.7 Rollout 对比报告

## Kimi 配置

```yaml
model_name: kimi-k2-5
base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
api_key: 通过环境变量 API_KEY 注入，未写入仓库文件
```

本次 Kimi rollout 严格使用：

- viewport：`1280x760`
- `--max-steps 50`
- GitHub 首页：`https://github.com/`
- refiner 最近 5 步 SOM 图片历史：开启

Kimi batch：`/home/ubuntu/Explorer/trajectories/kimi_k2_5_rollout_20260607/batch_1280x760_085926`

Claude 对照 batch：`/home/ubuntu/Explorer/trajectories/refiner_history_rollout_20260607/batch_062632`

## 图片尺寸确认

Kimi 5 条轨迹的 `screenshot_0.png` 均为：

```text
1280 x 760
```

因此本次符合“图片格式一定要 1280*760”的要求。

## Kimi 逐条结果

| Run | Actions | Verifier | Summary | Regex fail | Reasoning 泄漏 | API calls | Input tokens | Output tokens | 成本 | Runtime |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| `github_50_1` | 23 | success | regex fail | yes | 0 | 27 | 244,955 | 8,647 | `$1.4410` | 2,646s |
| `github_50_2` | 21 | failure | regex fail | yes | 0 | 24 | 221,528 | 7,821 | `$1.3032` | 2,083s |
| `github_50_3` | 47 | failure | regex fail | yes | 2 | 52 | 532,548 | 15,166 | `$3.0419` | 4,100s |
| `github_50_4` | 44 | failure | regex fail | yes | 3 | 52 | 544,225 | 16,085 | `$3.1233` | 4,231s |
| `github_50_5` | 18 | failure | regex fail | yes | 0 | 21 | 189,827 | 6,191 | `$1.1039` | 2,137s |

## Kimi 汇总

| 指标 | Kimi |
|---|---:|
| 完成落盘 | 5 / 5 |
| 满 50 actions | 0 / 5 |
| 总 actions | 153 |
| Verifier success | 1 / 5 |
| Verifier failure | 4 / 5 |
| regex fail | 5 / 5 |
| reasoning 泄漏轨迹 | 2 / 5 |
| reasoning 泄漏 step 总数 | 5 |
| API reported 总成本 | `$10.0132` |
| 平均成本 / action | `$0.0654` |
| 平均 runtime / trajectory | 3,039.4s |

## 与 Claude Opus 4.7 历史图批次对比

Claude 对照批次同样是 GitHub 5 条、`--max-steps 50`、refiner 最近 5 步历史图，但 Claude 使用 1280 max edge / quality 80 压缩；Kimi 使用 viewport 1280x760 的 image_url 输入。

| 指标 | Claude Opus 4.7 | Kimi K2.5 |
|---|---:|---:|
| 完成落盘 | 5 / 5 | 5 / 5 |
| 满 50 actions | 0 / 5 | 0 / 5 |
| 总 actions | 175 | 153 |
| Verifier success | 1 / 5 | 1 / 5 |
| Verifier failure | 4 / 5 | 4 / 5 |
| regex fail | 4 / 5 | 5 / 5 |
| reasoning 泄漏轨迹 | 2 / 5 | 2 / 5 |
| reasoning 泄漏 step 总数 | 8 | 5 |
| API reported 总成本 | `$5.9091` | `$10.0132` |
| 平均成本 / action | `$0.0338` | `$0.0654` |
| 平均 runtime / trajectory | 2,502s | 3,039.4s |

## 结论

Kimi K2.5 可以跑通当前多模态流程，并且截图尺寸已确认是 `1280x760`。但在这批 5 条 GitHub 50-step rollout 中，Kimi 的整体数据质量没有超过 Claude：

1. Kimi 5 条全部 `summary = regex fail`，比 Claude 更差。
2. Kimi verifier success 也是 1 / 5，没有改善。
3. Kimi 总 actions 153，低于 Claude 的 175。
4. Kimi API reported 平均成本/action 约 `$0.0654`，接近 Claude 的 1.94 倍。
5. Kimi 平均耗时也更高，约 3,039s/条。

因此当前 pipeline 下，Kimi 不适合作为替代 Claude 的更优方案。主要瓶颈仍然不是单纯模型能力，而是：

- task drift
- summary 正则解析不稳定
- `--max-steps` 只是上限
- refiner 图片历史增加成本和耗时，但没有明显提升成功率

## 建议

1. 暂时不要把 Kimi 作为主力 rollout 模型。
2. 优先修 `TaskSummarizationAgent` 的输出格式，避免 `regex fail`。
3. 冻结 original task，避免 refiner 不断新增约束。
4. refiner 图片历史建议改成可选，并优先测试最近 2 步，而不是 5 步。
