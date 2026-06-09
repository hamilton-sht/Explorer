# Track A — Trajectory Synthesis (使用 + 机制)

Track A = Explorer 仅拿到一个 URL,自己 propose 任务、refine 动作、最后 verify 自己。**只为合成训练轨迹**,不评测。

---

## 一、快速开始

```bash
cd /home/haotingshi/Explorer

# 跑默认 30 站(均匀采样 6 个 domain)
API_KEY=<sk-...> DISPLAY=:99 \
  /home/haotingshi/miniconda3/envs/osworld/bin/python \
  scripts/run_trackA.py \
  --model gpt-5.5 \
  --api-base-url https://api-int.memtensor.cn/v1 \
  --api-key <sk-...> \
  --sample-file data/webgym_sites_sample_30.jsonl \
  --max-steps 8 \
  --workers 4

# 自定义站点
--sample-file data/webgym_sites_sample_100.jsonl
--sample-file data/webgym_sites_all.jsonl     # 全量 1158 站
```

输出:`trajectories/trackA_<timestamp>/task_NN_<id>/task_trajectory_data.json` + 各步截图 + run.log + summary.json

---

## 二、站点数据

`data/` 目录是从 webgym test.jsonl 抽取去重后的站点索引(只保留 URL+domain,**不带 task**):

| 文件 | 站点数 | 用途 |
|---|---|---|
| `webgym_sites_all.jsonl` | 1158 | 全量,生产合成数据 |
| `webgym_sites_sample_300.jsonl` | 300 | 中等规模快速跑 |
| `webgym_sites_sample_100.jsonl` | 100 | 中规模 |
| `webgym_sites_sample_30.jsonl` | 30 | 6 domain 各 5 站,平衡 |
| `webgym_sites_sample_10.jsonl` | 10 | smoke test |

每行:`{"task_id": "site_0042", "website": "...", "domain": "...", "subdomain": "..."}`。

已知死站 (`also.de`) 已剔除。新发现死站手动加到 `data/` 生成脚本的 DEAD 集合,重新生成。

---

## 三、核心机制

```
URL → TaskProposalAgent (step 0)  →  refined_goal
       ↓
       loop step 1..max_steps:
         screenshot + history → TaskRefinerAgent → grounded action → execute
         若 action ∈ {answer(...), stop()} → 自然终止 → break
       ↓
       TaskSummarizationAgent  → summarization_pred (描述真正做到的事)
       ↓
       决定 verifier 看什么 user_intent:
         - 自然终止 → 用 proposal 原任务
         - 跑满 max_steps 且 ≥2 实质动作 → RELABEL → 用 summarization 写的新任务
         - summarization 含 "regex fail" / 过短 → 不重标
       ↓
       TrajectoryVerifierAgent (看全部截图) → Status: success/failure/unknown
       ↓
       certificate.relabeled = True/False
       写 task_trajectory_data.json
```

### Step 0: TaskProposalAgent
看 homepage 截图,自由 propose 一个 ≤20 步可解的具体目标。3 条核心规则:
- 必须具体可验证(有目标值/页面/数字)
- ≤20 atomic actions
- 描述"WHAT to find",不规定"HOW to navigate"(避免提前焊死路径)

输出:`{"task": "...", "action_in_natural_language": "...", "grounded_action": "click(x,y)"}`

### Step 1..N: TaskRefinerAgent
看当前截图 + 历史截图(`refiner-image-history-steps`,默认 = max_steps,即看全)+ NL action history,产出下一步原子动作。

**Action space**(绝对像素,1920×1080):
```
click(x,y), doubleclick(x,y), rightclick(x,y), hover(x,y), move(x,y)
type("text"), press("Enter"), keyup("shift")
scroll("down", 600), wait(), go_back(), go_forward(), navigate("https://...")
zoom_region(x,y,w,h), zoom_out()
answer("final answer")  # 任务完成
stop()                  # 任务不可解(登录墙/CAPTCHA/不存在)
```

**Task fidelity rule with controlled pivot**:默认保留原任务字面;只有当原任务真做不下去(探索≥3 条路径无果 OR 目标显然不存在)才允许 pivot 到同域同主题、≤3 步可解的相关任务。

### 防止"regex fail"哨兵泄漏
LLM 返回解析失败时 refiner 回填 `{"task": "regex fail", ...}`。`main.py` 检测到这个哨兵不会让它进 `refined_goal`,fall back 到上一个有效 goal。

