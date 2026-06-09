# Action Protocol 映射方案：UI-TARS2 Benchmark Adapter 与 AL 预训练协议迁移

本文分两部分：

1.  UI-TARS / UI-TARS2 风格的统一 action protocol 如何映射到不同 benchmark 的原生执行协议。
    
2.  和 mid-train 对齐的 Chrome pixel action protocol 如何迁移到 UI-TARS / UI-TARS2-compatible protocol
    

benchmark 的协议差异不应该直接进入模型训练协议，而应该收敛到 adapter 层

## 0. 总结

UI-TARS2 的关键设计是：

```text
模型侧输出统一 action/function
  -> action parser
  -> structured action
  -> benchmark-specific adapter/operator
  -> benchmark native action

```

因此，benchmark 的原生协议差异不直接进入模型训练协议，而是在 adapter 层处理。

对我们来说，推荐迁移目标不是让模型重新学习 UI-TARS2 的表面语法，而是把 UI-TARS2-compatible action 当作内部 IR：

```text
AL / SFT / RL canonical protocol:
  mouse_move, mouse_hover, click_xy, doubleclick_xy, rightclick_xy,
  type_xy, select_xy, scroll, key, drag, wait,
  go_back, go_forward, navigate, zoom_region, answer, stop

runtime adapter 内部 IR:
  click(point), left_double(point), right_single(point), move/hover(point),
  type(content), scroll(point,direction), hotkey/press,
  drag(start_point,end_point), wait, finished(content)
  + optional SDK functions

benchmark native protocol:
  PyAutoGUI / Playwright-CDP / ADB / point evaluator / shell executor

```

注意：旧 Browser Demo 的 `click(ref)` / `type(ref,text)` 属于 SoM/ref 协议，适合 browser demo 和 Playwright 执行；UI-TARS2 主路线更偏坐标化 GUI action。迁移时应把 `ref` 解析为 bbox center，再转成 `point`。

---

# Part 1. UI-TARS2 如何映射到 Benchmark Action Protocol

## 1.1 UI-TARS2 的模型侧 Action Space

UI-TARS2 继承 UI-TARS 的 GUI action，并扩展 SDK/tool functions。

### GUI Actions

| UI-TARS2 / UI-TARS action | 说明 |
| --- | --- |
| `click(point)` | 点击屏幕点 |
| `left_double(point)` | 左键双击 |
| `right_single(point)` | 右键单击 |
| `drag(start_point,end_point)` | 拖拽 |
| `scroll(point,direction)` | 在指定点附近滚动 |
| `type(content)` | 输入文本 |
| `hotkey(key)` | 快捷键 |
| `press(key)` / `keydown(key)` / `keyup(key)` | 键盘按下/释放 |
| `wait()` | 等待 |
| `finished(content)` | 结束并提交答案或完成状态 |

### SDK / Tool Functions

UI-TARS2 还支持 GUI-SDK 类任务，可用：

```text
terminal command
file management
MCP/tool invocation

```

这些 function 不属于传统 GUI action，主要用于 TerminalBench、SWE-Bench、文件处理、多工具任务。

## 1.2 UI-TARS2 的 Adapter 总链路

```text
model response:
  Thought: ...
  Action: click(point='320 180')

parse_action_to_structure_output:
  {
    "action_type": "click",
    "action_inputs": {"start_box": "[x1,y1,x2,y2]"},
    "thought": "..."
  }

benchmark adapter:
  OSWorldAdapter / BrowserAdapter / AndroidAdapter / GroundingAdapter / SDKAdapter

native action:
  pyautogui / ADB / Playwright-CDP / point evaluator / shell executor

```

## 1.3 坐标映射规则

UI-TARS2 风格的坐标处理可以抽象为：

```text
model point
  -> parser normalized point / box
  -> adapter maps to environment coordinate
  -> native executor

```

推荐统一字段：

```json
{
  "point": [320, 180],
  "coordinate_space": "image_pixel|normalized_0_1|normalized_0_1000|window_pixel",
  "screen_size": [1440, 900]
}

```

如果模型输出的是 bbox，则取中心点：

```text
x = (x1 + x2) / 2
y = (y1 + y2) / 2

```

## 1.4 OSWorld / Desktop Benchmark 映射

OSWorld 原生执行层通常是 PyAutoGUI 或 computer-use action。UI-TARS adapter 将结构化 action 转成 PyAutoGUI。

