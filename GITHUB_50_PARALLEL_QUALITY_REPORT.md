# GitHub 5 条 50-step 并行任务质量统计

## 批次信息

- 批次目录：`/home/ubuntu/Explorer/trajectories/github_50steps_parallel_20260606/batch_111617_nohup`
- 网站：GitHub
- 每条目标：`--max-steps 50`
- 实际启动方式：5 个任务并行运行
- 模型：`claude-opus-4-7`
- API：`https://api-int.memtensor.cn/v1`
- 价格：input `$5/M`，output `$25/M`，cache read `$0.5/M`

## 逐条结果

| Run | Actions | Verifier | Summary | Regex fail | Reasoning 泄漏 | API calls | Input tokens | Output tokens | 成本 | Runtime |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| `github_50_1` | 12 | success | Find and star a Python data visualization repository that serves as a popular alternative to Matplotlib with over 10000 stars on GitHub | no | 0 | 16 | 2,427 | 13,532 | `$0.3504` | 264s |
| `github_50_2` | 43 | failure | regex fail | yes | 0 | 52 | 5,727 | 53,577 | `$1.3681` | 1,259s |
| `github_50_3` | 6 | success | Find and star a Python machine learning repository with over 1000 stars sorted by recently updated on github | no | 1 | 11 | 1,338 | 8,354 | `$0.2155` | 175s |
| `github_50_4` | 46 | failure | regex fail | yes | 5 | 51 | 1,619 | 48,504 | `$1.2207` | 1,109s |
| `github_50_5` | 47 | failure | regex fail | yes | 3 | 89 | 14,041 | 82,126 | `$2.1234` | 1,726s |

## 汇总

| 指标 | 数值 |
|---|---:|
| 完成落盘轨迹 | 5 / 5 |
| 满 50 actions 的轨迹 | 0 / 5 |
| Early stop / 未满 50 | 5 / 5 |
| 总 actions | 154 |
| Verifier success | 2 / 5 |
| Verifier failure | 3 / 5 |
| `regex fail` 轨迹 | 3 / 5 |
| reasoning 泄漏轨迹 | 3 / 5 |
| reasoning 泄漏 step 总数 | 9 |
| 总 API reported cost | `$5.2781` |
| 平均成本 / action | `$0.0343` |
| 平均 runtime / trajectory | 906.6s |

## 质量判断

这批 5 条不能直接作为高质量 50-step 数据使用，主要问题：

1. 没有任何一条达到 50 actions。`--max-steps 50` 只是上限，模型仍然会提前 stop 或流程失败。
2. 3 条出现 `task_summary = regex fail`，说明 summary 阶段解析或模型输出格式不稳定。
3. 3 条存在 reasoning 泄漏 element/SOM 相关信息，说明仅靠 prompt 约束还不能完全消除泄漏。
4. 并行运行会增加不稳定性：run5 的 API calls 明显偏高，说明存在 retry 或重复调用。

## 当前可用性

- 可作为调试/失败样本：5 条都可保留。
- 可作为高质量成功轨迹：最多只有 `github_50_1` 和 `github_50_3` 候选，但它们分别只有 12 和 6 actions，不符合 50-step 要求。
- 不建议纳入正式 50-step 数据集：本批整体不达标。

## 建议下一步

1. 如果必须要 50 actions，应在 prompt 中明确“不要 stop，除非页面要求登录/付款”，并降低 summary 失败率。
2. 对 GitHub 可以从更适合长轨迹的公开入口开始，例如 Trending、Explore、topic 页面，而不是首页。
3. 并行度建议先从 2 workers 开始校准，再提高到 5 或更多。
4. 如果坚持不用硬编码 sanitizer，那么需要继续加强 prompt，并把 reasoning 泄漏作为 reject 条件。
