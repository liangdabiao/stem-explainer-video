---
name: stem-explainer-video
description: STEM 科普视频生成 skill。面向科学、技术、工程、数学主题的讲解视频：先用 AI 生成结构严格的中文示意图，再用 MiniMax H3 以该图为首帧驱动动画，最后由 Remotion 确定性叠加字幕、术语卡与标注，输出竖屏或横屏成片。触发词：科普视频、讲解视频、示意图动画、知识讲解视频、STEM explainer、teaching video、科普短片、原理动画。
---

# stem-explainer-video

生成**结构严格**的 STEM 科普视频。

核心思路是**四层解耦**：每层只干自己擅长的事，互不越界。

```
第 1 层  底图（严格）  AI 生图模型     → 结构对不对、中文标签准不准
第 2 层  动画（保真）  MiniMax H3      → 什么在动（以底图为首帧驱动）
第 3 层  文字（确定）  Remotion 代码   → 字幕、术语卡、标注（永不交给 AI）
第 4 层  旁白          apiz speak      → 配音
```

**为什么要这样分**：AI 擅长「画得像」，不擅长「算得准」和「改得小」。
把「画」「动」「写」「说」拆开之后，每一层都能做到自己那一层该有的确定性。

---

## ★★ 成本控制：动效分层（**动手前必读**）

**AI 视频只在「运动本身就是知识点」时才必要。** 这是本 skill 最重要的机制。

| 层 | `motion.type` | 手段 | 成本 | 用在什么镜头 |
|---|---|---|---|---|
| 静止层 | `still` | 静态底图 + 代码动效（推镜/高亮/标注） | **0** | 结构图、剖面图、流程图、对比图 |
| 精确层 | `precise` | 代码渲染的确定性动画 | **0** | AI 做不了的精确状态变更 |
| AI 层 | `ai` | minimax/h3 首帧驱动 | **79 积分/段** | **只有**运动本身是知识点时 |

**科普片里 AI 视频的合理占比：15%~30%。超过 50% 基本在浪费钱。**

写 plan 时的判断：

1. 换成静态图 + 高亮框，观众还懂吗？→ 懂就用 `still`
2. 这个运动本身是知识点吗？（流体流动 / 阀门开启 / 分子振动 / 相变 / 爆炸展开）
   → 是才用 `ai`
3. 这个运动有精确起止状态吗？→ 有就用 `precise`

**花钱前先算账**：

```bash
python scripts/estimate_cost.py plan.json
```

会输出总成本，并与「每拍都用 AI 视频」做对比。AI 占比过高会明确警告。

流程上的强制卡点：

- `gen_animations.py` **只处理** `motion.type == 'ai'` 的拍，其余直接跳过
- `plan_schema.py` 校验：`still` 却写了 `animation.prompt` → 报错（浪费）
- `build_storyboard.py` 打印实际动效分布与成本

> **实战教训**：本 skill 早期版本把「每拍都出 AI 视频」写死了，
> 跑一个 3 拍测试就烧掉 91 积分，其中 **73% 花在「静态图就够」的镜头上**。

完整说明见 `references/motion-layers.md`。

### ★ 还有第四种形态：**整段代码场景**（`custom`）

上面三层解决的是「一拍的动效」。当一个主题需要**连续、严格按相位同步**的复杂运动时
（心动周期、振荡、相位耦合），既不该用静态图 + 高亮，也不该用 AI 视频 ——
AI 做不出「严格按相位对齐、每帧几何都正确」。

正确做法是**直接写一个 Remotion 组件**，用 SVG + `useCurrentFrame()` 把整个场景画出来。
零积分、可无限次调参、几何永远正确。

样片 `examples/heart/`：**心脏的复杂工作原理**，12.25 秒，**0 积分**
（没生图、没 AI 视频，只有 edge-tts 配音）。包含四腔按心动周期搏动、
四个瓣膜按相位严格互斥开合、红蓝双回路血流（射血期走动脉、舒张期走静脉）、
同步滚动的 ECG、实时相位标签与瓣膜状态面板。