| UI-TARS2 action | OSWorld native action |
| --- | --- |
| `click(point)` / `left_single(point)` | `pyautogui.click(x, y, button='left')` |
| `left_double(point)` | `pyautogui.doubleClick(x, y, button='left')` |
| `right_single(point)` | `pyautogui.click(x, y, button='right')` |
| `hover(point)` | `pyautogui.moveTo(x, y)` |
| `drag(start_point,end_point)` | `pyautogui.moveTo(sx, sy)` + `pyautogui.dragTo(ex, ey)` |
| `scroll(point,"up")` | `pyautogui.scroll(5, x=x, y=y)` |
| `scroll(point,"down")` | `pyautogui.scroll(-5, x=x, y=y)` |
| `hotkey("ctrl c")` | `pyautogui.hotkey("ctrl", "c")` |
| `press("enter")` | `pyautogui.press("enter")` 或 keyDown/keyUp |
| `type(content)` | clipboard paste 或 `pyautogui.write(content)` |
| `finished()` | `DONE` |

### 示例

```json
{
  "ui_tars_action": {
    "name": "click",
    "args": {"point": [320, 180]}
  },
  "native_action": "pyautogui.click(320, 180, button='left')"
}

```

## 1.5 Browser / Web Benchmark 映射

Browser benchmark 的原生协议可能是坐标点击、DOM element/ref、Playwright/CDP API 或 answer-only。UI-TARS2 风格优先保留视觉坐标 action，再由 browser adapter 执行。

| UI-TARS2 action | Browser native action |
| --- | --- |
| `click(point)` | `page.mouse.click(x, y)` 或 CDP `Input.dispatchMouseEvent` |
| `type(content)` | `page.keyboard.type(content)` / `Input.insertText` / fill active element |
| `scroll(point,direction)` | `page.mouse.wheel(dx, dy)` |
| `hotkey(key)` | `page.keyboard.press(...)` |
| `drag(start_point,end_point)` | mouse move/down/move/up |
| `wait()` | `wait_for_load_state` / sleep |
| `finished(content)` | `answer(content)` / submit final answer |

如果 benchmark 原生要求 DOM/ref：

```text
point
  -> viewport coordinate
  -> document.elementFromPoint(x,y)
  -> benchmark ref / element id

```

## 1.6 AndroidWorld / Mobile Benchmark 映射

Android benchmark 通常通过 ADB 或 accessibility 执行。

| UI-TARS2 action | Android native action |
| --- | --- |
| `click(point)` | `adb shell input tap x y` |
| `drag(start_point,end_point)` | `adb shell input swipe sx sy ex ey duration` |
| `scroll(point,direction)` | swipe up/down |
| `type(content)` | ADB text input / clipboard input |
| `press_back()` | Android BACK keyevent |
| `press_home()` | Android HOME keyevent |
| `press_enter()` | Android ENTER keyevent |
| `finished(content)` | final answer / done |

## 1.7 Grounding Benchmark 映射

ScreenSpot、ScreenSpot-Pro、OSWorld-G、MMBench-GUI-L2 这类 benchmark 不需要执行多步环境动作。

```text
UI-TARS2 action:
  click(point)

benchmark native output:
  point(x,y)

verifier:
  point inside target bbox

```

| UI-TARS2 action | Grounding native output |
| --- | --- |
| `click(point)` | `point(x,y)` |
| `finished()` | 不需要 |
| `type/scroll/drag` | 不适用 |

## 1.8 Terminal / SWE / SDK Benchmark 映射

TerminalBench、SWE-Bench 等不应使用 GUI action。

| UI-TARS2 SDK function | Native execution |
| --- | --- |
| `terminal(command)` | sandbox shell |
| `read_file(path)` | filesystem read |
| `write_file(path, content)` | filesystem write |
| `edit_file(path, patch)` | patch/edit API |
| `tool_call(name,args)` | MCP/tool executor |

## 1.9 Answer-only Benchmark 映射

MMMU 等静态 QA benchmark 不使用 GUI action。

```text
finished(content) / answer(content)
  -> normalized answer
  -> exact match / multiple choice / judge

```
---

# Part 2. 从我们预训练 Action Protocol 映射到 UI-TARS2 Protocol

## 2.1 我们当前有两类协议来源

