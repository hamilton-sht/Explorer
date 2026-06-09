# Active Lifting Mid Train / SFT 数据需求文档

配套格式规范文档:

*   [《Active Lifting Browser Demo 数据格式标注规范》](https://alidocs.dingtalk.com/i/nodes/Amq4vjg8903oeQA3TPYOK920J3kdP0wQ?iframeQuery=utm_source%3Dportal%26utm_medium%3Dportal_recent): 轨迹、动作、tool call 标记、拒收和质检细则。
    
*   [《SFT / RL 数据收集团队交付规范》](https://alidocs.dingtalk.com/i/nodes/mweZ92PV6M0ByL60TKRm60jvWxEKBD6p?cid=5458921075:6618931269&utm_source=im&utm_scene=team_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&dontjump=true&corpId=ding9ce80ba1f8bbb896ffe93478753d9884): 交付物、`data_type`、manifest、验收门槛。
    

## 0. 数据格式先说明

本项目数据按 **trajectory** 交付。一条 trajectory 是针对一张图片的一段按时间排列的观察与动作记录:

```text
当前图片 x_t
-> 当前步模型文本 w_t
-> 可选工具调用 <|tool_call>action<tool_call|>
-> 执行动作后的下一张图片 x_next
-> 下一步继续
```

换成数据字段, 每一步至少要能写清楚:

| 字段 | 含义 | 要求 |
| --- | --- | --- |
| `x_t.image` | 当前浏览器/桌面/图片观察 | 保存截图或图片路径 |
| `env_meta_t` | 当前环境元信息 | URL、viewport、screen size、上一步结果等 |
| `w_t` | 当前步文本 | 可以是简短思考, 也可以包含工具调用 |
| `tool_call_token` | 工具调用结束触发标记 | 固定为 `<tool_call\|>` |
| `parsed_action` | 从 `w_t` 中解析出的动作 | 有动作时必填, 无动作时为 `null` |
| `env_meta_next` | 后继环境元信息 | 记录执行是否成功、URL/viewport 变化等 |

标准 JSONL 形态如下, `trajectories.jsonl` 每行一条:

```json
{
  "trajectory_id": "traj_001",
  "resolution":{
    "width": 512,
    "height": 720,
  },
  "task": {
    "task_id": "search_001",
    "feasibility":"true|false", 
    "instruction": "查找一个至少有 300 stars，且最近 5 天内更新的 Julia GitHub 仓库，并说明其主要用途。",
    "start_url": "https://github.com",
  },
  "steps": [
    {
      "t": 0,
      "x_t": {
        "image": "observations/traj_001/000/screenshot.jpg"
      },
      "env_meta_current": {
        "observation_id": "traj_001_000",
        "url": "https://github.com",
        "viewport": { "width": 512, "height": 720 }
      },
      "Cot":"需要使用 GitHub 的搜索功能查找 Julia 仓库，先打开导航菜单。" 
      "w_t": "需要使用 GitHub 的搜索功能查找 Julia 仓库，先打开导航菜单。打开左上角导航菜单。<|tool_call>click(27.65, 22.13)<tool_call>",
      "tool_call_token": "<tool_call|>",
      "parsed_action": {
        "name": "click",
        "args": { "x": 27.65, "y": 22.13 }
      },
      "x_next": {
        "image": "observations/traj_001/001/screenshot.jpg"
      },
      "env_meta_next": {
        "observation_id": "traj_001_001",
        "url": "https://github.com",
        "viewport": { "width": 512, "height": 720},
      }
    },
    {
      "t": 1,
      "x_t": {
        "image": "observations/traj_001/001/screenshot.jpg"
      },
      "env_meta_current": {
        "observation_id": "traj_001_001",
        "url": "https://github.com",
        "viewport": {
          "width": 512,
          "height": 720,
        }
      },
      "Cot": "导航菜单中已经显示搜索入口，下一步激活搜索框。",
      "w_t": "导航菜单中已经显示搜索入口，下一步激活搜索框。点击 Search or jump to 搜索框。<|tool_call|>click(202.27, 351.70)<tool_call|>",
      "tool_call_token": "<|tool_call|>",
      "parsed_action": {
        "name": "click",
        "args": {
          "x": 202.27,
          "y": 351.70,
        }
      },
      "x_next": {
        "image": "observations/traj_001/002/screenshot.jpg"
      },
      "env_meta_next": {
        "observation_id": "traj_001_002",
        "url": "https://github.com",
        "viewport": {
          "width": 512,
          "height": 720,
        },
      }
    },    
  ],
  "final": {
    "completion_status": "success", {success,failed,not_applicable}
    "factuaclity_status": "factuaclity_valid" {factuaclity_valid,factuaclity_invalid,terminate}
    "answer": "....",
    "verifier": { "status": "correct" } {correct,incorrect}
  }
}
```

**备注:** 

**1 Cot 是 w\_t的子串；w\_t需包含Cot, 同时给出response** 

**2 feasibility: true  表示该任务理论上可以完成 false 表示该任务理论上无法完成**

**3 completion\_status: success 表示在 feasible case 中，answer 成功完成任务 ;failed  表示在 feasible case 中，answer 没有成功完成任务 ;not\_applicable 表示 infeasible case 中不评价任务完成情况**

**4 factuality\_status: factually\_valid 表示 answer 与 image、query、feasibility 一致； factually\_invalid  表示 answer 与 image、query、feasibility 不一致 ；terminate 表示 answer 为空字符串，模型终止**

### 0.1 工具调用写法

如果当前步有动作, 动作必须写在 `<|tool_call>` 和 `<tool_call|>` 之间:

```text
我需要点击搜索框。<|tool_call>click_xy(320, 120)<tool_call|>
```

如果当前步没有动作, `parsed_action` 写 `null`, 且 `x_next.image` 必须等于 `x_t.image`。

### 0.2 允许的主要动作

| 动作 | 写法 |
| --- | --- |
| 移动 | move(x,y) |
| 悬停 | hover(x,y) |
| 点击 | `click(x, y)` |
| 双击 | `doubleclick(x,y)` |
| 右键 | `rightclick(x,y)` |
| 输入 | `type("text")` |
| 按键 | `press("Enter")` |
| 快捷键 | `hotkey("Ctrl C")` |
| 按键按下 | `keydown("shift")` |
| 按键松开 | `keyup("shift")` |
| 滚动v1 | `scroll("down", 600)` |
| 滚动v2 | `scroll_container(x,y,"down", 600)` |
| 拖拽 | `drag(x1, y1, x2, y2)` |
| 等待 | `wait()` |
| 后退/前进 | `go_back()` / `go_forward()` |
| 导航 | `navigate("https://allowed.example")` |
| 区域框选 | `zoom_region(x, y, w, h)` |
| 返回原图 | `zoom_out()` |
| 最终回答 | `answer("final answer")` |
| 放弃/停止 | `stop()` |

**坐标默认按当前截图的 pixel 坐标填写 , 并必须保存** `**screen_size**`**。如果来源数据使用归一化坐标, 必须显式写** `**coordinate_space**`**, 不要混写。**

### 0.3 三类数据都按这个格式交

| 数据类型 | 轨迹形态 |
| --- | --- |
| 静态 QA / MMMU 类 | 单步: `图片 -> 思考/CoT -> answer()` |
| 高分辨率 / 文档 / 图表 | 少步: `全图 -> zoom_region -> 局部观察 -> answer()` |
| Browser / Computer Use | 多步: `截图 -> thought/action -> 下一张截图 -> ... -> answer/stop` |

只要进入本项目交付, 都按上述 trajectory 形态组织。

## 1. 总量需求

| 阶段 | 总量 | 数据桶 | 量 | 质量要求 | verifier 要求 |
| --- | --- | --- | --- | --- | --- |
| Mid Train | 20B tokens | 通用 benchmark 相关多模态数据 | 14B | 可为 `bulk` | 可选, 建议保留 certificate |
|  |  | Active Lifting / Computer Use 轨迹数据 | 6B | 可为 `bulk` | 建议有 |
| SFT | 10B tokens | 通用 benchmark 数据改造成 AL 轨迹格式 | 7B | 必须 `clean` | 必须 |
|  |  | Active Lifting / Computer Use 轨迹数据 | 3B | 必须 `clean` | 必须 |

硬规则:

1.  所有数据统一按轨迹格式交付。静态 QA 也表示成单步或少步 `observe -> think -> answer` 轨迹。
    
2.  SFT 数据不能把 Mid Train 数据简单加 label 复用。SFT 必须是重新筛选、改写、验证后的 `clean` 数据。
    
3.  SFT / RL / reward-audit 中 `quality_tier=bulk` 的样本数必须为 0。
    
4.  重点 benchmark 的 CoT / thinking trace 若原始数据存在, 必须保留, 不得压扁成 answer-only。
    
5.  SFT数据需要多步的， 而并非单步交互
    

## 4. 交付物

每批数据必须包含:

| 文件 | 必需 | 说明 |
| --- | --- | --- |
| `manifest.json` | 是 | 数据版本、来源、split、数量、token 数、污染控制、verifier 版本 |
| `tasks.jsonl` | 是 | 每行一个任务样本 |
| `trajectories.jsonl` | 是 | 每行一条轨迹; 静态 QA 也要有 pseudo trajectory |
| `artifacts/` | 是 | 截图、DOM / a11y、bbox、视频、环境快照、日志等引用文件 |
| `qa_report.json` | 是 | 自动质检和人工抽检结果 |
| `rejected.jsonl` | 是 | 被过滤样本及失败原因, 不能直接丢弃 |

## 5. 单样本必需字段

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `sample_id` | 是 | 全局唯一 |
| `trajectory_id` | 轨迹样本必需 | 全局唯一 |
| `stage` | 是 | `mid_train` / `sft` / `rl` / `reward_audit` |
| `split` | 是 | `mid_train` / `sft_train` / `rl_train` / `internal_eval` / `reward_audit` |
| `quality_tier` | 是 | `bulk` / `clean`; SFT 与 RL 只能是 `clean` |
| `data_type` | 是 | 使用 SFT/RL 规范中的枚举 |
| `source_dataset` | 是 | 原始或合成来源 |
| `benchmark_family` | 是 | OSWorld-G、ScreenSpot-Pro、MMMU 等 |
| `instruction` | 是 | 任务指令 |
| `observation_refs` | 是 | 图片、截图、页面快照、文档等 artifact 路径 |
| `steps` | 轨迹样本必需 | 当前观察、模型文本、动作、后继观察 |
| `parsed_action` | 有动作时必需 | 机器可解析动作 |
| `coordinate_space` | GUI/CUA 必需 | `image_pixel` / `normalized_0_1000` 等, 必须显式填写 |
| `screen_size` | GUI/CUA 必需 | 截图宽高 |
| `gold_output` | SFT 必需 | 最终答案、分类、目标状态或 action result |
| `certificate` | SFT/RL 必需 | gold answer、target state、bbox、unit test 等隐藏参考 |
| `verifier` | SFT/RL 必需 | verifier 类型、版本、结果 |
| `license` | 是 | `internal` / `open` / `unknown` |
| `contamination` | 是 | official eval 排除、近重复检查、去污染版本 |
| `token_count` | 是 | 最终训练序列的 effective token 统计, 不计 padding |

## 6. 轨迹格式要求

1.  轨迹按 `x_t -> w_t -> tool_call/action -> x_next` 组织。
    
2.  `x_t` 和 `x_next` 必须是真实 observation 或可回放环境得到的 observation。
    
3.  `parsed_action` 必须与文本动作一致, 不能只写自然语言动作。
    
4.  GUI / CUA 样本必须显式保存 `coordinate_space` 和 `screen_size`。
    
5.  `gold_output`、`certificate`、DOM oracle、bbox oracle 不得出现在 policy-visible 字段中。
    
6.  `answer()` / `stop()` 终止样本必须保留最终 verifier 或 certificate 信息。
    