### TaskSummarizationAgent
看 action history + 最多 10 张截图(`summarization-max-screenshots`),输出 **"轨迹实际达成的最 ambitious 任务"**:
- 只用正面 outcome 动词:`Open / Reach / Locate / Select / Enter / Navigate to / View / Display`
- 禁用承诺式动词:`Subscribe / Book / Purchase / Complete checkout`
- 不提失败尝试 / 未达成目标
- 最终截图必须能验证

### 重标判定(`budget_hit_relabel`)
全部满足才触发:
1. 没自然终止(`answer/stop` 不在最后)
2. ≥2 个非 scroll/wait/stop/answer 的实质动作
3. summarization_pred 不为空
4. 不含 "regex fail" 字面
5. 长度 ≥20 字符

触发时:`user_intent = summarization_pred`,`original_task ← summarization_pred`(原 propose 任务被覆盖),`certificate.relabeled = True`,`certificate.relabel_reason = "budget_exhausted_no_natural_termination"`。

### TrajectoryVerifierAgent
看 user_intent + 全部 step-labeled 截图(step i 后的页面)+ 最后页 markdown,输出:
```
Thoughts: ...
Status: "success" / "failure"
```
对 `stop()` 的语义:有 blocker(登录墙/CAPTCHA)→ success;能继续却 stop → failure。
对 information seeking:任何中间截图含答案就算到达。

### 容错(三层)
1. **`get_state()` 3 次重试** — 截图/HTML 失败不丢历史
2. **Verifier 调用 try/except** — verifier 崩了写 `Status: unknown`,继续保存
3. **`flow.run()` 最外层 try/except** — 任何崩溃都写一个 stub JSON,保证子进程不丢

---

## 四、关键参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--max-steps` | 8 | 最大 step;比这个长就走重标 |
| `--workers` | 4 | 并发(15GB RAM 安全上限) |
| `--timeout` | 900 | 单任务秒数 |
| `--refiner-image-history-steps` | = max_steps | refiner 看历史截图数量 |
| `--summarization-max-screenshots` | 10 | summarizer 看截图数量 |
| `--min-actions-before-stop` | 3 | 早 stop 强制改 scroll 的阈值 |
| `--verifier-intent-source` | original | verifier 用原任务(natural) or summary(默认 original,重标会自动覆盖) |

---

## 五、输出结构

```
trajectories/trackA_<timestamp>/
├── summary.json                    # SR, counts, configs
└── task_NN_<id>/
    ├── task_trajectory_data.json   # ★ 主产物
    ├── screenshot_0..N.png         # 每步前的页面
    ├── screenshot_final.png        # 最终页
    ├── html_0..N.html              # 每步 HTML
    ├── run.log                     # 子进程 stdout
    ├── step_simulator_flow.log     # 详细执行日志
    └── llm_usage.jsonl             # LLM 调用 token 计费
```

`task_trajectory_data.json` 关键字段:
- `instruction` / `task_summary` — verifier 看到的任务(可能是重标后)
- `original_task` — 重标后会被覆盖,看 `certificate.relabeled` 区分
- `actions` — 完整轨迹
- `steps` — 数据 spec 兼容的 step 记录
- `verifier_agent_response` — 完整 judge 文本
- `final.completion_status` — success / failed
- `final.verifier.status` — correct / incorrect / unknown
- `certificate.relabeled` — true/false
- `certificate.aux_summarization_response` — 完整 summary 文本
- `gold_output.answer` — agent 给的 answer

---

## 六、二次评判

如果改 verifier prompt 后想重判已有 run,用:
```bash
python scripts/rejudge_run.py \
  --run-dir trajectories/trackA_<timestamp> \
  --model gpt-5.5 \
  --api-base-url ... --api-key ...
```
写 `re_verifier_response.txt` 和 `re_verifier_summary.json` 到每个 task 目录,**不动**原 JSON。

---

## 七、当前限制

- 弹窗多的电商站(buyagift 等)8 步会被 cookie/sign-up 弹窗吃掉一半预算 → 可放宽到 `--max-steps 12`
- 第 0 步只 `wait()` 就退出的 agent 不触发重标(`n_substantive < 2`),按原任务判 failure
- 真死站(DNS/网络层)无救,加入 `data/` 生成脚本的 DEAD 集合
- Relabel 任务可能是"机会主义路径"(agent 误点到的页面被包装成目标)— 训练时如担心,过滤 `certificate.relabeled=true` 子集再人工抽样