### A. 旧 Browser Demo / Midtrain 共用协议

旧 Browser Demo 协议偏 SoM/ref：

```text
click(ref)
type(ref,text)
select(ref,option)
click_xy(x,y)
key(name)
drag(x1,y1,x2,y2)
scroll(dir,amount)
wait()
go_back()
go_forward()
navigate(url)
zoom_to(ref)
zoom_region(x,y,w,h)
answer(text)
stop()

```

特点：

*   browser 里主用 `ref`，即 SoM 编号。
    
*   `click_xy` 只是兜底。
    
*   对 Playwright/CDP 执行友好。
    
*   与 UI-TARS2 的纯坐标主路线不完全一致。
    

### B. 最新 Browser Demo / SFT 标注协议

最新 Browser Demo 数据格式标注规范偏坐标工具调用，并要求 action 写在 `<|tool_call>` 与 `<tool_call|>` 之间：

```text
mouse_move
mouse_hover
click_xy
doubleclick_xy
rightclick_xy
type_xy
select_xy
scroll
key
drag
wait
go_back
go_forward
navigate
zoom_region
answer
stop

```

特点：

*   更接近 UI-TARS2 的坐标化 GUI action。
    
*   `w_t` 中可以内联 `<|tool_call>type_xy(...)`。
    
*   `parsed_action` 已经是结构化动作。
    
*   `zoom_region` 的最新语义不是裁剪/放大，而是在同尺寸完整截图上画框；后续坐标仍相对完整截图。
    

## 2.2 迁移目标协议

建议定义中间层 `UITARS2CompatAction`：

```json
{
  "name": "click|type|scroll|hotkey|press|drag|wait|finished|sdk_call",
  "args": {},
  "coordinate_space": "image_pixel|normalized_0_1|normalized_0_1000|window_pixel",
  "screen_size": [1440, 900],
  "source_action": {},
  "migration_status": "ok|needs_ref_resolution|unsupported|lossy"
}

```

## 2.3 坐标类动作映射

| 我们的 action | UI-TARS2-compatible action | 规则 |
| --- | --- | --- |
| `mouse_move(x,y)` | `move(point=(x,y))` 或 `hover(point=(x,y))` | adapter 可转 PyAutoGUI moveTo / browser mouse.move |
| `mouse_hover(x,y)` | `hover(point=(x,y))` | adapter 可转 moveTo / mouse.move |
| `click_xy(x,y)` | `click(point=(x,y))` | 直接映射 |
| `doubleclick_xy(x,y)` | `left_double(point=(x,y))` | 直接映射 |
| `rightclick_xy(x,y)` | `right_single(point=(x,y))` | 直接映射 |
| `type_xy(x,y,text)` | `click(point=(x,y))` + `type(content=text)` | UI-TARS2 的 `type` 通常不带点；先点击输入框再输入 |
| `select_xy(x,y,option)` | `click(point=(x,y))` + `type/press` 或 browser select adapter | UI-TARS2 无标准 select，需 adapter |
| `drag(x1,y1,x2,y2)` | `drag(start_point=(x1,y1), end_point=(x2,y2))` | 直接映射 |
| `zoom_region(x,y,w,h)` | `click/drag` 不等价；保留为 observation adapter 或 unsupported | UI-TARS2 标准 action 不含观察式 zoom；最新规范要求返回同尺寸带框截图 |

### `type_xy` 推荐展开

```json
{
  "source_action": {"name": "type_xy", "args": {"x": 320, "y": 120, "text": "refund"}},
  "ui_tars2_actions": [
    {"name": "click", "args": {"point": [320, 120]}},
    {"name": "type", "args": {"content": "refund"}}
  ]
}

```

## 2.4 Ref / SoM 类动作映射

旧协议的 `ref` 不能直接喂给 UI-TARS2，需要先解析成坐标。

```text
ref
  -> SoM snapshot / bbox table
  -> bbox
  -> center point
  -> UI-TARS2 click(point)

```

| 我们的 action | UI-TARS2-compatible action | 需要的数据 |
| --- | --- | --- |
| `click(ref)` | `click(point=center(bbox(ref)))` | `som_snapshot` / `bbox_table` |
| `type(ref,text)` | `click(point=center(bbox(ref)))` + `type(content=text)` | `bbox_table` |
| `select(ref,option)` | `click(point=center(bbox(ref)))` + adapter select/type/press | `bbox_table` + element role |
| `zoom_to(ref)` | observation crop around `bbox(ref)` | `bbox_table` |

