# STEM 严格绘图规范

科普视频的底图是「严格性来源」：结构对不对、中文标签准不准，全看这一步。
本文件是写底图提示词时必须遵守的规范。

---

## 一、AI 生图的能力边界（**最重要，先读这段**）

AI 生图模型是**模式匹配器**，不是几何引擎。它能渲染「看起来对」的图，
但**无法保证**：

- 平行线真正平行、直角真是 90°
- 三角形真正全等（边长精确相等）
- 几何关系与公式严格对应
- 公式/文字无拼写错误

### ✅ AI 生图适合（本 skill 主路线）

- 概念示意图、流程图、信息图
- 信号通路、细胞结构（标注准确即可，几何不必精确）
- 机械结构剖视图（视觉清晰即可）
- 教学插图、概念信息图
- 风格化、教学性图表

### ❌ AI 生图不适合（必须用代码生成）

- **数学严格证明图**（勾股定理、欧几里得几何证明、向量/矩阵图）
- **坐标图、函数图像**（坐标系、抛物线、正弦曲线）
- **精确构造图**（圆的内接多边形、角平分线、相似三角形证明）
- **电路图、化学结构式（精确键长/角度）**
- **数据图**（柱状图/折线图/热图）——必须用 matplotlib / plotly

> **判断原则**：图需要「几何正确性」才能传达信息 → 必须用代码。
> 图只需要「视觉传达」概念 → 可以用 AI 生图。
>
> 本 skill 的 `gen_diagrams.py` 走 AI 路线；若你的题目落在 ❌ 那一栏，
> 请改用代码生成底图，再把 PNG 放进 `assets/diagrams/<shot_id>.png`，
> 后续流程（动画/配音/渲染）完全不变。

---

## 二、底图提示词 9 段结构（**强制**）

每一段都要写出来，不能省。AI 对结构化描述的遵循度远高于散文描述。

| # | 段 | 内容 | 例子 |
|---|---|---|---|
| 1 | **Type** | 图表类型 | `Clean flat vector scientific textbook diagram` |
| 2 | **Subject** | 主题与具体内容 | `a cross-section of a pipe carrying water` |
| 3 | **Layout** | 布局 | `vertical portrait, subject centered, generous top and bottom margin` |
| 4 | **Style** | 视觉风格 | `flat vector, textbook illustration, no 3D, no photo texture` |
| 5 | **Color scheme** | hex 码 | `water #2563eb, pipe #6b7280, accents #ef4444` |
| 6 | **Labels** | 字体与标签语言 | `bold black Chinese labels with thin leader lines: 管道, 水流, 阀门` |
| 7 | **Quality** | 质量级别 | `publication-ready, clean crisp outlines, high contrast` |
| 8 | **Constraints** | 禁止项 | `no watermark, no extra text, no garbled characters, no distortion` |
| 9 | **Background** | 背景 | `pure white background #FFFFFF` |

---

## 三、10 条铁律（**强制**）

1. **颜色用 hex 码**：`#2563eb` 数据主色、`#ef4444` 强调/抑制、`#3b82f6` 膜蛋白、`#10b981` 激活
2. **方向显式声明**：`top-to-bottom vertical cascade`、`left-to-right horizontal flow`、`clockwise`
3. **字体明确指定**：中文 `Microsoft YaHei` / `SimHei` 粗体；英文 `Arial` / `Helvetica`
4. **术语标准化**：用 `MAPK/ERK` 不用「细胞信号」；用 `B-form DNA` 不用「DNA」
5. **分辨率和比例**：竖屏科普用 `9:16`；横屏课程用 `16:9`
6. **否定清单**：禁止虚构数据/认证/相互作用/通路分支；禁止箭头方向错误
7. **标注规范**：激活实线、抑制虚线（T 型端）；磷酸化用红圈 `P`
8. **中英混排**：`线粒体 (Mitochondria)`，中文为主时英文括注
9. **多子图编号**：`A`/`B`/`C`/`D` 加粗置于子图左上角
10. **学术合规**：禁止用 AI 生成真实实验数据图（scatter/bar/line），仅限概念示意图

---

## 四、中文标签规范

实测结论（`gpt-image-2` 竖版 9:16）：中文标签**笔画准确、无乱码**，
但**必须显式点名每个词**，否则模型会自行省略标签。

写法要求：

- 把所有中文词**逐个列出来**：`bold black Chinese labels with thin leader lines: 管道, 水流, 阀门`
- 不要写「加上适当的标签」——模型会自己发明词
- 明确字体：`bold Microsoft YaHei sans-serif`
- 明确禁止项：`no English text, no pinyin, no garbled characters`
- 标签数量控制在 3~5 个，超过容易出错

---

## 五、构图规范（竖屏 9:16 特别容易踩）

- **竖屏会强行改变物体朝向**：横管可能被画成竖管。
  → 必须在 Layout 段显式写：`the pipe is HORIZONTAL, running left to right`
- **上下留白**：底部要留出字幕区。写 `generous empty margin at the bottom for subtitles`
- **主体居中偏上**：`subject centered in the upper two-thirds`
- **元素不出画**：写 `all elements fully within the canvas, nothing cropped`
- **标签不压主体**：写 `labels placed outside the subject with thin leader lines`