---

## 何时使用

- 要做**科普/讲解类视频**：讲一个科学原理、一个工程机制、一个数学概念
- 画面需要**准确的结构**（剖面图、流程图、信号通路、机械结构）
- 需要**中文标签**准确（AI 生图现在可以做到，但要显式点名）
- 要**图 + 动画 + 字幕 + 旁白**合成成片

**不适用**：

- 真实实验数据图（散点/柱状/折线）→ 用 matplotlib/Origin，不要用 AI
- 纯文字/PPT 翻页视频 → 用通用办公 skill
- 照片级写实、创意插画 → 用通用生图 skill
- 故事类手绘动画 → 用 `story-handdrawn-video` skill

---

## 前置条件

| 依赖 | 说明 | 检查 |
|---|---|---|
| `apiz` CLI | 已安装并已登录 | `apiz auth status` |
| Python 3.10+ | 标准库即可，无需 pip 装包 | `python --version` |
| `ffmpeg` / `ffprobe` | 合成与质检 | `ffmpeg -version` |
| `node` ≥ 20 + npm | Remotion 渲染 | `node -v` |
| Chrome | Remotion 渲染内核 | 自动探测常见安装路径 |

自检一条命令跑完：

```bash
python scripts/lib_apiz.py
```

---

## 五步工作流

### 第 0 步：写讲稿（**最重要的产出**）

**先稿后片**。讲稿不清，图再好也没用。

读 `references/teaching-script.md`，按「四问结构」（是什么 / 怎么实现 /
为什么 / 值得学吗）组织，逐拍写成表格，标好每一拍讲什么、画面长什么样、
什么在动。

### 第 1 步：写 plan.json

plan.json 是整条流水线唯一的数据源。字段说明见
`references/plan-format.md`，完整可跑的例子见
`examples/pipe-valve/plan.json`。

最小结构：

```json
{
  "meta": {"title": "...", "ratio": "9:16", "resolution": "480p"},
  "shots": [
    {
      "id": "s01",
      "duration_sec": 7,
      "narration": "旁白逐字稿",
      "caption": "屏幕字幕",
      "term": "术语",
      "term_def": "术语释义",
      "diagram":   {"prompt": "9 段式底图提示词"},
      "animation": {"prompt": "什么在动、什么不动", "duration": 7}
    }
  ]
}
```

### 第 2 步：写底图提示词

读 `references/diagram-rules.md`（9 段结构 + 10 条铁律 + 中文标签规范）。

三条最容易翻车的：

1. **逐个点名中文标签** —— `bold black Chinese labels: 管道, 水流, 阀门`
   不点名，模型会自己发明标签
2. **竖屏会改朝向** —— 横管写成 `the pipe is HORIZONTAL running left to right`
3. **底部留白** —— `generous empty margin at the bottom for subtitles`

多拍之间**严格复用 Style / Color / Background 三段**，避免风格漂移。

### 第 3 步：跑流水线

```bash
python scripts/run_episode.py plan.json
```

或者分步跑（便于单步调试）：

```bash
python scripts/gen_diagrams.py   plan.json   # 第1层 底图
python scripts/gen_animations.py plan.json   # 第2层 动画
python scripts/gen_narration.py  plan.json   # 第3层 配音
python scripts/build_storyboard.py plan.json # 第4层 组装
python scripts/render_episode.py plan.json   # Remotion 渲染
python scripts/verify_media.py   plan.json --video out/episode.mp4  # 质检
```

### 第 4 步：质检

`verify_media.py` 会做四件事：

1. 每拍素材齐全
2. **视频时长 ≥ 旁白时长**（否则「话没说完画面就切走」）
3. **音频波形体检** —— 0.5 秒窗 RMS，有声窗占比 > 95%，静音段 < 2 秒
   （⚠️ ffprobe 时长一致、报 PASS 都查不出音轨损坏，只有算 RMS 才发现）
4. 整片音视频时长差 < 0.5 秒