### 示例

```json
{
  "source_action": {"name": "click", "args": {"ref": 12}},
  "ref_resolution": {
    "ref": 12,
    "bbox": [100, 200, 180, 240],
    "center": [140, 220]
  },
  "ui_tars2_action": {
    "name": "click",
    "args": {"point": [140, 220]}
  }
}

```

如果 `ref` 找不到 bbox：

```text
migration_status = "needs_ref_resolution" 或 "unsupported"
样本不能进入 UI-TARS2-compatible SFT/RL 主训练

```

## 2.5 Keyboard / Scroll / Navigation 映射

| 我们的 action | UI-TARS2-compatible action | 规则 |
| --- | --- | --- |
| `key(name)` | `hotkey(key=name)` 或 `press(key=name)` | 单键用 `press`，组合键用 `hotkey` |
| `scroll(dir,amount)` | `scroll(point=current_or_center, direction=dir)` | 无 point 时默认 viewport center |
| `wait()` | `wait()` | 直接映射 |
| `go_back()` | `hotkey("alt left")` 或 browser adapter `go_back` | UI-TARS2 标准 GUI action 无 go\_back，需要 adapter |
| `go_forward()` | `hotkey("alt right")` 或 browser adapter `go_forward` | 同上 |
| `navigate(url)` | browser adapter `navigate` 或 SDK/browser tool | UI-TARS2 标准 GUI action 无 direct navigate |

建议：

*   `go_back/go_forward/navigate` 不作为 UI-TARS2 GUI core action。
    
*   Browser benchmark 需要时放在 BrowserAdapter 的 native function。
    
*   如果要保留到模型侧，标记为 `browser_function`，不要混进通用 desktop/mobile action。
    

## 2.6 Answer / Stop 映射

| 我们的 action | UI-TARS2-compatible action | 规则 |
| --- | --- | --- |
| `answer(text)` | `finished(content=text)` | 终止并提交答案 |
| `stop()` | `finished(content="")` 或 `call_user/abort` | 按任务定义为失败/放弃/无答案 |

推荐统一：

```text
answer(text) -> finished(content=text, status="success_candidate")
stop()       -> finished(content="", status="abort")

```

## 2.7 Macro Action 映射

旧 SFT / 完整方案中可能出现：

```text
search_in_page(query)
search(query)
EOS

```

迁移规则：

| Macro | UI-TARS2-compatible 展开 | 是否进入在线 RL |
| --- | --- | --- |
| `search_in_page(query)` | `hotkey("ctrl f")` + `type(content=query)` + optional `press("enter")` | 否 |
| `search(query)` | browser-specific search box click + `type`，或网页任务重写 | 否 |
| `EOS` | `finished(content="")` | 是 |

原则：

*   macro 只能用于离线 replay / 数据迁移 / teacher trace 解释。
    
*   在线 RL policy 不暴露 task-level macro。
    
*   如果 macro 无法稳定展开，样本标记 `unsupported_action`。
    

## 2.8 Zoom / Active Perception 映射

我们的 `zoom_region` / `zoom_to` 是 Active Lifting 的主动观察动作，但 UI-TARS2 标准 GUI action 里没有完全等价项。

推荐处理：

```text
zoom_to(ref)
  -> resolve ref bbox
  -> create cropped high-res observation
  -> action_type = observation_transform

zoom_region(x,y,w,h)
  -> draw box on the same-size full screenshot
  -> action_type = observation_transform

```

也就是说，`zoom_*` 不应强行映射成 click/drag。它更像 observation adapter：

```json
{
  "name": "zoom_region",
  "migration_target": "observation_transform",
  "ui_tars2_core_action": null,
  "status": "lossy"
}

```

如果目标 benchmark 没有 active observation API，则：

```text
训练 SFT 可保留 zoom trace；
在线 RL benchmark adapter 中禁用 zoom；
或把 zoom 后 observation 预先展开为下一帧截图。

```

## 2.9 SDK / Tool Action 映射

如果我们的预训练协议未来加入工具：