### ★ 边缘裁切问题（实测高发）

AI 生图常把结构画到画面边缘 —— 实测三张底图的**左右 12% 区域都有 8%~15% 的墨水**，
意思是横管这类横向元素几乎顶到画面边缘。

后果：字幕条压上来时，边缘的中文标签（「管道」）会被切掉一半。

**三个层面一起防**：

1. **提示词层**（推荐）：
   `the entire subject fits within the central 80% of the canvas with clear white margin on all four sides`
2. **渲染层**（本 skill 已内置）：
   静态层用 `contain` + 4.5% 内缩（`INSET`），底图整体内缩，边缘内容不会被切
3. **检查层**（可选）：
   ```bash
   python scripts/pad_diagram.py plan.json          # 检查四边墨水
   python scripts/pad_diagram.py plan.json --pad    # 加白边修补
   ```

**推镜幅度也要克制**：缩放超过 1.12 就会把边缘标签推出去。
`StillMotion` 已把缩放上限锁在 1.12。

---

## 六、风格一致性（多拍必做）

一集科普片里每拍的底图必须是「同一张图」的感觉。**Campaign Style Lock**：

| 项目 | 锁定内容 |
|---|---|
| 固定色板 | 2~3 主色 + 1 强调色，全部 hex |
| 统一字体 | 中文一种 + 英文一种 |
| 统一线条 | 线宽、颜色、端点一致 |
| 统一背景 | 纯白 `#FFFFFF` |
| 统一标注框 | 圆角矩形、半透明白底 |

→ 做法：把 Style/Color/Background 三段**逐字复用**，
只换 Type/Subject/Layout/Constraints 四段。

---

## 七、场景模板

`references/templates/` 下有 24 个模板，按场景编号：

| # | 模板 ID | 场景 | # | 模板 ID | 场景 |
|---|---|---|---|---|---|
| 01 | signaling-pathway | 信号通路/机制图 | 13 | multi-panel-figure | 多子图组合 |
| 02 | experimental-workflow | 实验流程/技术路线 | 14 | plasmid-map | 质粒图/分子结构 |
| 03 | cell-structure | 细胞/解剖结构 | 15 | machine-mechanism | 机械/工程示意 |
| 04 | data-infographic | 数据可视化信息图 | 16 | physics-schematic | 物理原理示意 |
| 05 | academic-poster | 双语学术海报 | 17 | chemistry-structure | 化学结构/反应机理 |
| 06 | concept-infographic | 概念教育信息图 | 18 | math-concept | 数学概念可视化 |
| 07 | timeline | 科学史时间线 | 19 | graphical-abstract | 论文图文摘要 |
| 08 | comparison-matrix | 对比矩阵 | 20 | lab-safety | 实验室安全规范 |
| 09 | cross-section | 截面/剖视图 | 21 | educational-poster | 教学海报 |
| 10 | hub-spoke | 中心辐射图 | 22 | step-by-step | 步骤说明图 |
| 11 | hierarchical-tree | 层级树/分类树 | 23 | architecture-diagram | 系统/算法架构图 |
| 12 | cyclic-flow | 循环流程图 | 24 | bilingual-diagram | 中英双语通用图 |

每模板字段：

- `id` / `name` / `keywords` / `trigger_phrases` —— 检索与匹配
- `prompt_template` —— 9 段式模板，把变量填进去
- `defaults` —— 推荐尺寸与变体
- `variants` —— `academic` / `textbook` / `infographic` / `3d-render`
- `category_tips` —— 学科专属提示
- `accuracy_tips` —— 准确性红线
- `supports_image_reference` —— **能否喂参考图给视频模型**（关键开关）

> `supports_image_reference: true` 的模板更适合做**动画**：
> 首帧驱动时结构保真度更高。

---

## 八、常见翻车点与防护

| 翻车 | 防护 |
|---|---|
| 蛋白质名错误 | 对照 KEGG/UniProt；用标准基因符号 |
| 箭头方向错误 | 显式声明 `top-to-bottom` / `left-to-right` |
| 中文乱码/缺笔画 | 逐个点名标签 + 指定 `Microsoft YaHei` |
| 竖屏把横管画成竖管 | Layout 段写 `the pipe is HORIZONTAL` |
| 标签被裁掉 | 写 `all labels fully visible, nothing cropped` |
| 模型自行加标签 | 写 `no extra text, only the labels listed above` |
| 模型渲染成照片风 | 写 `flat vector illustration, no photo texture, no 3D` |
| 整套图风格漂移 | 严格复用 Style/Color/Background 三段 |
| 化学/通路跨学科混淆 | Prompt 头部加 `PURE CHEMISTRY ONLY. NO biology, NO cells.` |
| **AI 无法保证数学精确性** | 数学/几何/数据图必须用代码生成，不能靠 AI |
| **AI 对细微状态不敏感** | 让 AI「把手轮转开」它不会转 → 精确状态变更必须代码绘制 |