---

## 成本

| 环节 | 单价 | 15 拍 × 6 秒 |
|---|---|---|
| 底图 | 6 积分/张 | 90 |
| 动画 480p | 79 积分/段 | 1185 |
| 配音 | ~1 积分/句 | ~15 |
| **480p 预览合计** | | **≈ 12.9 元** |
| **768P 终稿合计** | | **≈ 17.6 元** |

> 省钱的做法：**先用 480p 跑通全片，再只把视频层用 768P 重跑一遍**，
> 底图和配音复用。

---

## 关键约束（都是实测踩出来的）

| 约束 | 说明 |
|---|---|
| `content` 必须是数组 | h3 走 Chat Completions 风格，传字符串直接报错 |
| 画幅参数名是 `ratio` | 不是 `aspect_ratio`，不给具体值报 `ratio 不能为 adaptive` |
| `resolution` 大小写不一致 | `768P` 是大写 P，写 `768p` 被拒 |
| **首帧必须写在 `content` 里带 `role`** | 写在顶层会被**静默忽略**，首帧渲成纯白 |
| 图片模型用 `--image-size "9:16"` | `--aspect-ratio` 对图片模型不生效 |
| 视频模型不擅长细微状态变更 | 让 AI「把手轮转开」它不会转 → 精确变更用代码 |

完整说明见 `references/api-handbook.md`。

---

## 能力边界（**必读**）

AI 生图是**模式匹配器**，不是几何引擎：

- ✅ 适合：概念示意图、流程图、剖面图、信号通路、教学插图
- ❌ 不适合：**数学严格证明图、坐标图/函数图像、精确构造图、
  精确键长角度的电路图/化学结构式、真实数据图**

→ 后者必须用代码生成底图。把 PNG 放进 `assets/diagrams/<shot_id>.png`，
**后续流程完全不变**。

另一个边界：AI 对**细微机械状态**不敏感。精确的状态变更（阀门开了几度、
水位升到哪）要用代码绘制，不能指望 AI 改图。

---

## 目录结构

```
stem-explainer-video/
├── SKILL.md
├── README.md                    # 通俗易懂的使用说明
├── references/
│   ├── diagram-rules.md         # 底图提示词规范（9段结构+10铁律）
│   ├── api-handbook.md          # apiz / H3 API 手册（含全部踩坑）
│   ├── teaching-script.md       # 科普讲稿规范（问题驱动）
│   ├── plan-format.md           # plan.json 字段说明
│   └── templates/               # 24 个 STEM 场景模板
├── scripts/
│   ├── lib_apiz.py              # apiz 封装（图片/视频/上传/配音）
│   ├── plan_schema.py           # plan 校验
│   ├── gen_diagrams.py          # 第1层 底图
│   ├── gen_animations.py        # 第2层 动画
│   ├── gen_narration.py         # 第3层 配音
│   ├── build_storyboard.py      # 第4层 组装
│   ├── render_episode.py        # Remotion 渲染
│   ├── verify_media.py          # 质检（含音频波形体检）
│   └── run_episode.py           # 一键串联
├── templates/remotion-project/  # Remotion 工程模板（自包含）
│   └── src/HeartCycle.tsx       # 复杂科普动效样片源码（心脏，0 积分）
├── examples/pipe-valve/         # 完整可跑示例（plan.json 流水线）
└── examples/heart/              # 复杂动效样片：成片 + 方法论 + 踩坑记录
```

---

## 参考文档索引

| 想解决的问题 | 看哪篇 |
|---|---|
| 底图提示词怎么写 | `references/diagram-rules.md` |
| 选哪个 STEM 模板 | `references/templates/` |
| API 报错 / 参数怎么传 | `references/api-handbook.md` |
| 讲稿怎么组织 | `references/teaching-script.md` |
| plan.json 字段含义 | `references/plan-format.md` |
| 想写「整段代码场景」的复杂动效 | `references/motion-layers.md` 第二节之二 + `examples/heart/README.md` |