| 我们的 action | UI-TARS2-compatible function |
| --- | --- |
| `terminal(command)` | `terminal(command)` |
| `read_file(path)` | `read_file(path)` |
| `write_file(path,content)` | `write_file(path,content)` |
| `edit_file(path,patch)` | `edit_file(path,patch)` |
| `tool_call(name,args)` | `tool_call(name,args)` |

这些 function 应与 GUI action 分命名空间：

```text
gui.click(...)
sdk.terminal(...)
sdk.read_file(...)

```

## 2.10 完整迁移表

| 我们的 action | UI-TARS2-compatible action/function | 迁移状态 | 备注 |
| --- | --- | --- | --- |
| `mouse_move(x,y)` | `move(point=(x,y))` / `hover(point=(x,y))` | ok | adapter 转 mouse move |
| `mouse_hover(x,y)` | `hover(point=(x,y))` | ok | adapter 转 hover/moveTo |
| `click_xy(x,y)` | `click(point=(x,y))` | ok | 坐标系必须明确 |
| `doubleclick_xy(x,y)` | `left_double(point=(x,y))` | ok | 坐标系必须明确 |
| `rightclick_xy(x,y)` | `right_single(point=(x,y))` | ok | 坐标系必须明确 |
| `type_xy(x,y,text)` | `click(point=(x,y))` + `type(content=text)` | ok | 两步展开 |
| `select_xy(x,y,option)` | `click(point=(x,y))` + adapter select/type | lossy | 需 element role |
| `scroll(dir,amount)` | `scroll(point=center,direction=dir)` | ok | 默认 viewport center |
| `scroll(x,y,dir)` | `scroll(point=(x,y),direction=dir)` | ok | 直接映射 |
| `key(name)` | `press(key)` / `hotkey(key)` | ok | 组合键用 hotkey |
| `drag(x1,y1,x2,y2)` | `drag(start_point,end_point)` | ok | 直接映射 |
| `wait()` | `wait()` | ok | 直接映射 |
| `answer(text)` | `finished(content=text)` | ok | 终止动作 |
| `stop()` | `finished(content="")` | ok | status 标记 abort |
| `click(ref)` | `click(point=center(bbox(ref)))` | needs\_ref\_resolution | 需要 SoM/bbox |
| `type(ref,text)` | `click(point=center(bbox(ref)))` + `type(content=text)` | needs\_ref\_resolution | 需要 SoM/bbox |
| `select(ref,option)` | `click(point=center(bbox(ref)))` + adapter select/type | lossy | 需要 role/options |
| `zoom_to(ref)` | observation crop around bbox(ref) | lossy | 非 UI-TARS2 core |
| `zoom_region(x,y,w,h)` | observation transform，同尺寸截图画框 | lossy | 非 UI-TARS2 core |
| `go_back()` | browser adapter `go_back` 或 `hotkey("alt left")` | adapter\_specific | 非通用 GUI core |
| `go_forward()` | browser adapter `go_forward` 或 `hotkey("alt right")` | adapter\_specific | 非通用 GUI core |
| `navigate(url)` | browser adapter `navigate` | adapter\_specific | 应限制白名单 |
| `search_in_page(query)` | `hotkey("ctrl f")` + `type(content=query)` | offline\_only | 不进在线 RL |
| `EOS` | `finished(content="")` | ok | 需保留 status |

## 2.11 迁移产物格式

每条 action 迁移后保存：

```json
{
  "source_protocol": "al_browser_demo_v1|al_sft_vlatest|al_pretrain",
  "target_protocol": "ui_tars2_compat_v1",
  "source_action": {
    "name": "type_xy",
    "args": {"x": 320, "y": 120, "text": "refund"}
  },
  "target_actions": [
    {"name": "click", "args": {"point": [320, 120]}},
    {"name": "type", "args": {"content": "refund"}}
  ],
  "coordinate_space": "image_pixel",
  "screen_size": [1440, 900],
  "migration_status": "ok",
  "lossy": false,
  "notes": ""
}

```

Ref action 需要额外保存：

```json
{
  "ref_resolution": {
    "ref": 12,
    "bbox": [100, 200, 180, 240],
    "center": [140, 220],
    "source": "som_snapshot"
  }
}

```

## 2.12 验收标准

迁移数据进入训练或 runtime adapter 前必须满足：

