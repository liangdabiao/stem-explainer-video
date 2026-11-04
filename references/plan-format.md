# plan.json 字段说明

plan.json 是整条流水线的**唯一数据源**。所有脚本都只读它。

---

## 顶层结构

```json
{
  "meta": { ... },
  "shots": [ ... ]
}
```

---

## meta

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `title` | string | `"未命名科普片"` | 片名 |
| `lang` | string | `"zh"` | 语言 |
| `width` | int | `720` | 合成画幅宽 |
| `height` | int | `1280` | 合成画幅高 |
| `fps` | int | `30` | 合成帧率 |
| `ratio` | string | `"9:16"` | 底图与视频的画幅比例 |
| `resolution` | string | `"480p"` | 视频分辨率档位：`480p`/`768P`/`1080p`/`2K` |
| `image_model` | string | `"openai/gpt-image-2"` | 底图模型 |
| `video_model` | string | `"minimax/h3"` | 视频模型 |
| `voice` | string | `"female-shaonv"` | 配音音色 |
| `tts_model` | string | `"speech-2.8-hd"` | 配音模型 |
| `tts_speed` | float | `1.0` | 语速，科普建议 1.05~1.15 |
| `theme` | object | 见下 | 配色 |

### theme

```json
{
  "bg": "#FFFFFF",
  "ink": "#171714",
  "accent": "#2563eb",
  "warn": "#ef4444",
  "muted": "#6b7280"
}
```

| 字段 | 用在哪 |
|---|---|
| `bg` | 画面底色（应与底图背景一致） |
| `ink` | 字幕文字色 |
| `accent` | 术语卡主色、字幕左边条、标注框边框 |
| `warn` | 需要强调/警示的标注 |
| `muted` | 次要文字 |

> `bg` 必须和底图的背景**一致**，否则叠字幕时会有色差边缘。

---

## shots[]

每一拍一个对象。

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `id` | ✅ | string | 拍号，唯一。建议 `s01`、`s02`… |
| `duration_sec` | ✅ | number | 本拍时长（**秒**）。4~15 |
| `narration` | ✅ | string | 旁白逐字稿。**≤ 50 字**，建议 25~40 字 |
| `caption` | | string | 屏幕字幕。省略则用 `narration` |
| `term` | | string | 术语卡大字（如「阀门」） |
| `term_def` | | string | 术语释义（如「控制通断的开关」） |
| `motion` | | object | **动效配置（决定这一拍花不花钱）** |
| `annotations` | | array | 画面标注层 |
| `takeaway` | | string | 本拍一句话要点（结尾回顾用） |
| `diagram` | | object | 底图配置 |
| `animation` | | object | 动画配置（**仅 `motion.type='ai'` 时需要**） |

### ★ motion（成本控制的核心）

```json
"motion": {
  "type": "still",
  "zoomTo": {"x": 500, "y": 220, "scale": 1.25},
  "highlight": {
    "x": 500, "y": 220, "w": 190, "h": 130,
    "label": "阀门手轮", "delay": 1.2, "duration": 4.5,
    "color": "#ef4444"
  }
}
```

| 字段 | 说明 |
|---|---|
| `type` | `still`（静态底图+代码动效，0 积分）/ `ai`（AI 视频，79 积分）/ `precise`（代码精确动画，0 积分） |
| `zoomTo` | `still` 层：推镜目标点（千分比）与倍数 |
| `highlight` | `still` 层：高亮框 |

**默认是 `still`**（不写 `motion` 就按 `still` 处理）。
只有「运动本身就是知识点」的拍才写 `type: "ai"`。

> ⚠️ 校验规则：`motion.type='still'` 却写了 `animation.prompt` → **报错**。
> 因为那段提示词永远不会被用到，属于纯浪费。

> ⚠️ `motion.type='ai'` 却没写 `animation.prompt` → **报错**。

### diagram

```json
{
  "prompt": "9 段式底图提示词",
  "model": "openai/gpt-image-2",
  "ratio": "9:16",
  "params": { }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `prompt` | ✅ | 底图提示词。格式见 `references/diagram-rules.md` |
| `model` | | 覆盖 `meta.image_model` |
| `ratio` | | 覆盖 `meta.ratio` |
| `params` | | 额外参数，JSON 合并进请求 |

> **不用 AI 出图时**：整个 `diagram` 字段省略，
> 手工把 PNG 放到 `assets/diagrams/<id>.png`，
> 并在 `assets/diagrams/urls.json` 里写入 `{"<id>": "公网URL"}`。
> 动画步骤照样能跑。

### animation（仅 `motion.type='ai'`）

```json
{
  "prompt": "什么在动、什么必须不动",
  "duration": 7
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `prompt` | ✅ | 动画提示词。三句结构，见 `references/teaching-script.md` |
| `duration` | | 视频时长。**必须与 `duration_sec` 一致**，否则音画错位 |

### annotations

画面上的确定性文字标注（由 Remotion 渲染，不是 AI 画的）。

```json
[
  {"text": "手轮", "x": 500, "y": 220, "color": "#ef4444", "delay": 1.5}
]
```

| 字段 | 说明 |
|---|---|
| `text` | 标注文字 |
| `x` | 横向位置，**千分比**（0~1000，左=0 右=1000） |
| `y` | 纵向位置，**千分比**（0~1000，上=0 下=1000） |
| `color` | 边框与文字色，默认用 `theme.accent` |
| `delay` | 出现延迟（秒），用来配合旁白节奏 |

> 用千分比而不是像素，换画幅（9:16 ↔ 16:9）也不会错位。

---

## 校验规则

`plan_schema.py` 会检查：

1. 顶层有 `meta` 和 `shots`，`shots` 非空
2. 每拍有 `id`（不重复）、`narration`、`duration_sec`
3. `duration_sec` 在 4~15 之间
4. **`motion.type` 合法**（`still` / `ai` / `precise`）
5. **`motion.type='still'` 却有 `animation.prompt`** → 报错（这段提示词浪费了）
6. **`motion.type='ai'` 却没 `animation.prompt`** → 报错
7. `motion.type='ai'` 时，`animation.duration` 与 `duration_sec` 一致
8. `still` / `precise` 层必须有 `diagram.prompt`

手动校验：

```bash
python scripts/plan_schema.py plan.json
```

输出 `[OK] plan.json: N 拍，预计时长 X.Xs` 即通过。

---

## 时长对齐（重要）

AI 视频的时长受 h3 限制（4~15 秒整数），而**旁白长度由内容决定**。
两者很容易打架 —— 典型症状是「话没说完画面就切走」。

`fit_duration.py` 自动处理：视频比旁白短时循环补齐，产物在
`assets/videos/fitted/`。`build_storyboard.py` 会自动优先使用它。

```bash
python scripts/fit_duration.py plan.json
```

> 静态层（`still`）不需要这一步 —— 画面本身就是静态的，
> 时序完全由 Remotion 控制，天然与旁白对齐。

---

## 完整示例

`examples/pipe-valve/plan.json` —— 一集 3 拍的完整科普片，
**其中只有 1 拍用 AI 视频**（水流流动），另 2 拍用静态底图 + 高亮框。
可直接复制改写。
