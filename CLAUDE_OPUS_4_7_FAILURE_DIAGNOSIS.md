# Claude Opus 4.7 失败原因诊断与修复

## 结论

Claude Opus 4.7 本身能跑通，但当前 pipeline 的失败主要来自四个地方：

1. `TaskSummarizationAgent` 不稳定，长轨迹时经常 `regex fail`。
2. summary 失败后，代码把 `regex fail` 当成 verifier 的 user intent，导致 verifier 被污染。
3. `TaskRefinerAgent` 每步都更新 task，容易 task drift，把任务越改越难甚至不可验证。
4. GitHub 某些 UI，尤其 language dropdown / search suggestion，容易让 agent 卡循环。

因此失败不是单纯模型能力问题，而是数据生成 pipeline 的稳定性问题。

## 证据

### Claude refiner-history 批次

批次：`trajectories/refiner_history_rollout_20260607/batch_062632`

| Run | Actions | Verifier | Summary | 主要问题 |
|---|---:|---|---|---|
| `github_50_1` | 42 | failure | regex fail | summary fail，verifier intent 被污染；搜索 suggestion 反复点击 |
| `github_50_2` | 40 | failure | regex fail | summary fail；搜索框重复 type/clear，任务漂移 |
| `github_50_3` | 44 | failure | regex fail | summary fail；Issues tab 定位失败，反复 scroll up |
| `github_50_4` | 12 | success | 正常 | 成功找到并 star TensorFlow，但早停 |
| `github_50_5` | 37 | failure | regex fail | summary fail；反复在搜索结果和 repo 页面之间导航 |

### 对照成功样本

`trajectories/github_50steps_20260606/github_50_1_no_pricing_090610`

- actions: 50
- verifier: success
- summary: 正常

说明 Claude 可以跑出 50-step success。问题集中在 pipeline 稳定性，而不是模型完全不能做。

## 根因 1：Summary 阶段太脆弱

旧逻辑：

- summary 输出必须包含 ```...``` code fence
- 如果没有匹配到，就直接 `pred = regex fail`
- 后续 verifier 用 `regex fail` 当 user intent

结果：

```text
task_summary = regex fail
user_intent = regex fail
verifier 根据 regex fail 判定失败
```

这是最严重的问题。很多轨迹的 action history 本身并不是完全坏，但最后 summary 解析失败后整条轨迹被污染。

## 根因 2：Summary 传图过多

旧逻辑会把 action history 对应的截图都传给 summarizer。50-step 长轨迹就可能传几十张图。

即使 Claude 兼容层压缩图片，长轨迹 summary 请求仍然很重，容易导致：

- API 超时
- 输出格式异常
- summary regex fail

Kimi 上这个问题更明显，直接出现 write timeout；Claude 上表现为 summary 不稳定和 regex fail。

## 根因 3：Task drift

`TaskRefinerAgent` 每一步都会输出新的 `task` 字段，并且 prompt 原本要求：

```text
Update the overall task aligned with this set of actions.
```

这会导致任务逐步变复杂：

- 原本只是找一个 repository
- 后面加 star 数、更新时间、语言、topic、issues、README、community activity
- 最后 verifier 发现页面无法证明所有条件，于是 failure

长轨迹越长，task drift 风险越高。

## 根因 4：GitHub UI 卡循环

失败日志里反复出现：

- language dropdown 里输入 Python，但没有真正点击 Python 选项
- search suggestion 被反复点击，但没有进入稳定结果页
- scroll up/down 试图找 Issues tab 或 README 内容，但页面状态没有推进

这类失败不是模型不会读页面，而是 GitHub 动态 UI + SOM/accessibility tree 状态经常让 action grounding 变得不稳定。

## 已实现修复

### 1. Summary 最多只传最后 3 张图

新增参数：

```bash
--summarization-max-screenshots 3
```

默认值：3。

目的：降低 summary 请求体大小，减少超时和格式异常。

### 2. Summary regex fail fallback

如果 summarizer 仍然输出失败：

- 优先 fallback 到 `original_task`
- 其次 fallback 到最后一个非 regex 的 refined task

这样不会再把 `regex fail` 直接作为 verifier intent。

### 3. 保存 `original_task`

step 0 生成的原始任务现在会保存到：

```json
"original_task": "..."
```

后续可以用它判断 task drift。

### 4. Summary 解析增强

除了 ```...```，现在也尝试解析：

- `In summary, the answer is: ...`
- `overall task description: ...`
- `task description: ...`
- 最后一条非空行

减少纯格式问题导致的 regex fail。

### 5. Refiner prompt 限制 task drift

已加入约束：

- 不要新增新的 star count、日期、过滤器、成功条件
- 不要把 discovery task 改成更复杂的 comparison task
- `task` 字段应尽量保持原始 overall task

### 6. History 保持开启

按你的要求，refiner 最近 5 步图片历史保持开启：

```bash
--refiner-image-history-steps 5
```

默认值也已设为 5。

## Smoke Test 结果

修复后使用 Claude Opus 4.7 跑 5-step smoke：

目录：`trajectories/claude_fix_smoke_20260607/github_smoke_131755`

结果：

- actions: 5
- viewport: `1280x760`
- history: 开启，最近 5 步
- `task_summary`: 正常，不是 regex fail
- `original_task`: 正常保存
- API retry: 无
- traceback: 无
- verifier: failure，因为 5 步太短，尚未完成比较任务

这个 smoke 证明：summary regex fail/fallback 这条链路已经修通。

## 还需要继续修的点

### 高优先级

1. 冻结 task，用 `original_task` 做 verifier intent，而不是 summary 反推任务。
2. 对 GitHub language dropdown 增加 prompt 规避：失败两次后不要继续 dropdown，改用 GitHub search query。
3. 对重复 action 增加检测：连续多次相同 click/type/scroll 且 URL 不变时，强制换策略。

### 中优先级

1. Summary 可以完全改成文本-only：action list + final URL + original task，不传图。
2. Verifier 对 navigation task 和 information-seeking task 分开评估。
3. 50-step 如果是硬要求，需要 min-step 机制；否则 `--max-steps` 只是上限。

## 建议下一步

用 Claude Opus 4.7 重新跑一小批 5 条，配置：

```bash
--viewport-width 1280
--viewport-height 760
--refiner-image-history-steps 5
--summarization-max-screenshots 3
--max-steps 50
```

然后比较：

- regex fail 是否从 4/5 降低
- verifier success 是否提高
- history 开启时 runtime 是否仍可接受
- task drift 是否减少