| 指标 | 阈值 |
| --- | --- |
| action parse success | ≥ 99% |
| coordinate space filled | 100% |
| screen size filled | 100% |
| ref resolution success，ref 类样本 | ≥ 98% |
| migrated action executable | ≥ 95% |
| macro 出现在在线 RL action space | 0 |
| unsupported action 占比 | ≤ 2% |
| lossy migration 占比 | 单独统计，不得混入主训练默认权重 |

## 2.13 推荐落地顺序

### 阶段 A：离线迁移与 Adapter 验证

```text
source traces
  -> parse source action
  -> resolve ref / normalize coords
  -> convert to UI-TARS2-compatible action
  -> replay check

```

### 阶段 B：默认不改模型表面协议

默认保留最新 Browser Demo / SFT 的 `<|tool_call>click_xy(...)<tool_call|>` 表面输出，由 host parser 转成 UI-TARS2-compatible IR，再继续转 benchmark native action。历史 `heart_segment + </a>` 只按 legacy 数据迁移处理。

```text
model output:
  <|tool_call>type_xy(320,120,"refund")

host parser:
  {"name":"type_xy","args":{"x":320,"y":120,"text":"refund"}}

IR:
  click(point=(320,120)) + type(content="refund")

```

不建议为了对齐 UI-TARS2 语法而额外微调模型，除非后续要复用 UI-TARS2 的现成推理服务或开源 agent harness。

### 阶段 C：可选 SFT Warm-up

只有在需要模型直接输出 UI-TARS2 grammar 时，才用迁移成功样本训练：

```text
Thought: ...
Action: click(point='x y')

```

### 阶段 D：RL Adapter 接入

按 benchmark 接：

```text
OSWorld        -> PyAutoGUI adapter
Browser/Web    -> Playwright/CDP adapter
AndroidWorld   -> ADB adapter
Grounding      -> point evaluator
Terminal/SWE   -> SDK adapter
Answer-only    -> answer evaluator

```

### 阶段 E：协议收敛

如果后续目标是最大程度复用 UI-TARS2 路线，建议逐步减少 `ref` 主路线，增加坐标 action 数据比例：

```text
click(ref) / type(ref,text)
  -> click_xy / type_xy
  -> click(point) / type(content)

```

但 Browser demo 可以继续保留 `ref`，因为它对 Playwright 执行稳定、低熵、易调试。

---

# Part 3. 直接复合映射：从我们的方法到 Benchmark Native Action

## 3.1 是否需要让模型对齐 UI-TARS2 表面协议？

不需要作为默认路径。

更推荐的落地方式是：

```text
我们的模型输出协议
  -> ALActionParser
  -> AL canonical structured action
  -> UITARS2CompatIR
  -> BenchmarkAdapter
  -> benchmark native action

```

UI-TARS2-compatible action 在这里只是中间 IR，不是模型必须学习的新输出语言。

这样做的收益：

*   不需要额外微调模型去学 `Action: click(point='...')` 语法。
    
*   可以继续复用我们 SFT / pretrain 已经学到的 `<|tool_call>click_xy(...)<tool_call|>` 分布；历史 `heart_segment + </a>` 数据只在离线迁移时解析。
    
*   benchmark 适配集中在 runtime adapter，调试和回滚更容易。
    
*   同一条模型输出可以按 benchmark 目标映射到 PyAutoGUI、Playwright、ADB、grounding point 或 answer evaluator。
    

## 3.2 复合映射公式

定义两个映射：

```text
F: 我们的 action -> UI-TARS2-compatible IR
G_b: UI-TARS2-compatible IR -> benchmark b native action

```

则直接映射为：

```text
H_b = G_b ∘ F

我们的 action -> benchmark b native action

```

工程上：

```python
al_action = parse_al_action(model_output, observation, history)
ir_actions = to_uitars2_ir(al_action, observation)
native_actions = benchmark_adapter.to_native(ir_actions, observation)
result = benchmark_env.execute(native_actions)

```

## 3.3 Runtime Adapter 架构

```text
Model
  outputs: <|tool_call>...<tool_call|>

ALActionParser
  parses to ALAction

ActionNormalizer
  normalizes name/args/coordinate/ref/macro

UITARS2CompatIRConverter
  converts ALAction to one or more IR actions

BenchmarkAdapter
  converts IR actions to native benchmark action

Verifier
  scores final state / answer / trajectory

```

推荐接口：

```python
class ALActionParser:
    def parse(self, model_output, observation, history) -> list[ALAction]:
        ...

class UITARS2CompatIRConverter:
    def convert(self, action: ALAction, observation) -> list[IRAction]:
        ...

class BenchmarkAdapter:
    def to_native(self, actions: list[IRAction], observation) -> list[NativeAction]:
        ...

```

## 3.4 直接映射表：我们的方法 -> OSWorld

| 我们的 action | 中间 IR | OSWorld native action |
| --- | --- | --- |
| `mouse_move(x,y)` / `mouse_hover(x,y)` | `move/hover(point=(x,y))` | `pyautogui.moveTo(x,y)` |
| `click_xy(x,y)` | `click(point=(x,y))` | `pyautogui.click(x,y)` |
| `doubleclick_xy(x,y)` | `left_double(point=(x,y))` | `pyautogui.doubleClick(x,y)` |
| `rightclick_xy(x,y)` | `right_single(point=(x,y))` | `pyautogui.click(x,y,button="right")` |
| `type_xy(x,y,text)` | `click(point=(x,y))` + `type(content=text)` | `pyautogui.click(x,y)` + clipboard paste |
| `key("ctrl c")` | `hotkey("ctrl c")` | `pyautogui.hotkey("ctrl","c")` |
| `scroll(x,y,"down")` | `scroll(point=(x,y),direction="down")` | `pyautogui.scroll(-5,x=x,y=y)` |
| `drag(x1,y1,x2,y2)` | `drag(start,end)` | `moveTo(x1,y1)` + `dragTo(x2,y2)` |
| `wait()` | `wait()` | `time.sleep(...)` |
| `answer(text)` | `finished(content=text)` | `DONE` + answer stored for verifier |
| `stop()` | `finished(status="abort")` | `DONE` / `FAIL` by policy |

## 3.5 直接映射表：我们的方法 -> Browser / Web

| 我们的 action | 中间 IR | Browser native action |
| --- | --- | --- |
| `mouse_move(x,y)` / `mouse_hover(x,y)` | `move/hover(point=(x,y))` | `page.mouse.move(x,y)` |
| `click_xy(x,y)` | `click(point=(x,y))` | `page.mouse.click(x,y)` / CDP mouse event |
| `doubleclick_xy(x,y)` | `left_double(point=(x,y))` | `page.mouse.dblclick(x,y)` |
| `rightclick_xy(x,y)` | `right_single(point=(x,y))` | `page.mouse.click(x,y, button="right")` |
| `click(ref)` | `click(point=center(bbox(ref)))` | `page.mouse.click(cx,cy)` or `page.click(selector)` |
| `type_xy(x,y,text)` | `click(point=(x,y))` + `type(content=text)` | click + `Input.insertText` / keyboard type |
| `type(ref,text)` | `click(point=center(bbox(ref)))` + `type(content=text)` | `page.fill(selector,text)` if selector exists; otherwise click + type |
| `select(ref,option)` | adapter-specific select | `page.select_option(selector,option)` |
| `scroll(dir,amount)` | `scroll(point=center,direction=dir)` | `page.mouse.wheel(dx,dy)` |
| `key(name)` | `press/hotkey` | `page.keyboard.press(name)` |
| `go_back()` | browser function | `page.go_back()` |
| `go_forward()` | browser function | `page.go_forward()` |
| `navigate(url)` | browser function | `page.goto(url)` with whitelist |
| `answer(text)` | `finished(content=text)` | submit answer to evaluator |

这里 BrowserAdapter 可以选择两种执行路径：

```text
ref-preserving path:
  click(ref) -> page.click(selector)

coordinate path:
  click(ref) -> bbox center -> page.mouse.click(cx,cy)

```

Browser demo 优先用 ref-preserving path，因为 Playwright auto-wait 更稳定；对 benchmark 若只接受坐标，则走 coordinate path。

## 3.6 直接映射表：我们的方法 -> Grounding Benchmarks

适用：OSWorld-G、ScreenSpot-Pro、MMBench-GUI-L2。

| 我们的 action / 数据 | 中间 IR | Benchmark output |
| --- | --- | --- |
| `click_xy(x,y)` | `click(point=(x,y))` | `point(x,y)` |
| `click(ref)` | `click(point=center(bbox(ref)))` | `point(cx,cy)` |
| `type_xy(...)` | 不适用，取点击点或过滤 | 通常不进入 grounding |
| `zoom_region(...)` | observation transform | 不作为最终 action |

Grounding 只需要输出点，因此可以直接短路：

```text
AL action -> point -> bbox hit verifier

```

不需要真的生成 UI-TARS2 表面 `click(point=...)` 文本。

## 3.7 直接映射表：我们的方法 -> AndroidWorld

| 我们的 action | 中间 IR | Android native action |
| --- | --- | --- |
| `click_xy(x,y)` | `click(point=(x,y))` | `adb shell input tap x y` |
| `doubleclick_xy(x,y)` | `left_double(point=(x,y))` | 两次 `adb shell input tap x y`，间隔短延迟 |
| `rightclick_xy(x,y)` | `right_single(point=(x,y))` | 通常无等价，标记 unsupported 或映射 long press |
| `type_xy(x,y,text)` | `click(point=(x,y))` + `type(content=text)` | tap + text input |
| `scroll(x,y,"down")` | `scroll(point=(x,y),direction="down")` | swipe up |
| `scroll(x,y,"up")` | `scroll(point=(x,y),direction="up")` | swipe down |
| `drag(x1,y1,x2,y2)` | `drag(start,end)` | `adb shell input swipe x1 y1 x2 y2 duration` |
| `key("back")` | `press_back()` | Android BACK keyevent |
| `key("home")` | `press_home()` | Android HOME keyevent |
| `answer(text)` | `finished(content=text)` | final answer / done |

## 3.8 直接映射表：我们的方法 -> Terminal / SWE / SDK

如果我们的模型输出 GUI action，则不能直接用于 TerminalBench/SWE-Bench；必须是 SDK/tool action。

| 我们的 action | 中间 IR | Native action |
| --- | --- | --- |
| `terminal(command)` | `terminal(command)` | shell command |
| `read_file(path)` | `read_file(path)` | filesystem read |
| `write_file(path,content)` | `write_file(path,content)` | filesystem write |
| `edit_file(path,patch)` | `edit_file(path,patch)` | apply patch |
| `tool_call(name,args)` | `tool_call(name,args)` | MCP/tool executor |

如果当前预训练协议没有 SDK action，则这类 benchmark 不能只靠 adapter 解决，需要补数据或补工具输出能力。

## 3.9 直接映射表：我们的方法 -> Answer-only Benchmark

适用：MMMU、静态 VQA/QA。

| 我们的 action | Benchmark native output |
| --- | --- |
| `answer(text)` | normalized answer |
| `stop()` | no answer / abort |
| GUI actions | 不适用 |

answer-only benchmark 不需要 UI-TARS2 GUI action IR。

## 3.10 `zoom_region` 的直接处理

`zoom_region` / `zoom_to` 不建议映射到 benchmark native action，除非 benchmark 环境本身支持主动观察。

推荐作为 observation transform：

```text
zoom_region(x,y,w,h)
  -> draw a rectangle on the same-size full screenshot
  -> keep all following coordinates relative to the full screenshot
  -> next model step

```

对不支持主动观察的 benchmark：

```text
SFT/replay: 可以保留
online RL benchmark: 禁用或预展开
grounding eval: 不作为最终预测

```

## 3.11 什么时候还需要微调对齐 UI-TARS2？

只有以下情况才需要：

1.  要直接复用 UI-TARS2 官方 agent harness，且 harness 只接受 `Thought: ... Action: click(point=...)`。
    
2.  要混入大量 UI-TARS2 原生格式数据，且不想在 dataloader 做格式转换。
    
3.  要对外发布兼容 UI-TARS2 prompt 的模型。
    

否则默认不做。我们只需要训练/维护：

```text
ALActionParser + ActionNormalizer + BenchmarkAdapter

```

## 3.12 第三部分验收标准

| 指标 | 阈值 |
| --- | --- |
| model output -> ALAction parse success | ≥ 99% |
| ALAction -> IR conversion success | ≥ 99% |
| IR -> benchmark native conversion success | ≥ 98% |
| native action execution success，replay | ≥ 95% |
| 坐标越界率 | ≤ 0.5% |
| ref resolution success | ≥ 98% |
| macro 泄漏到 online RL native action | 0 |
| benchmark verifier 可调用率 | 100% |

核心验收不是“模型会不会输出 UI-TARS2 语法”，而是：

```text
我们的模型输出能否被稳定解析、转换、执行、验证。

```